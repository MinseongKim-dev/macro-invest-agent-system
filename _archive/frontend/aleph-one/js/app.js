// Aleph-One — main orchestration
// Loads data from FastAPI backend, falls back to demo data, drives all visual modules

(function () {

  // ── Demo / fallback data ────────────────────────────────────────────────
  const DEMO = {
    regime: {
      regime_label: 'goldilocks',
      regime_family: 'expansion',
      confidence: 'high',
      as_of_date: '2026-05-20',
      freshness_status: 'fresh',
      degraded_status: false,
      transition: { transition_type: 'continuation', changed: false },
      missing_inputs: [],
    },
    signals: {
      run_id: 'demo-001',
      strongest_signal_id: 'tech_growth',
      signals: [
        { signal_id: 'tech_growth',      signal_type: 'buy',  strength: 'strong', score: 0.85, trend: 'up'   },
        { signal_id: 'equity_momentum',  signal_type: 'buy',  strength: 'strong', score: 0.78, trend: 'up'   },
        { signal_id: 'rate_sensitivity', signal_type: 'sell', strength: 'medium', score: 0.42, trend: 'down' },
        { signal_id: 'inflation_hedge',  signal_type: 'hold', strength: 'weak',   score: 0.51, trend: 'flat' },
        { signal_id: 'defensive_rot',    signal_type: 'sell', strength: 'weak',   score: 0.33, trend: 'down' },
      ],
      trust: { freshness_status: 'fresh', availability: 'full', is_degraded: false, sources: [] },
    },
    snapshot: {
      trust: { freshness_status: 'fresh', availability: 'full', is_degraded: false, sources: [{ source_label: 'FRED' }] },
      features: [],
    },
    events: {
      events: [
        { event_type: 'FED_DECISION', region: 'US', title: 'Fed holds at 4.5% — signals 2 cuts in H2 2026'       },
        { event_type: 'GDP_RELEASE',  region: 'US', title: 'US Q1 GDP revised up to 2.8% annualized'             },
        { event_type: 'CPI_RELEASE',  region: 'US', title: 'CPI cools to 2.3% YoY · Core PCE at 2.7%'           },
        { event_type: 'ECB_MEETING',  region: 'EU', title: 'ECB cuts 25bps · signals gradual easing path'        },
        { event_type: 'TRADE_DATA',   region: 'CN', title: 'China trade surplus narrows on easing domestic demand'},
      ],
    },
  };

  // ── Regime color map ────────────────────────────────────────────────────
  const REGIME_COLOR = {
    goldilocks:             '#00E5FF',
    expansion:              '#00E5FF',
    disinflation:           '#00BFFF',
    reflation:              '#FFB800',
    slowdown:               '#FF8C00',
    stagflation_risk:       '#FF6B35',
    contraction:            '#FF4455',
    policy_tightening_drag: '#BF00FF',
    mixed:                  'rgba(232,240,254,0.6)',
    unclear:                'rgba(232,240,254,0.5)',
  };

  function _color(label) { return REGIME_COLOR[label] || REGIME_COLOR.unclear; }

  // ── Helpers ─────────────────────────────────────────────────────────────
  function _el(id) { return document.getElementById(id); }

  function _setText(id, text) {
    const el = _el(id);
    if (el) el.textContent = text;
  }

  function _setColor(id, color) {
    const el = _el(id);
    if (el) {
      el.style.color      = color;
      el.style.textShadow = `0 0 10px ${color}`;
    }
  }

  // ── Health score ────────────────────────────────────────────────────────
  function _health(snapshot) {
    let s = 0;
    const t = snapshot?.trust;
    if (!t) return 55;
    if (t.freshness_status === 'fresh')      s += 40;
    else if (t.freshness_status === 'stale') s += 18;
    if (t.availability === 'full')           s += 30;
    else if (t.availability === 'partial')   s += 14;
    if (!t.is_degraded)                      s += 30;
    return Math.min(s, 100);
  }

  // ── Render: regime ──────────────────────────────────────────────────────
  function _renderRegime(regime) {
    const label  = (regime.regime_label  || 'unknown').toUpperCase();
    const family = (regime.regime_family || '').toUpperCase();
    const color  = _color(regime.regime_label);
    const conf   = regime.confidence ? String(regime.confidence).toUpperCase() : '';

    _setText('regime-badge', label);
    _setColor('regime-badge', color);
    _setText('regime-family', family);

    _setText('alpha-regime-value', label);
    _setColor('alpha-regime-value', color);
    _setText('alpha-regime-family', family + (conf ? ` · CONF: ${conf}` : ''));
  }

  // ── Render: signals ─────────────────────────────────────────────────────
  function _renderSignals(signals) {
    const list = signals?.signals || [];
    const ul   = _el('alpha-signals-list');
    if (!ul) return;

    ul.innerHTML = '';
    list.slice(0, 5).forEach(sig => {
      const type  = sig.signal_type || 'hold';
      const score = typeof sig.score === 'number' ? `${Math.round(sig.score * 100)}%` : '—';
      const arrow = { up: '▲', down: '▼', flat: '—' }[sig.trend] || '—';
      const li    = document.createElement('li');
      li.className = 'signal-item';
      li.innerHTML =
        `<span class="signal-type signal-type--${type}">${type.toUpperCase()}</span>` +
        `<span>${(sig.signal_id || '').replace(/_/g, ' ')}</span>` +
        `<span class="signal-score">${arrow} ${score}</span>`;
      ul.appendChild(li);
    });
  }

  // ── Render: health / confidence ─────────────────────────────────────────
  function _renderHealth(snapshot) {
    const score = _health(snapshot);
    const healthEl = _el('alpha-health-value');
    const subEl    = _el('alpha-health-sub');
    const confEl   = _el('alpha-confidence');
    const fillEl   = _el('alpha-confidence-fill');

    const color = score >= 70 ? '#00E5FF' : score >= 40 ? '#FFB800' : '#FF4455';

    if (healthEl) {
      healthEl.textContent = String(score);
      healthEl.style.color = color;
      healthEl.style.textShadow = `0 0 10px ${color}`;
    }
    if (subEl) {
      const t    = snapshot?.trust;
      const srcs = (t?.sources || []).map(s => s.source_label || s.source_id).filter(Boolean);
      subEl.textContent = srcs.length ? `SRC: ${srcs.join(', ')}` : `${t?.freshness_status || 'unknown'}`;
    }
    if (confEl) {
      confEl.textContent = `${score}%`;
      confEl.style.color = color;
    }
    if (fillEl) fillEl.style.width = `${score}%`;
  }

  // ── Scan animation (on Analyze) ─────────────────────────────────────────
  function _scan() {
    const line    = _el('scan-line');
    const statusEl = _el('response-status');
    const tsEl    = _el('response-timestamp');

    if (line) {
      line.classList.remove('active');
      void line.offsetWidth;           // force reflow to restart animation
      line.classList.add('active');
    }
    if (statusEl) {
      statusEl.className   = 'response-status status--scanning';
      statusEl.textContent = 'SCANNING';
      setTimeout(() => {
        statusEl.className   = 'response-status status--complete';
        statusEl.textContent = 'COMPLETE';
        setTimeout(() => {
          statusEl.className   = 'response-status status--ready';
          statusEl.textContent = 'READY';
        }, 3200);
      }, 950);
    }
    if (tsEl) {
      const d = new Date();
      tsEl.textContent = d.toUTCString().slice(5, 25) + ' UTC';
    }
  }

  // ── Data state ───────────────────────────────────────────────────────────
  let _signals  = null;
  let _snapshot = null;
  let _regime   = null;

  // ── Load functions ───────────────────────────────────────────────────────
  async function _loadRegime() {
    const { data } = await AlephAPI.regime();
    _regime = data || DEMO.regime;
    _renderRegime(_regime);
  }

  async function _loadSignals() {
    const { data } = await AlephAPI.signals();
    _signals = data || DEMO.signals;
    _renderSignals(_signals);
    if (typeof AlephNetworkMap !== 'undefined') AlephNetworkMap.updateWithSignals(_signals);
    _maybeUpdateMatrix();
  }

  async function _loadSnapshot() {
    const { data } = await AlephAPI.snapshots();
    _snapshot = data || DEMO.snapshot;
    _renderHealth(_snapshot);
    _maybeUpdateMatrix();
  }

  async function _loadEvents() {
    const { data } = await AlephAPI.events();
    const evts = data || DEMO.events;
    if (typeof AlephWorldMap !== 'undefined') AlephWorldMap.updateWithEvents(evts);
  }

  function _maybeUpdateMatrix() {
    if (_signals && typeof AlephRiskMatrix !== 'undefined') {
      AlephRiskMatrix.updateWithData(_signals, _regime);
    }
  }

  // ── Clock ────────────────────────────────────────────────────────────────
  function _startClock() {
    const el = _el('clock');
    if (!el) return;
    const tick = () => {
      const n = new Date();
      const p = v => String(v).padStart(2, '0');
      el.textContent = `${p(n.getUTCHours())}:${p(n.getUTCMinutes())}:${p(n.getUTCSeconds())} UTC`;
    };
    tick();
    setInterval(tick, 1000);
  }

  // ── Terminal wiring ──────────────────────────────────────────────────────
  function _initTerminal() {
    const btn   = _el('analyze-btn');
    const input = _el('command-input');

    const onAnalyze = () => {
      _scan();
      Promise.allSettled([_loadSignals(), _loadRegime(), _loadEvents()]);
    };

    if (btn)   btn.addEventListener('click', onAnalyze);
    if (input) input.addEventListener('keydown', e => { if (e.key === 'Enter') onAnalyze(); });
  }

  // ── Bootstrap ────────────────────────────────────────────────────────────
  async function _boot() {
    // Initialize visual modules first
    const netCanvas = _el('network-canvas');
    const matSvg    = _el('risk-matrix-svg');
    const worldSvg  = _el('world-map-svg');
    const tickerEl  = _el('ticker-content');

    if (netCanvas && typeof AlephNetworkMap !== 'undefined') AlephNetworkMap.init(netCanvas);
    if (matSvg    && typeof AlephRiskMatrix  !== 'undefined') AlephRiskMatrix.init(matSvg);
    if (worldSvg  && typeof AlephWorldMap    !== 'undefined') AlephWorldMap.init(worldSvg, tickerEl);

    _initTerminal();
    _startClock();

    // Load all data in parallel (with demo fallbacks)
    await Promise.allSettled([_loadRegime(), _loadSignals(), _loadSnapshot(), _loadEvents()]);

    // Trigger welcome scan animation
    setTimeout(_scan, 1400);

    // Refresh data every 60 s
    setInterval(() => {
      Promise.allSettled([_loadRegime(), _loadSignals(), _loadSnapshot(), _loadEvents()]);
    }, 60_000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _boot);
  } else {
    _boot();
  }

}());
