// Aleph-One Risk / Opportunity Matrix
// Pure SVG — no external dependencies

(function () {
  const ROWS = [
    { ticker: 'AAPL',  sector: 'tech' },
    { ticker: 'MSFT',  sector: 'tech' },
    { ticker: 'GOOGL', sector: 'tech' },
    { ticker: 'TSLA',  sector: 'ev'   },
    { ticker: 'NVDA',  sector: 'tech' },
  ];

  const COLS = [
    { id: 'momentum',  label: 'MOMENTUM'  },
    { id: 'regime',    label: 'REGIME'    },
    { id: 'rates',     label: 'RATES'     },
    { id: 'sentiment', label: 'SENTIMENT' },
    { id: 'signal',    label: 'SIG SCORE' },
  ];

  const HDR_X = 52;    // width of row-label column
  const HDR_Y = 30;    // height of col-header row
  const CW    = 88;    // cell width
  const CH    = 52;    // cell height
  const W     = HDR_X + COLS.length * CW;
  const H     = HDR_Y + ROWS.length * CH;

  let _svg;
  let _cells = []; // [row][col] = { rect, tag }

  function _ns(tag) {
    return document.createElementNS('http://www.w3.org/2000/svg', tag);
  }

  // Deterministic pseudo-random seeded by cell coordinates
  function _prng(seed) {
    let s = (seed * 1664525 + 1013904223) & 0xffffffff;
    return ((s >>> 0) / 0xffffffff);
  }

  function _scoreCell(ri, ci, signals, regime) {
    const base = _prng((ri + 1) * 97 + (ci + 1) * 53);
    const sigList = signals?.signals || [];
    const sig = sigList[ri % Math.max(sigList.length, 1)] || {};
    const family = regime?.regime_family || 'uncertain';

    let score = base;

    if (ci === 4) {                          // SIG SCORE: use real score
      score = typeof sig.score === 'number' ? sig.score : base;
    } else if (ci === 1) {                   // REGIME FIT
      const fit = { expansion: 0.82, inflation_transition: 0.5, contraction: 0.18, uncertain: 0.4 };
      score = (fit[family] ?? 0.5) + (base - 0.5) * 0.22;
    } else if (ci === 0) {                   // MOMENTUM: from trend
      const trend = { up: 0.78, flat: 0.50, down: 0.24 };
      score = (trend[sig.trend] ?? 0.5) + (base - 0.5) * 0.28;
    } else {
      score = (sig.score ?? 0.5) * 0.38 + base * 0.62;
    }

    // Sector adjustments
    if (ROWS[ri].sector === 'tech' && ci === 2) score *= 0.87; // tech sensitive to rates
    if (ROWS[ri].ticker === 'TSLA' && ci === 3) score *= 1.13; // TSLA sentiment amplified
    if (ROWS[ri].ticker === 'NVDA' && ci === 0) score *= 1.10; // NVDA momentum bias

    score = Math.max(0, Math.min(1, score));

    let type, tag;
    if (score >= 0.70) {
      type = 'opp';
      tag  = score >= 0.85 ? '▲ ADJUST' : '▲ HOLD+';
    } else if (score <= 0.32) {
      type = 'risk';
      tag  = score <= 0.16 ? '▼ REDUCE' : '▼ WATCH';
    } else {
      type = 'neutral';
      tag  = '— STABLE';
    }
    return { score, type, tag };
  }

  function _init(svgEl) {
    _svg = svgEl;
    _svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    _svg.style.width  = '100%';
    _svg.style.height = '100%';

    // Embedded styles
    const style = _ns('style');
    style.textContent = `
      .mx-ch { font: bold 8.5px 'Space Mono','Courier New',monospace; fill: rgba(232,240,254,0.38); letter-spacing: .8px; }
      .mx-rh { font: bold 11px 'Space Mono','Courier New',monospace; fill: #00E5FF; }
      .mx-cell { stroke-width: 1; transition: fill .3s; }
      .mx-opp  { fill: rgba(0,229,255,.18);  stroke: rgba(0,229,255,.5); }
      .mx-risk { fill: rgba(191,0,255,.18);  stroke: rgba(191,0,255,.5); }
      .mx-neu  { fill: rgba(255,255,255,.04); stroke: rgba(255,255,255,.10); }
      .mx-tag  { font: 8px 'Space Mono','Courier New',monospace; }
      .mx-tag-opp  { fill: #00E5FF; }
      .mx-tag-risk { fill: #BF00FF; }
      .mx-tag-neu  { fill: rgba(232,240,254,.45); }
      @keyframes mxflash { 0%,100%{opacity:1} 45%{opacity:.18} }
      .mx-flash { animation: mxflash .55s ease; }
    `;
    _svg.appendChild(style);

    // Column headers
    COLS.forEach((col, ci) => {
      const t = _ns('text');
      t.setAttribute('x', HDR_X + ci * CW + CW / 2);
      t.setAttribute('y', HDR_Y - 8);
      t.setAttribute('text-anchor', 'middle');
      t.setAttribute('class', 'mx-ch');
      t.textContent = col.label;
      _svg.appendChild(t);
    });

    // Rows
    _cells = ROWS.map((row, ri) => {
      const cy = HDR_Y + ri * CH;

      // Row label
      const rt = _ns('text');
      rt.setAttribute('x', HDR_X - 6);
      rt.setAttribute('y', cy + CH / 2 + 4);
      rt.setAttribute('text-anchor', 'end');
      rt.setAttribute('class', 'mx-rh');
      rt.textContent = row.ticker;
      _svg.appendChild(rt);

      return COLS.map((_, ci) => {
        const cx = HDR_X + ci * CW;

        const rect = _ns('rect');
        rect.setAttribute('x', cx + 3);
        rect.setAttribute('y', cy + 3);
        rect.setAttribute('width', CW - 6);
        rect.setAttribute('height', CH - 6);
        rect.setAttribute('rx', 4);
        rect.setAttribute('class', 'mx-cell mx-neu');
        _svg.appendChild(rect);

        const tag = _ns('text');
        tag.setAttribute('x', cx + CW / 2);
        tag.setAttribute('y', cy + CH / 2 + 3);
        tag.setAttribute('text-anchor', 'middle');
        tag.setAttribute('class', 'mx-tag mx-tag-neu');
        tag.textContent = '—';
        _svg.appendChild(tag);

        return { rect, tag };
      });
    });
  }

  function _updateWithData(signals, regime) {
    if (!_cells.length) return;
    _cells.forEach((rowCells, ri) => {
      rowCells.forEach((cell, ci) => {
        const { type, tag } = _scoreCell(ri, ci, signals, regime);
        cell.rect.setAttribute('class', `mx-cell mx-${type === 'opp' ? 'opp' : type === 'risk' ? 'risk' : 'neu'}`);
        cell.tag.textContent = tag;
        cell.tag.setAttribute('class', `mx-tag mx-tag-${type === 'opp' ? 'opp' : type === 'risk' ? 'risk' : 'neu'}`);

        // Flash animation
        cell.rect.classList.add('mx-flash');
        setTimeout(() => cell.rect.classList.remove('mx-flash'), 600);
      });
    });
  }

  window.AlephRiskMatrix = { init: _init, updateWithData: _updateWithData };
}());
