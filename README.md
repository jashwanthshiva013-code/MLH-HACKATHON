# ContribGuide AI

**Tagline:** *Understand an open-source issue. Find where to start. Follow a clear contribution plan.*

**Positioning:** *Evidence-Grounded AI Contribution Guide* — not another code explainer.

Built for the **MLH × DEV × React Hyderabad Hack Day** — *"Best Open-Source AI Project"* challenge.

---

## Problem

New contributors often struggle to understand unfamiliar repositories and translate
GitHub issues into concrete development tasks. Existing AI tools answer
*"what is this code?"* — but a new contributor needs the answer to
*"I want to contribute — what exactly should I do?"*

## Solution

ContribGuide AI takes a **public GitHub repository URL** + a **GitHub issue**
and generates an **evidence-grounded, step-by-step contribution plan**:

- What the issue means (classified: Bug / Feature / Enhancement / Documentation)
- Repository overview (language, framework, files scanned, key folders)
- Which files are relevant — and **why**, with code evidence from the repo
- How the relevant files are connected (only real relationships — nothing invented)
- Where to start, with the reason
- A numbered contribution plan, each step labeled **Confirmed from repository**
  or **AI suggestion**
- A test plan (existing tests + suggested new tests + verification checklist)
- Potential impact / risks, evidence-backed
- A learning path (concepts + recommended reading order)
- A **Refine Plan** Q&A that answers follow-ups using the repository context

The AI **guides** the developer. It never modifies the repository.

## Key Features

- **Evidence grounding** — every recommendation cites actual code (file + line number)
  and carries a confidence level (high / medium / low)
- **Honest analysis** — if the repo has no auth code, it says
  *"Authentication infrastructure was not found in the scanned repository"*
  instead of inventing it; if no import relationships exist, it says the flow
  could not be established
- **Structured AI output** — the backend validates every plan against a Pydantic
  schema before the frontend ever sees it; invalid AI output is rejected, never rendered
- **Replaceable AI providers** — deterministic built-in engine by default, or plug in
  any open-weight model via Ollama / OpenAI-compatible endpoint (env-configured)
- **Two offline demos** — bug fix and feature request, no GitHub access needed
- **Refine Plan** — ask "Explain step 3", "Why do I need this file?",
  "What should I learn before doing this?", …

## How It Works

```
GitHub Issue
     ↓
Repository Analysis  (tree → ignore junk → score files → collect evidence → trace imports)
     ↓
Relevant Code
     ↓
Evidence
     ↓
AI Provider  (evidence engine | open-weight LLM via Ollama / compatible API)
     ↓
Validated JSON plan
     ↓
Contribution Plan → Test Plan → Developer
```

## AI Architecture

`backend/ai_service.py` exposes one function:

```python
analyze_repository_issue(repository_context, issue) -> plan dict
```

- **Repository context** is deliberately compact: file paths, matched code
  snippets, import relationships, repo overview — the whole repo is never
  dumped into the model.
- **Default provider (`evidence`)**: a deterministic engine
  (`backend/evidence_engine.py`) that builds the plan purely from repository
  evidence. Zero API keys, works offline — ideal for hackathon demos.
- **LLM providers (`ollama`, `openai_compatible`)**: send the compact context
  with a strict grounding system prompt and parse **structured JSON** back,
  validated with Pydantic. Switch with environment variables — no code changes.
- `POST /api/refine` answers follow-up questions from the plan's context.

## Why AI Is Central

Without the AI layer this would be a static repo browser. The AI:

1. Maps free-text issues to ranked, evidence-backed file recommendations
2. Explains *why* each file matters in contributor terms
3. Orders files into a real dependency flow
4. Drafts implementation steps and distinguishes confirmed facts from suggestions
5. Generates a test plan and risk assessment tailored to the issue type

## Novelty

Other tools: `Repository → AI → "here is what the repo does"` (a chatbot).

ContribGuide AI: `Issue → actual repository code → evidence-backed contribution plan`
(an AI mentor for your first contribution).

## Tech Stack

- **Frontend:** React 18 + Vite, hand-written modern CSS (light developer-tool aesthetic)
- **Backend:** Python + FastAPI, Pydantic validation, `requests` for GitHub API
- **AI:** built-in evidence engine (default) · Ollama / OpenAI-compatible open-weight models (optional)

## Installation

**Backend:**
```bash
cd backend
pip install -r requirements.txt
```

**Frontend:**
```bash
cd frontend
npm install
```

## Environment Variables

All configuration lives in `backend/.env` (see `backend/.env.example`).
The token is used **only by the backend** — it is never sent to the browser.

| Variable | Default | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | — | GitHub API token. Raises the rate limit 60 → 5,000 req/hour |
| `AI_PROVIDER` | `evidence` | `evidence` · `ollama` · `openai_compatible` |
| `AI_API_KEY` | — | Key for an OpenAI-compatible endpoint (alias for `OPENAI_COMPAT_KEY`) |
| `OPENAI_COMPAT_URL` | — | Any OpenAI-compatible chat-completions endpoint |
| `OPENAI_COMPAT_MODEL` | — | Model name |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `llama3.1` | Open-weight model name |

## GitHub token setup

The backend calls the GitHub REST API on behalf of the application — the end
user never logs in and never sees the token.

1. **Create a token:** github.com → your profile → **Settings** → **Developer
   settings** → **Personal access tokens** → **Tokens (classic)** →
   **Generate new token (classic)**.
2. **Required permissions:** for **public** repositories, **no scopes are needed**.
   (If you prefer fine-grained tokens: "Public Repositories (read-only)" access
   is sufficient.)
3. **Configure:** copy `backend/.env.example` to `backend/.env` and set
   `GITHUB_TOKEN=your-token-here`. Never commit `backend/.env`.
4. **Restart the backend.**

## How GitHub rate limiting is handled

- Every GitHub API response's `x-ratelimit-remaining` / `x-ratelimit-reset`
  headers are tracked; each API call is logged (method, endpoint, status,
  remaining quota — the token is never logged).
- If GitHub returns **403/429 with quota exhausted**, the backend **stops
  immediately** — no retries — and returns a useful error including when the
  quota resets. The UI shows the error with a **Retry Analysis** button.
- `GET /api/github/rate-limit` returns live quota
  (`{limit, remaining, reset, authenticated}`); the React nav shows a
  **GitHub API ● Connected** / **⚠ Rate limit low** indicator.
- An analysis costs only ~2 API calls (metadata + file tree). File contents
  come from `raw.githubusercontent.com`, which does **not** consume API quota.

## How repository caching works

- Repository metadata, file trees, and file contents are cached in the backend
  (in-memory TTL cache, 15 minutes), so re-analyzing the same repository
  doesn't repeat GitHub requests.
- **Request deduplication:** if Analyze is clicked twice for the same
  repository + issue while a scan is in flight, the second request attaches to
  the first instead of scanning again.
- Only ~15 relevant files are fetched per analysis; vendored/generated/binary
  paths (`node_modules`, `dist`, `__pycache__`, lock files, …) are excluded.

## Running Locally

```bash
# Terminal 1 — backend (from project root)
# Optional first: cp backend/.env.example backend/.env  (then set GITHUB_TOKEN)
uvicorn backend.app:app --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

Open **http://localhost:5173**. The Vite dev server proxies `/api` to the backend.

**Using an open-weight model** (example with Ollama + Llama 3.1):
```bash
ollama pull llama3.1
AI_PROVIDER=ollama OLLAMA_MODEL=llama3.1 uvicorn backend.app:app --port 8000
```

## Example

Input:
- Repo: `https://github.com/demo/miniblog` (Flask blog, no auth code)
- Issue: *"Add login page"*

Output highlights:
- Type: **Feature Request** — *"needs a brand-new file: templates/login.html doesn't exist yet"*
- ⚠️ *"Authentication infrastructure was not found in the scanned repository…"*
- Steps: create `templates/login.html` → add `/login` route in `app.py` (confirmed: it defines the app's routes) → link from `templates/index.html` → reuse `static/style.css`
- Test plan: login page loads · valid credentials · invalid credentials · empty fields

Try it offline: the landing page has **Demo: bug fix** and **Demo: feature request** buttons.

## Limitations

- Public GitHub repositories only (no auth support)
- Keyword + import heuristics: vague issues give vague results
- Very large repos are partially scanned (GitHub API limits; warns when truncated)
- The built-in engine is rule-based — subtle semantic issues may need the LLM provider
- No repository modification by design

## Future Improvements

- Tree-sitter based call-graph analysis for deeper flow tracing
- PR-diff aware plans ("what changed since this issue was filed")
- More LLM providers (llama.cpp server, HuggingFace TGI)
- Caching of analyzed repositories
- GitHub issue import via issue URL/number

## AI Model Documentation

| Provider | Model (example) | License |
|---|---|---|
| `evidence` (default) | Built-in deterministic engine (this repo's code) | MIT (this project) |
| `ollama` | Llama 3.1 (Meta) | [Llama 3.1 Community License](https://llama.meta.com/llama3_1/license/) |
| `ollama` | Qwen2.5 (Alibaba) | Apache 2.0 |

## Open Source License

MIT — see [LICENSE](LICENSE).
