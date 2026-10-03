import { useEffect, useState } from 'react';
import { getRateLimit } from '../services/api.js';

// Small GitHub API quota indicator. The token itself always stays in the
// backend — this only shows the quota state returned by /api/github/rate-limit.
export default function RateLimitPill() {
  const [state, setState] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const s = await getRateLimit();
        if (alive) setState(s);
      } catch {
        /* leave the pill hidden if the backend is unreachable */
      }
    };
    load();
    const timer = setInterval(load, 60000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  if (!state) return null;
  const { authenticated, remaining, limit } = state;
  const low =
    remaining != null &&
    (remaining < 100 || (limit && remaining < limit * 0.05));

  const text = low
    ? `GitHub API ⚠ Rate limit low (${remaining} left)`
    : authenticated
      ? 'GitHub API ● Connected'
      : 'GitHub API ● Public (60/hr)';
  const cls = low ? 'rlp rlp-warn' : 'rlp rlp-ok';
  const title = authenticated
    ? `Authenticated · ${remaining ?? '?'} of ${limit ?? '?'} requests remaining`
    : 'Unauthenticated · 60 requests/hour. The app operator can add a GITHUB_TOKEN in backend/.env for 5,000/hour.';

  return (
    <span className={cls} title={title}>
      {text}
    </span>
  );
}
