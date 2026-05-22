/* risk-matrix.js — SVG Risk/Opportunity Matrix */

const MATRIX_TICKERS = ['AAPL', 'MSFT', 'TSLA', '005930', '000660'];
const MATRIX_COLS    = ['Momentum', 'Regime', 'Rates', 'Sentiment', 'Signal'];

function seededRand(seed) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) & 0xffffffff;
    return (s >>> 0) / 0xffffffff;
  };
}

function lerpColor(t) {
  // purple (risk) → cyan (opportunity)
  const r = Math.round(191 * (1 - t));
  const g = Math.round(229 * t);
  const b = 255;
  return `rgba(${r},${g},${b},${0.25 + t * 0.35})`;
}

function statusToScore(status) {
  if (!status) return 0.5;
  const s = status.toUpperCase();
  if (s === 'STABLE' || s === 'BUY')  return 0.82;
  if (s === 'WATCH'  || s === 'HOLD') return 0.45;
  if (s === 'SELL')                   return 0.18;
  return 0.5;
}

function buildCellScore(ticker, col, riskRow) {
  if (!riskRow) {
    const rng = seededRand(ticker.charCodeAt(0) * 31 + col.charCodeAt(0));
    return rng();
  }
  const map = {
    'Momentum':  () => statusToScore(riskRow.momentum),
    'Regime':    () => statusToScore(riskRow.regime),
    'Rates':     () => statusToScore(riskRow.rates),
    'Sentiment': () => statusToScore(riskRow.sentiment),
    'Signal':    () => statusToScore(riskRow.sig_score),
  };
  return (map[col] || (() => 0.5))();
}

function initRiskMatrix(svgEl, intelligenceData) {
  render(svgEl, intelligenceData);

  return {
    update(newData) { render(svgEl, newData); },
  };
}

function render(svgEl, data) {
  const W = 500, H = 320;
  const COL_W = 78, ROW_H = 48;
  const LABEL_W = 62, HEADER_H = 36;

  svgEl.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svgEl.innerHTML = '';

  const ns = 'http://www.w3.org/2000/svg';

  function el(tag, attrs, text) {
    const e = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    if (text !== undefined) e.textContent = text;
    return e;
  }

  const riskMatrix = data?.intelligence_synthesis?.risk_matrix || [];

  // Header row
  MATRIX_COLS.forEach((col, ci) => {
    svgEl.appendChild(el('text', {
      x: LABEL_W + ci * COL_W + COL_W / 2,
      y: HEADER_H - 6,
      'text-anchor': 'middle',
      fill: '#00E5FF',
      'font-family': '"Space Mono", monospace',
      'font-size': '9',
      'letter-spacing': '0.05em',
    }, col.toUpperCase()));
  });

  // Rows
  MATRIX_TICKERS.forEach((ticker, ri) => {
    const y = HEADER_H + ri * ROW_H;
    const riskRow = riskMatrix.find(r => r.ticker === ticker);

    // Row label
    svgEl.appendChild(el('text', {
      x: LABEL_W - 4,
      y: y + ROW_H / 2 + 4,
      'text-anchor': 'end',
      fill: '#E8F0FE',
      'font-family': '"Space Mono", monospace',
      'font-size': '9',
    }, ticker));

    MATRIX_COLS.forEach((col, ci) => {
      const x = LABEL_W + ci * COL_W;
      const score = buildCellScore(ticker, col, riskRow);
      const fill = lerpColor(score);

      // Cell background
      const rect = el('rect', {
        x: x + 2, y: y + 4,
        width: COL_W - 4, height: ROW_H - 8,
        rx: '4',
        fill,
        stroke: 'rgba(255,255,255,0.06)',
        'stroke-width': '0.5',
      });
      svgEl.appendChild(rect);

      // Score text
      svgEl.appendChild(el('text', {
        x: x + COL_W / 2,
        y: y + ROW_H / 2 + 4,
        'text-anchor': 'middle',
        fill: '#E8F0FE',
        'font-family': '"Space Mono", monospace',
        'font-size': '10',
        'font-weight': '700',
      }, Math.round(score * 100)));

      // ADJUST tag
      if (score > 0.8) {
        const tag = el('text', {
          x: x + COL_W / 2,
          y: y + ROW_H - 6,
          'text-anchor': 'middle',
          fill: '#00E5FF',
          'font-size': '7',
          'letter-spacing': '0.04em',
          class: 'node-flash',
          style: 'animation: node-flash 1.4s ease-in-out infinite;',
        }, '▲ ADJUST');
        svgEl.appendChild(tag);
      }

      // REDUCE tag
      if (score < 0.25) {
        const tag = el('text', {
          x: x + COL_W / 2,
          y: y + ROW_H - 6,
          'text-anchor': 'middle',
          fill: '#BF00FF',
          'font-size': '7',
          'letter-spacing': '0.04em',
        }, '▼ REDUCE');
        svgEl.appendChild(tag);
      }
    });
  });

  // Grid lines
  for (let ri = 0; ri <= MATRIX_TICKERS.length; ri++) {
    const y = HEADER_H + ri * ROW_H;
    svgEl.appendChild(el('line', {
      x1: LABEL_W, y1: y,
      x2: LABEL_W + MATRIX_COLS.length * COL_W, y2: y,
      stroke: 'rgba(255,255,255,0.05)', 'stroke-width': '0.5',
    }));
  }
}
