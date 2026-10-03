"""Repository analysis — pure analysis, no HTTP.

The scan pipeline (all GitHub I/O lives in github_client):

    metadata -> file tree -> filter irrelevant files -> score filenames
    against the issue -> fetch ONLY the relevant source files
    -> evidence / dependency flow / repo overview

An analysis costs ~2 GitHub API calls (metadata + tree). File contents come
from raw.githubusercontent.com, which does not consume API quota.
"""
import os
import re
from collections import Counter

from . import github_client

MAX_FILES_TO_READ = 15  # relevant files fetched per analysis

TEXT_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue",
    ".py", ".java", ".kt", ".go", ".rb", ".php", ".c", ".h",
    ".cpp", ".cs", ".swift", ".rs", ".html", ".css", ".scss",
    ".json", ".yml", ".yaml", ".xml", ".md", ".txt",
    ".toml", ".cfg", ".ini", ".gradle", ".properties",
}

CODE_EXTS = {
    "html", "js", "jsx", "ts", "tsx", "mjs", "cjs", "vue",
    "py", "java", "kt", "go", "rb", "php", "c", "h", "cpp",
    "cs", "swift", "rs", "css", "scss", "json", "yml", "yaml",
    "xml", "md", "txt",
}

# Directories / files that are never relevant to a contribution plan.
IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build",
    ".venv", "venv", "coverage", ".idea", ".vscode", "target",
    "out", ".next", ".nuxt",
}
IGNORE_BASENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "Gemfile.lock", "composer.lock", "Cargo.lock",
}
GENERATED_SUFFIXES = (".min.js", ".min.css", ".bundle.js")


def is_ignored(path):
    """True for vendored, generated, or binary-adjacent paths."""
    parts = path.split("/")
    if any(part in IGNORE_DIRS for part in parts[:-1]):
        return True
    base = parts[-1]
    if base in IGNORE_BASENAMES or base.endswith(GENERATED_SUFFIXES):
        return True
    return False


def is_text_file(path):
    name = path.lower()
    base = name.rsplit("/", 1)[-1]
    if base in ("dockerfile", "makefile", "readme", "license",
                "changelog", "contributing", "authors"):
        return True
    return any(name.endswith(ext) for ext in TEXT_EXTENSIONS)


STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "when", "what", "how", "why", "that", "this", "these", "those", "then",
    "than", "from", "into", "are", "was", "were", "been", "has", "have",
    "had", "does", "did", "will", "would", "should", "could", "can", "may",
    "might", "must", "not", "no", "yes", "if", "else", "its", "it", "as",
    "at", "by", "be", "is", "but", "also", "any", "all", "each", "other",
    "such", "only", "just", "very", "more", "most", "some", "there",
    "their", "they", "them", "you", "your", "we", "our", "us", "who",
    "which", "because", "until", "while", "about", "after", "again",
    "here", "once", "own", "same", "too", "now", "app", "page", "get",
    "gets", "got", "goes", "going", "make", "made", "using", "use",
    "used", "via", "etc", "out", "off", "reproduce", "steps",
    "step", "expected", "actual",
}


def scan_repository(repo_url, issue_text):
    """Run the full scan pipeline. Returns repo_data for the AI layer."""
    parsed = github_client.parse_repo_url(repo_url)
    if not parsed:
        raise github_client.RepoFetchError(
            "That doesn't look like a GitHub repository URL. "
            "Use something like https://github.com/owner/repo", 422)
    owner, repo = parsed

    meta = github_client.get_repo_meta(owner, repo)
    branch = meta.get("default_branch", "main")
    tree, truncated = github_client.get_file_tree(owner, repo, branch)

    files = [p for p in tree
             if not is_ignored(p) and is_text_file(p)]
    if not files:
        raise github_client.RepoFetchError(
            "No readable source files found in this repository.", 422)

    # Identify relevant files from names first — only these are downloaded.
    ranked_names = score_by_name(issue_text, files)
    shortlist = [p for p, s in ranked_names if s > 0][:MAX_FILES_TO_READ]
    if not shortlist:
        shortlist = [p for p, _ in ranked_names[:MAX_FILES_TO_READ]]

    contents = {}
    for path in shortlist:
        contents[path] = github_client.get_file_content(owner, repo, path, branch)

    return {
        "name": f"{owner}/{repo}",
        "branch": branch,
        "files": files,
        "contents": contents,
        "truncated": truncated,
    }

# ------------------------------------------------------------------ text utils

def tokenize(text):
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text or "")
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_]*", text.lower())
    return [w for w in words if len(w) >= 3 and w not in STOPWORDS]


def _path_tokens(path):
    return tokenize(re.sub(r"[/_.\-]", " ", path))


def score_by_name(issue_text, files):
    keywords = set(tokenize(issue_text))
    scored = []
    for path in files:
        hits = keywords & set(_path_tokens(path))
        scored.append((path, len(hits)))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored


def score_files(issue_text, files, contents):
    keywords = Counter(tokenize(issue_text))
    ranked = []
    for path in files:
        content = contents.get(path, "") or ""
        score, reasons = 0, []
        name_hits = sorted({kw for kw in keywords if kw in _path_tokens(path)})
        if name_hits:
            score += 6 * len(name_hits)
            reasons.append(f"filename matches issue keyword(s): {', '.join(name_hits[:4])}")
        content_lower = content.lower()
        hits = sum(content_lower.count(kw) for kw in keywords)
        if hits:
            score += min(hits, 20)
            top = [kw for kw, _ in keywords.most_common(4) if kw in content_lower]
            if top:
                reasons.append(f"mentions: {', '.join(top)}")
        if score > 0:
            confidence = "high" if score >= 12 else ("medium" if score >= 5 else "low")
            ranked.append({"path": path, "score": score, "reasons": reasons,
                           "confidence": confidence})
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def find_evidence(path, content, keywords, per_file=3):
    kws = [k for k in dict.fromkeys(keywords or []) if len(k) >= 3]
    if not content or not kws:
        return []
    evidence = []
    for lineno, raw in enumerate(content.splitlines(), 1):
        if len(evidence) >= per_file:
            break
        line = raw.strip()
        if line and any(kw in line.lower() for kw in kws):
            evidence.append({"line": lineno, "text": line[:160]})
    return evidence


def describe_role(path, content):
    text = (content or "").lower()
    if "@app.route" in text or "urlpatterns" in text:
        return "it defines the application's routes"
    if re.search(r"^\s*(def |function |class )", text, re.M):
        return "it contains the logic involved in the issue"
    if "<form" in text or "<html" in text:
        return "it renders the UI involved in the issue"
    return "it matched the issue keywords"


def summarize_issue(title, body):
    body = (body or "").strip()
    if not body:
        return title
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()]
    return " ".join(sentences[:2]) or title


def classify_issue(title, body):
    text = ((title or "") + " " + (body or "")).lower()
    if any(w in text for w in ("traceback", "exception", "crash", "broken",
                               "fail", "error", "bug", "wrong", "blank",
                               "not work", "doesn't work", "401", "404", "500")):
        return "Bug Fix", "bug"
    if any(w in text for w in ("slow", "performance", "optimis", "optimiz", "lag")):
        return "Performance", "performance"
    if any(w in text for w in ("readme", "documentation", "document", "docstring")):
        return "Documentation", "documentation"
    if any(w in text for w in ("add", "feature", "implement", "support", "create", "new")):
        return "Feature Request", "feature"
    return "General Task", "unknown"


def find_missing_files(issue_text, all_files):
    known = {p.rsplit("/", 1)[-1].lower() for p in (all_files or [])}
    missing = []
    for match in re.finditer(r"[\w\-./]+\.\w+", issue_text or ""):
        token = match.group(0).strip("./")
        base = token.rsplit("/", 1)[-1]
        ext = base.rsplit(".", 1)[-1].lower()
        if ext not in CODE_EXTS or len(base) < 5:
            continue
        if base.lower() not in known and token not in missing:
            missing.append(token)
    return missing[:5]


def find_related_tests(top_files, all_files):
    tests = [p for p in all_files if "test" in p.lower() or "spec" in p.lower()]
    found = []
    for entry in top_files:
        stem = entry["path"].split("/")[-1].rsplit(".", 1)[0].lower()
        for test_path in tests:
            if stem and stem in test_path.split("/")[-1].lower() \
                    and test_path != entry["path"]:
                found.append({"path": test_path, "for": entry["path"]})
                break
    return found


def suggest_test(path):
    name = path.split("/")[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    ext = name.rsplit(".", 1)[1].lower() if "." in name else ""
    if ext in ("js", "jsx", "ts", "tsx", "mjs", "cjs", "vue"):
        return f"tests/{stem}.test.js"
    if ext == "py":
        return f"tests/test_{stem}.py"
    if ext == "java":
        return f"tests/{stem}Test.java"
    return f"tests/{stem}.test"

# ------------------------------------------------------------ dependency graph

IMPORT_PATTERNS = {
    (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue"): [
        re.compile(r"""import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]"""),
        re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
    ],
    (".py",): [
        re.compile(r"^\s*from\s+([\w.]+)\s+import", re.M),
        re.compile(r"^\s*import\s+([\w.]+)", re.M),
    ],
    (".java", ".kt"): [re.compile(r"^\s*import\s+([\w.]+)\s*;", re.M)],
}
SUFFIXES = ["", ".js", ".jsx", ".ts", ".tsx", ".py", ".java",
            "/index.js", "/index.jsx"]


def _resolve(importer, imported, path_set, stem_index):
    imported = (imported or "").strip()
    if not imported:
        return None
    if imported.startswith("."):
        dots = len(imported) - len(imported.lstrip("."))
        rest = imported[dots:].lstrip("/").replace(".", "/")
        base = os.path.normpath(os.path.join(
            os.path.dirname(importer), "../" * (dots - 1) + rest))
        for suffix in SUFFIXES:
            if base + suffix in path_set:
                return base + suffix
        return None
    tail = imported.replace(".", "/").split("/")[-1]
    cands = stem_index.get(tail, [])
    return cands[0] if cands else None


def build_dependency_map(paths, contents):
    path_set = set(paths)
    stem_index = {}
    for path in paths:
        stem = os.path.splitext(os.path.basename(path))[0]
        stem_index.setdefault(stem, []).append(path)
    for stem in stem_index:
        stem_index[stem].sort(key=len)
    dep_map = {}
    for path in paths:
        ext = os.path.splitext(path)[1].lower()
        patterns = []
        for extensions, pats in IMPORT_PATTERNS.items():
            if ext in extensions:
                patterns = pats
                break
        raw = []
        for pat in patterns:
            raw.extend(pat.findall(contents.get(path, "") or ""))
        resolved = set()
        for imp in raw:
            target = _resolve(path, imp, path_set, stem_index)
            if target and target != path:
                resolved.add(target)
        dep_map[path] = sorted(resolved)
    return dep_map


def order_flow(paths, dep_map):
    path_set = set(paths)
    adjacency = {p: [d for d in dep_map.get(p, []) if d in path_set] for p in paths}
    visited, on_walk, order = set(), set(), []

    def visit(node):
        if node in visited or node in on_walk:
            return
        on_walk.add(node)
        for dep in adjacency[node]:
            visit(dep)
        on_walk.remove(node)
        visited.add(node)
        order.append(node)

    for path in paths:
        visit(path)
    order.reverse()
    return order


def connected_flow(paths, dep_map):
    """Only relationships actually found in the code — never guessed."""
    path_set = set(paths)

    def has_edge(path):
        return (any(d in path_set for d in dep_map.get(path, []))
                or any(path in dep_map.get(other, []) for other in paths))

    connected = [p for p in paths if has_edge(p)]
    return [p for p in order_flow(connected, dep_map) if p in set(connected)]

# ------------------------------------------------------ repo characteristics

EXT_LANGUAGE = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".go": "Go", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    ".cpp": "C++", ".c": "C", ".rs": "Rust", ".kt": "Kotlin",
    ".swift": "Swift",
}


def detect_language(files):
    counts = Counter()
    for path in files:
        lang = EXT_LANGUAGE.get(os.path.splitext(path)[1].lower())
        if lang:
            counts[lang] += 1
    return counts.most_common(1)[0][0] if counts else "Unknown"


def detect_framework(files, contents):
    names = {p.rsplit("/", 1)[-1].lower() for p in files}
    structural_names = ("package.json", "requirements.txt", "pyproject.toml",
                        "setup.py", "go.mod", "cargo.toml", "pom.xml")
    ordered = ([contents[p] for p in contents
                if p.rsplit("/", 1)[-1].lower() in structural_names]
               + list(contents.values()))
    sample = "\n".join(ordered).lower()
    if "package.json" in names:
        if "next.config" in names or '"next"' in sample:
            return "Next.js"
        if any(p.endswith(".vue") for p in files) or '"vue"' in sample:
            return "Vue"
        return "React" if "react" in sample else "Node.js"
    if "requirements.txt" in names or "pyproject.toml" in names or "setup.py" in names:
        if "django" in sample:
            return "Django"
        if "flask" in sample:
            return "Flask"
        if "fastapi" in sample:
            return "FastAPI"
        return "Python"
    if "go.mod" in names:
        return "Go"
    if "cargo.toml" in names:
        return "Rust"
    if "pom.xml" in names or "build.gradle" in names:
        return "Java"
    return "Not detected"


def detect_test_framework(files):
    names = {p.rsplit("/", 1)[-1].lower() for p in files}
    lowered = " ".join(names)
    if "jest" in lowered or "vitest" in lowered:
        return "Jest/Vitest"
    if "pytest" in lowered:
        return "pytest"
    if "junit" in lowered or "testng" in lowered:
        return "JUnit"
    if any("test" in p.lower() or "spec" in p.lower() for p in files):
        return "Detected (unidentified runner)"
    return ""


def top_folders(files, limit=6):
    counts = Counter()
    for path in files:
        if "/" in path:
            top = path.split("/")[0]
            if not top.startswith("."):
                counts[top] += 1
    return [f for f, _ in counts.most_common(limit)]
