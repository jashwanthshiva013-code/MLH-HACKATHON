"""GitHub REST API client — the ONLY place the GITHUB_TOKEN is used.

- Authentication happens here and only here; the token never leaves the backend.
- Required headers on every request:
    Authorization: Bearer <GITHUB_TOKEN>   (only when a token is configured)
    Accept: application/vnd.github+json
    X-GitHub-Api-Version: 2026-03-10
- File contents are fetched via raw.githubusercontent.com, which does NOT
  consume API rate quota — so an analysis costs ~2 API calls, not one per file.
- Every API response updates the tracked rate-limit state (used by
  GET /api/github/rate-limit). On 403/429 with quota exhausted the client
  stops immediately — no retries — and raises a user-friendly error.
- Every API call is logged (method, endpoint, status, remaining quota).
  The token is NEVER logged.
"""
import logging
import os
import re
import threading
from datetime import datetime, timezone

import requests

from .cache import content_cache, meta_cache, tree_cache

logger = logging.getLogger("contribguide.github")

API_BASE = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"
API_VERSION = "2026-03-10"

MAX_FILE_BYTES = 100_000


class RepoFetchError(Exception):
    """A user-facing repository fetch failure (carries an HTTP status)."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.message = message
        self.status = status


# Last-seen rate-limit state (from response headers), for the status endpoint.
_rl_lock = threading.Lock()
_LAST_SEEN = {"limit": None, "remaining": None, "reset": None,
              "authenticated": False}


def _token():
    return os.getenv("GITHUB_TOKEN", "").strip()


def _headers():
    headers = {
        "User-Agent": "ContribGuide-AI/1.0",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_reset(epoch):
    epoch = _int_or_none(epoch)
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _update_rate_limit(resp):
    with _rl_lock:
        _LAST_SEEN.update({
            "limit": _int_or_none(resp.headers.get("x-ratelimit-limit")),
            "remaining": _int_or_none(resp.headers.get("x-ratelimit-remaining")),
            "reset": _format_reset(resp.headers.get("x-ratelimit-reset")),
            "authenticated": bool(_token()),
        })


def _log_api_call(method, label, status, remaining):
    # The token is never logged — only method/endpoint/status/quota.
    logger.info("GitHub API %s %s -> %s | remaining=%s",
                method, label, status, remaining)


def _rate_limit_error(resp):
    remaining = resp.headers.get("x-ratelimit-remaining")
    reset_epoch = resp.headers.get("x-ratelimit-reset")
    retry_after = resp.headers.get("retry-after")
    reset_at = _format_reset(reset_epoch) or "unknown time"
    message = ("GitHub API rate limit exceeded "
               f"(remaining: {remaining or '0'}). Quota resets at {reset_at}.")
    if retry_after:
        message += f" Retry after {retry_after}s."
    if not _token():
        message += (" Set GITHUB_TOKEN in backend/.env for 5,000 requests/hour "
                    "instead of 60.")
    return RepoFetchError(message, 429)


def _get(url, label):
    """GET against api.github.com with rate-limit handling and logging."""
    try:
        resp = requests.get(url, headers=_headers(), timeout=20)
    except requests.RequestException as exc:
        raise RepoFetchError(
            f"Couldn't reach GitHub ({exc}). Check your internet connection.", 502)
    _update_rate_limit(resp)
    _log_api_call("GET", label, resp.status_code,
                  resp.headers.get("x-ratelimit-remaining"))

    if resp.status_code == 404:
        raise RepoFetchError(
            "Repository not found. Check the URL and make sure the repository "
            "is public.", 404)
    if resp.status_code in (403, 429):
        if resp.headers.get("x-ratelimit-remaining") == "0" \
                or resp.status_code == 429:
            # Quota exhausted: stop immediately, no retries.
            raise _rate_limit_error(resp)
        raise RepoFetchError(
            "Repository not accessible (GitHub returned HTTP 403). "
            "Private repositories are not supported.", 403)
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        raise RepoFetchError(
            f"GitHub returned an unexpected error ({resp.status_code}).", 502)
    return resp


def parse_repo_url(url):
    match = re.search(r"github\.com/([^/]+)/([^/\s?#]+)", (url or "").strip())
    if not match:
        return None
    return match.group(1), re.sub(r"\.git$", "", match.group(2))


def get_repo_meta(owner, repo):
    """Repository metadata (cached)."""
    def load():
        return _get(f"{API_BASE}/repos/{owner}/{repo}",
                    f"repos/{owner}/{repo}").json()
    return meta_cache.get_or_load(("meta", owner, repo), load)


def get_file_tree(owner, repo, branch):
    """Full blob path list + truncated flag (cached). Unfiltered."""
    def load():
        data = _get(
            f"{API_BASE}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1",
            f"repos/{owner}/{repo}/git/trees/{branch}?recursive=1").json()
        paths = [n["path"] for n in data.get("tree", [])
                 if n.get("type") == "blob"]
        return paths, data.get("truncated", False)
    return tree_cache.get_or_load(("tree", owner, repo, branch), load)


def get_file_content(owner, repo, path, branch):
    """Raw file text (cached). Raw fetches don't consume API quota."""
    def load():
        try:
            resp = requests.get(
                f"{RAW_BASE}/{owner}/{repo}/{branch}/{path}",
                headers=_headers(), timeout=20)
        except requests.RequestException:
            return ""
        if resp.status_code == 404:
            return ""
        return resp.text[:MAX_FILE_BYTES] if resp.ok else ""
    return content_cache.get_or_load(("content", owner, repo, branch, path), load)


def get_rate_limit_status():
    """Live quota info for GET /api/github/rate-limit. Never exposes the token."""
    try:
        resp = _get(f"{API_BASE}/rate_limit", "rate_limit")
        core = resp.json().get("resources", {}).get("core", {})
        return {
            "limit": core.get("limit"),
            "remaining": core.get("remaining"),
            "reset": _format_reset(core.get("reset")),
            "authenticated": bool(_token()),
        }
    except RepoFetchError:
        pass
    with _rl_lock:
        seen = dict(_LAST_SEEN)
    if seen["limit"] is None:
        seen["limit"] = 5000 if seen["authenticated"] else 60
    return seen
