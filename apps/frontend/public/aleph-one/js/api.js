/* api.js — Aleph-One API client
 * Wraps all backend endpoints. BASE auto-detects: same-origin /api when hosted,
 * localhost:8000/api when opened as file://.
 */

const BASE = (() => {
  if (location.protocol === 'file:') return 'http://localhost:8000/api';
  return '/api';
})();

async function fetchJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json();
}

const api = {
  intelligence: () => fetchJson(`${BASE}/v1/intelligence/stream`),
  regime:       () => fetchJson(`${BASE}/v1/regimes/latest`),
  events:       () => fetchJson(`${BASE}/v1/events/recent`),
  command:      (query) => fetch(`${BASE}/v1/intelligence/command`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ query }),
  }).then(r => r.json()),
};
