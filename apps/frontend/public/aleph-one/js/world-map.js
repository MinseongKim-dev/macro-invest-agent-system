/* world-map.js — Heatmap dots on SVG world map + news ticker */

// Rough SVG coordinate mappings for notable market locations
// SVG viewBox: 0 0 900 380
const EVENT_LOCATIONS = {
  US:     { x: 180, y: 150 },
  USA:    { x: 180, y: 150 },
  EU:     { x: 420, y: 80  },
  EUROPE: { x: 420, y: 80  },
  CN:     { x: 640, y: 120 },
  CHINA:  { x: 640, y: 120 },
  KR:     { x: 680, y: 100 },
  KOREA:  { x: 680, y: 100 },
  JP:     { x: 710, y: 90  },
  JAPAN:  { x: 710, y: 90  },
  UK:     { x: 390, y: 70  },
  DEFAULT:{ x: 450, y: 190 },
};

function eventColor(type) {
  if (!type) return '#00E5FF';
  const t = type.toUpperCase();
  if (t.includes('BULLISH') || t.includes('POSITIVE') || t.includes('GROWTH')) return '#00FF88';
  if (t.includes('BEARISH') || t.includes('NEGATIVE') || t.includes('DROP'))   return '#FF3366';
  return '#BF00FF';
}

function initWorldMap(svgEl, events) {
  renderDots(svgEl, events);
  return {
    update(newEvents) { renderDots(svgEl, newEvents); },
  };
}

function renderDots(svgEl, events) {
  const ns = 'http://www.w3.org/2000/svg';
  const container = svgEl.getElementById
    ? svgEl.getElementById('heatmap-dots')
    : svgEl.querySelector('#heatmap-dots');

  if (!container) return;
  container.innerHTML = '';

  if (!events || events.length === 0) {
    // Default ambient dots
    [
      { x: 180, y: 150, c: '#00E5FF' },
      { x: 420, y: 80,  c: '#00E5FF' },
      { x: 640, y: 120, c: '#BF00FF' },
      { x: 680, y: 100, c: '#00FF88' },
    ].forEach(({ x, y, c }) => appendDot(container, ns, x, y, c));
    return;
  }

  events.slice(0, 12).forEach((evt, i) => {
    const region = (evt.region || evt.country || 'DEFAULT').toUpperCase();
    const key = Object.keys(EVENT_LOCATIONS).find(k => region.includes(k)) || 'DEFAULT';
    const { x, y } = EVENT_LOCATIONS[key];
    // Jitter so overlapping events spread slightly
    const jx = x + (i % 3 - 1) * 12;
    const jy = y + (Math.floor(i / 3) % 3 - 1) * 8;
    appendDot(container, ns, jx, jy, eventColor(evt.event_type || ''));
  });
}

function appendDot(container, ns, x, y, color) {
  const g = document.createElementNS(ns, 'g');

  // Glow halo
  const halo = document.createElementNS(ns, 'circle');
  halo.setAttribute('cx', x); halo.setAttribute('cy', y); halo.setAttribute('r', '10');
  halo.setAttribute('fill', color.replace(')', ', 0.12)').replace('rgb', 'rgba').replace('#', 'rgba(').replace('rgba(', '#').replace(/^#/, ''));
  halo.setAttribute('style', `fill: ${color}22;`);
  g.appendChild(halo);

  // Core dot
  const dot = document.createElementNS(ns, 'circle');
  dot.setAttribute('cx', x); dot.setAttribute('cy', y); dot.setAttribute('r', '4');
  dot.setAttribute('fill', color);
  dot.setAttribute('class', 'heatmap-dot');
  dot.setAttribute('style', `animation-delay: ${Math.random() * 2}s`);
  g.appendChild(dot);

  container.appendChild(g);
}

function updateTicker(events) {
  const el = document.getElementById('ticker-content');
  if (!el) return;
  if (!events || events.length === 0) {
    el.textContent = 'INTELLIGENCE STREAM INITIALIZING…';
    return;
  }
  const items = events.map(e => {
    const type = e.event_type ? `[${e.event_type.toUpperCase()}]` : '';
    return `${type} ${e.title || e.description || '—'}`;
  }).join('   ◆   ');
  el.textContent = items;
}
