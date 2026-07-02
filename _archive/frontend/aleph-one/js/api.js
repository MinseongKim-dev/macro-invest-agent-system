// Aleph-One API client
// All functions return { data, error } — UI never crashes on backend failure

const API_BASE = '/api';

async function _fetchJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

async function _safe(fn) {
  try {
    return { data: await fn(), error: null };
  } catch (err) {
    return { data: null, error: err.message };
  }
}

const AlephAPI = {
  snapshots: (country = 'US') =>
    _safe(() => _fetchJson(`${API_BASE}/snapshots/latest?country=${country}`)),
  signals: (country = 'US') =>
    _safe(() => _fetchJson(`${API_BASE}/signals/latest?country=${country}`)),
  regime: () =>
    _safe(() => _fetchJson(`${API_BASE}/regimes/latest`)),
  regimeCompare: () =>
    _safe(() => _fetchJson(`${API_BASE}/regimes/compare`)),
  events: (limit = 30) =>
    _safe(() => _fetchJson(`${API_BASE}/events/recent?limit=${limit}`)),
  alerts: (limit = 20) =>
    _safe(() => _fetchJson(`${API_BASE}/alerts/recent?limit=${limit}`)),
};

window.AlephAPI = AlephAPI;
