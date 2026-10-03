"""ContribGuide AI backend — FastAPI.

Routes:
  GET  /api/health              service + provider status
  GET  /api/github/rate-limit   live GitHub API quota (never exposes the token)
  POST /api/analyze             {repo_url, issue_title, issue_description} -> plan
  POST /api/refine              {plan, question} -> {answer}
  GET  /api/demo/bug            offline demo: token-expiry bug (repo WITH auth code)
  GET  /api/demo/feature        offline demo: "add login page" (repo WITHOUT auth)

Configuration lives in backend/.env (see backend/.env.example).
The GITHUB_TOKEN is used only here, in the backend — never sent to the frontend.

Every plan is validated against the ContributionPlan schema before it is
returned — the frontend never receives unvalidated AI output. If repository
analysis fails, the failure is reported honestly; no fake results are generated.
"""
import asyncio
import hashlib
import json
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from . import ai_service, github_client, repository_analyzer
from .models import ContributionPlan

# Load backend/.env (GITHUB_TOKEN etc.) — kept out of version control.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("contribguide.app")

app = FastAPI(title="ContribGuide AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    repo_url: str
    issue_title: str
    issue_description: str = ""


class RefineRequest(BaseModel):
    plan: dict
    question: str


# ------------------------------------------------------------------ dedup
# Identical concurrent analyses share one in-flight task instead of
# scanning the repository twice.
_inflight: dict[str, asyncio.Task] = {}
_inflight_lock = asyncio.Lock()


def _fingerprint(req: AnalyzeRequest) -> str:
    h = hashlib.sha256()
    h.update(req.repo_url.strip().lower().encode())
    h.update(b"\x00" + req.issue_title.strip().encode())
    h.update(b"\x00" + req.issue_description.strip().encode())
    return h.hexdigest()


def _run_analysis_sync(req: AnalyzeRequest) -> dict:
    repo_data = repository_analyzer.scan_repository(
        req.repo_url, req.issue_title + "\n" + req.issue_description)
    plan = ai_service.analyze_repository_issue(
        repo_data,
        {"title": req.issue_title.strip(),
         "description": req.issue_description.strip()})
    return plan


def _validate(plan: dict) -> dict:
    try:
        return ContributionPlan.model_validate(plan).model_dump()
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail="The AI returned a plan that failed validation. "
                   "No unvalidated output is sent to the frontend. "
                   f"({exc})")


@app.get("/api/health")
def health():
    return {"status": "ok",
            "ai_provider": os.getenv("AI_PROVIDER", "evidence")}


@app.get("/api/github/rate-limit")
async def github_rate_limit():
    """Live GitHub API quota. The token itself is never exposed."""
    status = await asyncio.to_thread(github_client.get_rate_limit_status)
    return status


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    if not req.repo_url.strip() or not req.issue_title.strip():
        raise HTTPException(
            status_code=422,
            detail="Please provide both a GitHub repository URL and an issue description.")
    key = _fingerprint(req)
    async with _inflight_lock:
        task = _inflight.get(key)
        if task is None or task.done():
            task = asyncio.create_task(asyncio.to_thread(_run_analysis_sync, req))
            _inflight[key] = task
            task.add_done_callback(lambda t: _inflight.pop(key, None))
        else:
            logger.info("Deduplicated identical analysis request (already in flight).")
    try:
        plan = await task
    except github_client.RepoFetchError as exc:
        # Repository could not be analyzed — report honestly, no fake results.
        raise HTTPException(status_code=exc.status, detail=exc.message)
    except ai_service.AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return _validate(plan)


@app.post("/api/refine")
def refine(req: RefineRequest):
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="Please type a question.")
    try:
        answer = ai_service.answer_followup(req.plan, req.question.strip())
    except ai_service.AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"answer": answer}


def _demo_fixture(filename):
    path = os.path.join(BASE_DIR, "demo_fixtures", filename)
    with open(path, encoding="utf-8") as f:
        demo = json.load(f)
    return {
        "name": demo["repo"] + " (demo)",
        "files": [e["path"] for e in demo["files"]],
        "contents": {e["path"]: e["content"] for e in demo["files"]},
        "truncated": False,
        "issue": demo["issue"],
    }


@app.get("/api/demo/bug")
def demo_bug():
    demo = _demo_fixture("repo.json")
    plan = ai_service.analyze_repository_issue(
        demo, {"title": demo["issue"]["title"],
               "description": demo["issue"]["body"]},
        provider="evidence")
    return _validate(plan)


@app.get("/api/demo/feature")
def demo_feature():
    demo = _demo_fixture("repo2.json")
    plan = ai_service.analyze_repository_issue(
        demo, {"title": demo["issue"]["title"],
               "description": demo["issue"]["body"]},
        provider="evidence")
    return _validate(plan)
