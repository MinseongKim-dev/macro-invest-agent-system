// Aleph-One World Map Heatmap + News Ticker
// Enhances the inline SVG continent paths with heatmap event dots
// and populates the scrolling news ticker

(function () {
  // Approximate center coordinates in the SVG viewBox "0 0 900 260"
  // matching the continent <path> elements in index.html
  const REGION_POS = {
    US:     { x: 155, y: 110 },
    EU:     { x: 444, y: 80  },
    UK:     { x: 430, y: 72  },
    CN:     { x: 720, y: 70  },
    JP:     { x: 802, y: 78  },
    APAC:   { x: 728, y: 162 },
    GLOBAL: { x: 450, y: 130 },
  };

  let _svgEl = null;
  let _tickerEl = null;
  let _dots = [];

  function _init(svgEl, tickerEl) {
    _svgEl   = svgEl;
    _tickerEl = tickerEl;
  }

  function _clearDots() {
    _dots.forEach(d => { if (d.parentNode) d.parentNode.removeChild(d); });
    _dots = [];
  }

  function _updateWithEvents(eventsData) {
    if (!_svgEl) return;
    _clearDots();

    const events = eventsData?.events || (Array.isArray(eventsData) ? eventsData : []);

    // Tally events per region
    const counts = {};
    events.forEach(evt => {
      const region = (evt.region || 'GLOBAL').toUpperCase();
      counts[region] = (counts[region] || 0) + 1;
    });

    // Draw animated heatmap circles on the SVG
    Object.entries(counts).forEach(([region, count], idx) => {
      const pos = REGION_POS[region] || REGION_POS.GLOBAL;
      const hot = count >= 3;
      const r   = 5 + count * 3;

      // Outer glow ring
      const ring = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      ring.setAttribute('cx', pos.x);
      ring.setAttribute('cy', pos.y);
      ring.setAttribute('r',  r + 4);
      ring.setAttribute('fill', 'none');
      ring.setAttribute('stroke', hot ? 'rgba(191,0,255,0.5)' : 'rgba(0,229,255,0.4)');
      ring.setAttribute('stroke-width', '1');
      ring.style.animation       = `heatmap-pulse ${1.8 + idx * 0.3}s ease-in-out infinite`;
      ring.style.animationDelay  = `${idx * 0.25}s`;
      _svgEl.appendChild(ring);
      _dots.push(ring);

      // Core dot
      const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      dot.setAttribute('cx', pos.x);
      dot.setAttribute('cy', pos.y);
      dot.setAttribute('r',  r);
      dot.setAttribute('fill', hot ? 'rgba(191,0,255,0.55)' : 'rgba(0,229,255,0.45)');
      dot.setAttribute('stroke', hot ? 'rgba(191,0,255,0.85)' : 'rgba(0,229,255,0.85)');
      dot.setAttribute('stroke-width', '1');
      _svgEl.appendChild(dot);
      _dots.push(dot);
    });

    // Populate the news ticker
    if (_tickerEl && events.length > 0) {
      const items = events.map(evt => {
        const type  = (evt.event_type || evt.type || 'EVENT').replace(/_/g, ' ');
        const title = evt.title || evt.description || type;
        return `<span style="color:rgba(0,229,255,0.9)">[${type}]</span> ${_esc(title)}`;
      });
      // Duplicate for seamless infinite scroll
      const html = items.join('&nbsp;&nbsp;<span style="color:rgba(0,229,255,0.3)">///</span>&nbsp;&nbsp;');
      _tickerEl.innerHTML = html + '&nbsp;&nbsp;<span style="color:rgba(0,229,255,0.3)">///</span>&nbsp;&nbsp;' + html;
    }
  }

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  window.AlephWorldMap = { init: _init, updateWithEvents: _updateWithEvents };
}());
