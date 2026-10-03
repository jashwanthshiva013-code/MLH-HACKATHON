"""AI provider interface.

    analyze_repository_issue(repository_context, issue) -> plan dict

Providers (selected with the AI_PROVIDER environment variable):

  evidence            Built-in deterministic evidence engine. Default.
                      Works offline, no API key, fully transparent.

  ollama              Open-weight model served locally by Ollama
                      (e.g. llama3.1, qwen2.5). Set OLLAMA_MODEL.

  openai_compatible   Any OpenAI-compatible chat-completions endpoint
                      (vLLM, LM Studio, Together, OpenRouter, ...).
                      Set OPENAI_COMPAT_URL / OPENAI_COMPAT_KEY /
                      OPENAI_COMPAT_MODEL.

The LLM providers receive ONLY the compact, evidence-backed repository
context (file paths, matched snippets, import relationships) — never the
whole repo — plus a strict grounding prompt. Their JSON output is
validated before it is returned; invalid output raises AIProviderError
instead of being passed to the frontend.
"""
import json
import os
import re

import requests


class AIProviderError(Exception):
    pass


SYSTEM_PROMPT = """You are ContribGuide AI, an evidence-grounded open-source contribution guide.
You NEVER modify code. You guide a developer step by step.

STRICT GROUNDING RULES:
- Recommend ONLY files, functions, routes, and relationships present in the
  repository context below. Do not invent any.
- If the issue needs something the repository does not have (e.g. authentication
  code), say "Authentication infrastructure was not found in the scanned repository."
  and treat it as a new feature.
- If you are unsure about something, mark it "Likely, but not confirmed".
- Do NOT give generic programming advice; every step must reference the repo.

Return ONLY valid JSON with exactly this structure:
{
  "issue_understanding": {"title": "...", "description": "...",
    "type": "bug|feature|enhancement|documentation|unknown", "explanation": "..."},
  "repository_overview": {"name": "...", "language": "...", "files_scanned": 0,
    "folders": [], "framework": "..."},
  "relevant_files": [{"path": "...", "reason": "...",
    "evidence": [{"line": 1, "text": "..."}], "evidence_summary": "...",
    "confidence": "high|medium|low"}],
  "flow": ["..."],
  "flow_note": "...",
  "starting_point": {"file": "...", "reason": "..."},
  "steps": [{"text": "...", "basis": "confirmed|suggestion"}],
  "tests": {"existing": [], "suggested": [], "note": "..."},
  "risks": [{"area": "...", "basis": "confirmed|suggestion"}],
  "learning": {"topics": [], "reading_order": []},
  "warnings": []
}
Mark each step's "basis" as "confirmed" when it rests on repository evidence,
"suggestion" when it is your proposal.
"""


def _compact_context(repository_context, max_chars=12000):
    files = repository_context.get("files", [])
    contents = repository_context.get("contents", {})
    top = repository_context.get("top_files") or []
    lines = [f"Repository: {repository_context.get('name', '')}",
             f"Files in tree: {len(files)}",
             "Relevant files (with matched snippets):"]
    for entry in top[:8]:
        path = entry["path"]
        lines.append(f"\n### {path}")
        for ev in entry.get("evidence", [])[:3]:
            lines.append(f"  L{ev['line']}: {ev['text']}")
    flow = repository_context.get("flow") or []
    if flow:
        lines.append("\nImport relationships found: " + " -> ".join(flow))
    text = "\n".join(lines)
    return text[:max_chars]


def _call_chat_completions(url, headers, model, system, user, timeout=120):
    try:
        resp = requests.post(
            url.rstrip("/") + "/chat/completions",
            headers=headers,
            json={"model": model, "temperature": 0.2,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]},
            timeout=timeout)
    except requests.RequestException as exc:
        raise AIProviderError(f"Could not reach the AI model ({exc}). "
                              "Is the endpoint running and AI_PROVIDER configured?")
    if resp.status_code != 200:
        raise AIProviderError(
            f"AI model returned HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise AIProviderError("AI model returned an unexpected response shape.")


def _extract_json(raw):
    """Pull the JSON object out of a model reply (tolerates code fences)."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise AIProviderError("AI model did not return JSON.")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise AIProviderError(f"AI model returned invalid JSON ({exc}).")


def _llm_analyze(provider, repository_context, issue):
    context = _compact_context(repository_context)
    user = (f"ISSUE TITLE: {issue.get('title', '')}\n"
            f"ISSUE DESCRIPTION: {issue.get('description', '')}\n\n"
            f"REPOSITORY CONTEXT:\n{context}\n\n"
            "Generate the contribution plan as JSON.")
    if provider == "ollama":
        url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.1")
        headers = {"Content-Type": "application/json"}
        label = f"{model} via Ollama (open-weight)"
    else:
        url = os.getenv("OPENAI_COMPAT_URL", "")
        # AI_API_KEY is accepted as an alias for the key.
        key = os.getenv("OPENAI_COMPAT_KEY", "") or os.getenv("AI_API_KEY", "")
        model = os.getenv("OPENAI_COMPAT_MODEL", "")
        if not url or not model:
            raise AIProviderError(
                "OPENAI_COMPAT_URL and OPENAI_COMPAT_MODEL must be set for "
                "AI_PROVIDER=openai_compatible.")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        label = f"{model} via OpenAI-compatible endpoint"
    raw = _call_chat_completions(url, headers, model, SYSTEM_PROMPT, user)
    plan = _extract_json(raw)
    plan["generated_by"] = label
    # The FastAPI layer validates this against the ContributionPlan schema.
    return plan


def analyze_repository_issue(repository_context, issue, provider=None):
    """Main entry point. Returns a plan dict (validated by the caller)."""
    provider = (provider or os.getenv("AI_PROVIDER", "evidence")).strip().lower()
    if provider == "evidence":
        from . import evidence_engine
        return evidence_engine.build_plan(
            repository_context, issue.get("title", ""),
            issue.get("description", ""))
    if provider in ("ollama", "openai_compatible", "openai"):
        return _llm_analyze(provider, repository_context, issue)
    raise AIProviderError(
        f"Unknown AI_PROVIDER={provider!r}. Use 'evidence', 'ollama' or "
        "'openai_compatible'.")


def answer_followup(plan, question, provider=None):
    """Answer a 'Refine plan' follow-up using repository context."""
    provider = (provider or os.getenv("AI_PROVIDER", "evidence")).strip().lower()
    if provider == "evidence":
        from . import evidence_engine
        return evidence_engine.refine_answer(plan, question)
    # LLM path: answer from the plan's grounded context.
    summary = json.dumps({
        "issue": plan.get("issue_understanding"),
        "relevant_files": plan.get("relevant_files"),
        "steps": plan.get("steps"),
        "tests": plan.get("tests"),
    })[:6000]
    system = ("You are ContribGuide AI. Answer the developer's follow-up question "
              "using ONLY the contribution-plan context below. Stay grounded; "
              "if unsure, say so. Keep the answer concise.")
    if provider == "ollama":
        url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.1")
        headers = {"Content-Type": "application/json"}
    else:
        url = os.getenv("OPENAI_COMPAT_URL", "")
        # AI_API_KEY is accepted as an alias for the key.
        key = os.getenv("OPENAI_COMPAT_KEY", "") or os.getenv("AI_API_KEY", "")
        model = os.getenv("OPENAI_COMPAT_MODEL", "")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
    raw = _call_chat_completions(
        url, headers, model, system,
        f"PLAN CONTEXT:\n{summary}\n\nQUESTION: {question}")
    return raw.strip()
