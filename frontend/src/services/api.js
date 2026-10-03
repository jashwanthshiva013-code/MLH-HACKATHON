// Thin client for the FastAPI backend (proxied via vite.config.js).

async function handle(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return data;
}

export function analyzeRepo({ repo_url, issue_title, issue_description }) {
  return fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_url, issue_title, issue_description }),
  }).then(handle);
}

export function refinePlan(plan, question) {
  return fetch('/api/refine', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan, question }),
  }).then(handle);
}

export function getDemo(name) {
  return fetch(`/api/demo/${name}`).then(handle);
}

export function getHealth() {
  return fetch('/api/health').then(handle);
}

export function getRateLimit() {
  return fetch('/api/github/rate-limit').then(handle);
}
