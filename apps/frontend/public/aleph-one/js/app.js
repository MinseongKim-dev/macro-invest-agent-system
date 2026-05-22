/* app.js — Aleph-One orchestration */

let networkMap  = null;
let riskMatrix  = null;
let worldMapCtl = null;

/* ── Clock ────────────────────────────────────────────────────────────────── */
function startClock() {
  const el = document.getElementById('clock');
  function tick() {
    const now = new Date();
    el.textContent = now.toUTCString().slice(17, 25) + ' UTC';
  }
  tick();
  setInterval(tick, 1000);
}

/* ── Status Bar ───────────────────────────────────────────────────────────── */
function updateStatusBar(data) {
  const badge = document.getElementById('regime-badge');
  if (!badge) return;
  const regime = data?.macro_regime?.regime_name || 'UNKNOWN';
  badge.textContent = regime;
  badge.style.borderColor = regimeColor(regime);
  badge.style.color       = regimeColor(regime);
  badge.style.textShadow  = `0 0 6px ${regimeColor(regime)}`;
}

function regimeColor(name) {
  if (!name) return '#00E5FF';
  const n = name.toUpperCase();
  if (n.includes('EXPAN') || n.includes('REFLAT')) return '#00FF88';
  if (n.includes('TIGHT') || n.includes('STAG'))   return '#FF9900';
  if (n.includes('RISK_OFF') || n.includes('CONT')) return '#FF3366';
  return '#00E5FF';
}

/* ── Personal Alpha Panel ─────────────────────────────────────────────────── */
function updateAlphaPanel(data) {
  // Health score from portfolio_health
  const health = data?.portfolio_health?.score ?? null;
  const healthEl = document.getElementById('alpha-health-value');
  if (healthEl) {
    const score = health !== null ? Math.round(health) : '—';
    healthEl.textContent = health !== null ? `${score}` : '—';

    // Arc animation: stroke-dashoffset 141 → 0 for 100%
    const arc = document.getElementById('health-arc-path');
    if (arc && health !== null) {
      const offset = 141 - (health / 100) * 141;
      arc.style.strokeDashoffset = offset;
      const c = health > 70 ? '#00FF88' : health > 40 ? '#00E5FF' : '#FF3366';
      arc.setAttribute('stroke', c);
    }
  }

  // Macro regime
  const regimeEl = document.getElementById('alpha-regime-value');
  if (regimeEl) {
    const r = data?.macro_regime;
    if (r) {
      const col = regimeColor(r.regime_name);
      regimeEl.textContent = r.regime_name || '—';
      regimeEl.style.color      = col;
      regimeEl.style.textShadow = `0 0 8px ${col}`;
    }
  }

  // Top signals from active_signals
  const sigList = document.getElementById('alpha-signals-list');
  if (sigList) {
    sigList.innerHTML = '';
    const signals = data?.active_signals || [];
    signals.slice(0, 4).forEach(sig => {
      const span = document.createElement('span');
      span.className = `signal-badge ${(sig.action || '').toLowerCase()}`;
      span.textContent = `${sig.action} · ${sig.strategy || ''}`;
      sigList.appendChild(span);
    });
  }
}

/* ── Command Terminal ─────────────────────────────────────────────────────── */
function wireTerminal() {
  const btn   = document.getElementById('analyze-btn');
  const input = document.getElementById('command-input');
  const card  = document.getElementById('response-card');

  async function runCommand() {
    const query = input.value.trim();
    if (!query) return;

    card.classList.add('scanning');
    setTimeout(() => card.classList.remove('scanning'), 800);

    try {
      await api.command(query);
    } catch (_) {
      // Terminal still shows scan animation even if offline
    }
  }

  btn.addEventListener('click', runCommand);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') runCommand(); });
}

/* ── Boot ─────────────────────────────────────────────────────────────────── */
async function boot() {
  startClock();
  wireTerminal();

  // Attempt live data; fall back to sensible defaults so UI renders offline
  let intelligenceData = null;
  let eventsData = null;

  try {
    intelligenceData = await api.intelligence();
  } catch (e) {
    console.warn('Intelligence API unavailable:', e.message);
  }

  try {
    const evts = await api.events();
    eventsData = Array.isArray(evts) ? evts : (evts?.events || []);
  } catch (e) {
    console.warn('Events API unavailable:', e.message);
  }

  // Status bar + Personal Alpha
  updateStatusBar(intelligenceData);
  updateAlphaPanel(intelligenceData);

  // 3D Network Map
  const canvas = document.getElementById('network-canvas');
  if (canvas && typeof THREE !== 'undefined') {
    const networkNodes = intelligenceData?.intelligence_synthesis?.network_nodes || null;
    networkMap = initNetworkMap(canvas, networkNodes);
  }

  // Risk Matrix
  const matrixSvg = document.getElementById('risk-matrix-svg');
  if (matrixSvg) {
    riskMatrix = initRiskMatrix(matrixSvg, intelligenceData);
  }

  // World Map + Ticker
  const mapSvg = document.getElementById('world-map-svg');
  if (mapSvg) {
    worldMapCtl = initWorldMap(mapSvg, eventsData || []);
  }
  updateTicker(eventsData || []);

  // Poll for live updates every 5 s
  setInterval(async () => {
    try {
      const d = await api.intelligence();
      updateStatusBar(d);
      updateAlphaPanel(d);
      if (riskMatrix) riskMatrix.update(d);
      if (networkMap)  networkMap.update(d?.intelligence_synthesis?.network_nodes);
    } catch (_) { /* silent — stale data is fine */ }
  }, 5000);
}

boot().catch(console.error);
