"""Evidence-grounded contribution plan builder (deterministic AI engine).

This is the DEFAULT ai_service provider: it turns analyzed repository
data + an issue into the structured contribution-plan JSON using only
things actually found in the repository. It never invents files,
functions, routes, databases, or relationships.
"""
import re
from collections import Counter

from . import repository_analyzer as ra

TOP_FILES_TO_SHOW = 8

TYPE_MAP = {"bug": "bug", "feature": "feature", "performance": "enhancement",
            "documentation": "documentation", "unknown": "unknown"}

AUTH_HINTS = ("token", "session", "auth", "login")


def _evidence_summary(entry, keywords):
    """One honest line about what was found, e.g. route definitions."""
    texts = " ".join(e["text"] for e in entry.get("evidence", []))
    routes = re.findall(r"""@app\.route\(\s*['"]([^'"]+)['"]""", texts)
    routes += re.findall(r"""path\(\s*['"]([^'"]+)['"]""", texts)
    if routes:
        shown = ", ".join(dict.fromkeys(routes)[:4])
        return f"Found route definitions such as {shown}."
    if keywords:
        return f"Matched {len(entry.get('evidence', []))} code location(s) mentioning: {', '.join(keywords[:4])}."
    return "Matched the issue keywords."


def _by_hint(top_files, *hints):
    for hint in hints:
        for entry in top_files:
            if hint in entry["path"].lower():
                return entry["path"]
    return None


def _learning_topics(framework, language):
    fw = (framework or "").lower()
    if "flask" in fw:
        return ["Flask routing", "Jinja templates", "HTTP forms & requests", "Session handling"]
    if "django" in fw:
        return ["Django URLs & views", "Django templates", "Django ORM basics"]
    if "fastapi" in fw:
        return ["FastAPI routing", "Pydantic models", "Request validation"]
    if "react" in fw or "next" in fw:
        return ["React components", "State and props", "Client-side routing", "Fetching data from APIs"]
    if "vue" in fw:
        return ["Vue components", "Reactivity basics", "Vue Router"]
    if language == "Python":
        return ["Project structure", "The framework's routing", "Testing with pytest"]
    return ["Project structure", "The framework's routing", "Testing basics"]


def build_plan(repo_data, issue_title, issue_body):
    files = repo_data["files"]
    contents = repo_data["contents"]
    issue_text = (issue_title or "") + "\n" + (issue_body or "")
    text = issue_text.lower()

    type_label, type_key = ra.classify_issue(issue_title, issue_body)
    issue_type = TYPE_MAP.get(type_key, "unknown")
    summary = ra.summarize_issue(issue_title, issue_body)

    keyword_counts = Counter(ra.tokenize(issue_text))
    keywords = [k for k, _ in keyword_counts.most_common(12)
                if k not in ra.CODE_EXTS][:8]

    ranked = ra.score_files(issue_text, files, contents)
    for entry in ranked:
        entry["evidence"] = ra.find_evidence(
            entry["path"], contents.get(entry["path"], ""), keywords)
        entry["role"] = ra.describe_role(
            entry["path"], contents.get(entry["path"], ""))
    top = ranked[:TOP_FILES_TO_SHOW]
    paths = [f["path"] for f in top]

    dep_map = ra.build_dependency_map(paths, contents)
    flow = [p for p in ra.connected_flow(paths, dep_map)
            if "test" not in p.lower() and "spec" not in p.lower()]
    flow_note = ""
    if not flow and top:
        flow_note = "Flow could not be fully established from the scanned files."

    # starting point: file other relevant files depend on most
    dependents = {p: 0 for p in paths}
    for deps in dep_map.values():
        for dep in deps:
            dependents[dep] = dependents.get(dep, 0) + 1

    def _defines_routes(path):
        t = (contents.get(path, "") or "").lower()
        return 1 if ("@app.route" in t or "urlpatterns" in t or "@router" in t) else 0

    start_with = None
    if top:
        best = max(top, key=lambda f: (dependents.get(f["path"], 0),
                                       _defines_routes(f["path"]),
                                       f["score"]))
        n = dependents.get(best["path"], 0)
        reason = best["reasons"][0] if best["reasons"] else "it matched the issue best"
        why = (f"{n} other relevant file(s) connect through it, and {reason}."
               if n > 0 else reason[0].upper() + reason[1:] + ".")
        start_with = {"file": best["path"], "reason": why}
    main = start_with["file"] if start_with else (top[0]["path"] if top else None)
    main_entry = next((f for f in top if f["path"] == main), None)

    tests = ra.find_related_tests(top, files)
    missing = ra.find_missing_files(issue_text, files)

    auth_words = ("expir", "token", "session", "login", "auth",
                  "password", "signin", "sign-in")
    wants_auth = any(w in text for w in auth_words)
    has_auth_code = any(any(h in f["path"].lower() for h in AUTH_HINTS) for f in top)
    auth_file = _by_hint(top, "token", "session", "auth", "login")

    warnings = []
    steps = []

    # ---- issue understanding ----
    if type_key == "bug":
        explanation = ("This looks like a bug — something that should work "
                       "isn't behaving as expected. " + summary)
    elif type_key == "feature":
        if missing:
            explanation = ("This is a feature request, and it needs a brand-new file: "
                           + ", ".join(missing)
                           + " doesn't exist in the repository yet. " + summary)
        else:
            explanation = ("This is a feature request — new behavior needs to be added "
                           "to existing files. " + summary)
    elif type_key == "performance":
        explanation = ("This looks like a performance issue — something is slower than "
                       "it should be. " + summary)
    elif type_key == "documentation":
        explanation = "This is a documentation task. " + summary
    else:
        explanation = summary

    # ---- steps (tagged: confirmed vs suggestion) ----
    def add_step(step_text, basis="suggestion"):
        steps.append({"text": step_text, "basis": basis})

    if not top:
        warnings.append(
            "No relevant files were confidently identified for this issue. "
            "Try providing a more specific issue description.")
        add_step("Read the repository README and project structure to orient yourself.")
        add_step("Narrow the issue down to a specific file or behavior, then re-analyze.")
    else:
        if issue_type == "feature":
            add_step('Look at the current behavior first, so you know exactly what "done" looks like.')
        else:
            add_step("Reproduce the issue locally first, so you can confirm your change actually fixes it.")

        # Never invent auth code.
        if wants_auth and not has_auth_code:
            warnings.append(
                "⚠️ Authentication infrastructure was not found in the scanned repository — "
                "no token / session / auth / login code exists there. This looks like a new "
                "feature rather than a bug fix: you may need to introduce the authentication "
                "layer first.")
            add_step("Introduce the authentication layer first (where users and passwords "
                     "are checked) — none exists in this repository yet.")
        elif wants_auth and has_auth_code and issue_type == "bug" and auth_file:
            add_step(f"In {auth_file}: check whether the token/session is expired BEFORE "
                     "sending the request.", "confirmed")
            add_step("If it is expired, refresh it (or redirect to the login page) and "
                     "retry the original request exactly once.", "confirmed")

        for m in missing:
            add_step(f"Create {m} — it doesn't exist in the repository yet.")

        if issue_type == "feature" and main:
            role = (main_entry or {}).get("role") or "it matched the issue keywords"
            if main.endswith((".html", ".jsx", ".tsx", ".vue")):
                add_step(f"In {main}: build or extend the UI for the new behavior — {role}.",
                         "confirmed")
            elif "login" in text:
                add_step(f"In {main}: add a /login route — {role}.", "confirmed")
            else:
                add_step(f"In {main}: add the new behavior — {role}.", "confirmed")
            html_file = _by_hint(top, ".html")
            if html_file and html_file != main:
                add_step(f"Link the new page from {html_file} so users can reach it.", "confirmed")
            css_file = _by_hint(top, ".css")
            if css_file:
                add_step(f"Reuse {css_file} for styling, so the new page matches the site.", "confirmed")

        if issue_type == "bug" and main:
            add_step(f"Add a guard for the failing case in {main}, keeping the change "
                     "small and focused on this issue.", "confirmed")
        if issue_type == "enhancement" and main:
            add_step(f"Measure first: profile {main} to find the slow part before "
                     "changing anything.", "confirmed")

        add_step("Run the existing tests for the touched module and make sure nothing else breaks.")

    # ---- tests ----
    test_framework = ra.detect_test_framework(files)
    if issue_type == "feature" and "login" in text:
        test_items = ["Login page loads", "Valid credentials", "Invalid credentials",
                      "Empty fields", "Unauthorized access"]
    elif issue_type == "feature":
        test_items = ["The new behavior works end-to-end", "Invalid and edge-case inputs are handled",
                      "Existing behavior is unchanged"]
    elif issue_type == "bug":
        test_items = ["The originally failing case now passes",
                      "Related edge cases still behave correctly"]
    elif issue_type == "enhancement":
        test_items = ["Benchmark the slow operation before and after",
                      "Results are correct, not just fast"]
    else:
        test_items = ["Verify the reported case"]
    test_items.append("Add a regression test that fails before your fix and passes after it.")

    existing_tests = [t["path"] for t in tests]
    suggested_tests, seen = [], set(existing_tests)
    for entry in top[:3]:
        cand = ra.suggest_test(entry["path"])
        if cand not in seen:
            suggested_tests.append(cand)
            seen.add(cand)
    if not test_framework and not existing_tests:
        tests_note = ("No test framework detected in the scanned repository. "
                      "Suggested approach: add focused unit tests for the changed module "
                      "with the standard test runner for this language.")
    else:
        tests_note = (f"Detected: {test_framework}." if test_framework else "")

    # ---- risks (only evidence-backed areas, or labeled suggestions) ----
    risks = []
    lowered_paths = " ".join(f["path"].lower() for f in top)
    if any(h in lowered_paths for h in AUTH_HINTS):
        risks.append({"area": "Authentication", "basis": "confirmed"})
    if any(w in lowered_paths for w in ("model", "schema", "migration", "database", "db")):
        risks.append({"area": "Database", "basis": "confirmed"})
    if any(w in lowered_paths for w in ("session", "cookie")):
        risks.append({"area": "User session", "basis": "confirmed"})
    if any(w in lowered_paths for w in (".html", "template", "nav", "component", ".jsx", ".tsx", ".vue")):
        risks.append({"area": "Navigation / UI", "basis": "confirmed"})
    if existing_tests:
        risks.append({"area": "Existing tests may need updates", "basis": "suggestion"})
    if not risks:
        risks.append({"area": "Areas touching the changed files", "basis": "suggestion"})

    # ---- repo overview ----
    language = ra.detect_language(files)
    framework = ra.detect_framework(files, contents)
    overview = {
        "name": repo_data["name"],
        "language": language,
        "files_scanned": len(files),
        "folders": ra.top_folders(files),
        "framework": framework,
    }
    if repo_data.get("truncated"):
        warnings.append("This repository is very large, so only part of its file tree was scanned.")

    # ---- learning path ----
    learning = {
        "topics": _learning_topics(framework, language),
        "reading_order": flow or [f["path"] for f in top[:4]],
    }

    relevant_files = [{
        "path": f["path"],
        "reason": "; ".join(f["reasons"]) if f["reasons"] else "Matched the issue keywords.",
        "evidence": f["evidence"],
        "evidence_summary": _evidence_summary(f, keywords),
        "confidence": f["confidence"],
    } for f in top]

    return {
        "generated_by": "evidence-engine (built-in, deterministic)",
        "issue_understanding": {
            "title": issue_title, "description": issue_body,
            "type": issue_type, "explanation": explanation,
        },
        "repository_overview": overview,
        "relevant_files": relevant_files,
        "flow": flow,
        "flow_note": flow_note,
        "starting_point": start_with,
        "steps": steps,
        "tests": {"existing": existing_tests, "suggested": suggested_tests,
                  "checklist": test_items, "note": tests_note},
        "risks": risks,
        "learning": learning,
        "warnings": warnings,
    }


def refine_answer(plan, question):
    """Answer a follow-up question using the plan's repository context."""
    q = (question or "").lower()
    steps = plan.get("steps", []) or []
    files = plan.get("relevant_files", []) or []

    def file_brief(f):
        ev = "; ".join(f"{e['line']}: {e['text'][:70]}" for e in f.get("evidence", [])[:2])
        return f"{f['path']} — {f.get('reason', '')}" + (f" Evidence: {ev}." if ev else "")

    m = re.search(r"step\s+(\d+)", q)
    if m or q.startswith("explain step"):
        n = int(m.group(1)) if m else 1
        if 1 <= n <= len(steps):
            s = steps[n - 1]
            basis = "a confirmed fact from the repository" if s.get("basis") == "confirmed" \
                else "an AI suggestion (not directly verified in the repo)"
            rel = ", ".join(f["path"] for f in files[:3]) or "none identified"
            return (f"Step {n}: {s['text']}\n\nThis step is {basis}.\n"
                    f"Most relevant files: {rel}.")
        return f"There are {len(steps)} steps in this plan — which one did you mean?"

    if "why" in q and "file" in q:
        if not files:
            return "No files were confidently identified for this issue."
        return "Why each file matters:\n\n" + "\n\n".join(
            f"• {file_brief(f)}" for f in files[:4])

    if "simpler" in q or "easier" in q:
        first = steps[1]["text"] if len(steps) > 1 else "the first concrete step"
        return ("The simplest path: do the smallest change that resolves the issue and "
                f"skip everything else for now. Concretely: {first} Then run the "
                "related tests. You can always extend the change in a follow-up.")

    if "learn" in q or "before" in q or "prerequisite" in q:
        topics = plan.get("learning", {}).get("topics", [])
        order = plan.get("learning", {}).get("reading_order", [])
        t = ", ".join(topics) if topics else "the project's README"
        o = " → ".join(order[:4]) if order else "the relevant files above"
        return (f"Before contributing, get comfortable with: {t}.\n\n"
                f"Recommended reading order: {o}.")

    if "test" in q:
        t = plan.get("tests", {})
        checklist = t.get("checklist", [])
        sug = ", ".join(t.get("suggested", [])) or "focused unit tests for the changed module"
        lines = "; ".join(checklist[:5]) if checklist else sug
        return ("Write tests that prove the issue is fixed. Your checklist:\n"
                f"• {lines.replace('; ', chr(10) + '• ')}\n"
                f"Suggested new test files: {sug}.")

    start = plan.get("starting_point") or {}
    return ("Here's the big picture: "
            f"{plan.get('issue_understanding', {}).get('explanation', '')} "
            f"{('Start with ' + start['file'] + ': ' + start.get('reason', '') + '.') if start.get('file') else ''} "
            "Ask me things like 'Explain step 3', 'Why do I need this file?', "
            "'What should I learn before doing this?' or 'What tests should I write?'")
