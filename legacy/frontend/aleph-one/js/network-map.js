// Aleph-One 3D Portfolio Network Map
// Requires THREE global (loaded from CDN before this script)

(function () {
  const NODES = [
    { ticker: 'AAPL',  weight: 0.25, lat:  37.3, lon: -122.0 },
    { ticker: 'MSFT',  weight: 0.20, lat:  47.6, lon: -122.3 },
    { ticker: 'GOOGL', weight: 0.22, lat:  37.4, lon: -122.1 },
    { ticker: 'TSLA',  weight: 0.15, lat:  30.2, lon:  -97.7 },
    { ticker: 'NVDA',  weight: 0.18, lat:  37.4, lon:  -121.9 },
  ];

  let _renderer, _scene, _camera, _orbitGroup, _nodeMeshes, _vectorLines, _rafId;

  function _latLon(lat, lon, r) {
    const phi   = (90 - lat) * (Math.PI / 180);
    const theta = (lon + 180) * (Math.PI / 180);
    return new THREE.Vector3(
      -r * Math.sin(phi) * Math.cos(theta),
       r * Math.cos(phi),
       r * Math.sin(phi) * Math.sin(theta)
    );
  }

  function _makeSprite(text) {
    const c = document.createElement('canvas');
    c.width = 128; c.height = 36;
    const ctx = c.getContext('2d');
    ctx.font = 'bold 22px "Courier New"';
    ctx.fillStyle = '#00E5FF';
    ctx.textAlign = 'center';
    ctx.shadowColor = '#00E5FF';
    ctx.shadowBlur = 8;
    ctx.fillText(text, 64, 26);
    const tex = new THREE.CanvasTexture(c);
    const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false });
    const sprite = new THREE.Sprite(mat);
    sprite.scale.set(0.40, 0.11, 1);
    return sprite;
  }

  function _resizeToContainer(canvas) {
    const cont = canvas.parentElement;
    const w = cont.clientWidth  || 300;
    const h = cont.clientHeight || 220;
    if (w === 0 || h === 0) return;
    _camera.aspect = w / h;
    _camera.updateProjectionMatrix();
    _renderer.setSize(w, h);
    _renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  }

  function _animate() {
    _rafId = requestAnimationFrame(_animate);
    _orbitGroup.rotation.y += 0.003;
    _orbitGroup.rotation.x += 0.0004;
    _renderer.render(_scene, _camera);
  }

  function _init(canvas) {
    if (typeof THREE === 'undefined') {
      console.warn('NetworkMap: THREE not loaded');
      return;
    }

    _scene = new THREE.Scene();

    _scene.add(new THREE.AmbientLight(0x0a0a2a, 1.0));
    const l1 = new THREE.PointLight(0x00E5FF, 2.5, 12);
    l1.position.set(2, 3, 3);
    _scene.add(l1);
    const l2 = new THREE.PointLight(0xBF00FF, 1.8, 12);
    l2.position.set(-3, -2, 2);
    _scene.add(l2);

    _camera = new THREE.PerspectiveCamera(52, 1, 0.1, 100);
    _camera.position.set(0, 0, 3.0);

    _renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    _renderer.setClearColor(0x000000, 0);

    _orbitGroup = new THREE.Group();
    _scene.add(_orbitGroup);

    // Inner sphere (dark, slightly transparent)
    _orbitGroup.add(new THREE.Mesh(
      new THREE.SphereGeometry(1, 32, 32),
      new THREE.MeshPhongMaterial({ color: 0x08081a, transparent: true, opacity: 0.55 })
    ));

    // Outer wireframe
    _orbitGroup.add(new THREE.Mesh(
      new THREE.SphereGeometry(1.015, 20, 20),
      new THREE.MeshBasicMaterial({ color: 0x00E5FF, wireframe: true, transparent: true, opacity: 0.07 })
    ));

    // Node spheres + glow halos + labels
    _nodeMeshes = [];
    NODES.forEach((node) => {
      const pos = _latLon(node.lat, node.lon, 1.0);
      const r = 0.045 + node.weight * 0.065;

      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(r, 12, 12),
        new THREE.MeshBasicMaterial({ color: 0x00E5FF })
      );
      mesh.position.copy(pos);
      _orbitGroup.add(mesh);
      _nodeMeshes.push(mesh);

      // Glow halo
      const halo = new THREE.Mesh(
        new THREE.SphereGeometry(r * 2.2, 10, 10),
        new THREE.MeshBasicMaterial({
          color: 0x00E5FF,
          transparent: true,
          opacity: 0.10,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        })
      );
      halo.position.copy(pos);
      _orbitGroup.add(halo);

      // Ticker label sprite
      const sprite = _makeSprite(node.ticker);
      sprite.position.copy(pos.clone().multiplyScalar(1.22));
      _orbitGroup.add(sprite);
    });

    // Connecting lines between all node pairs
    const lineMat = new THREE.LineBasicMaterial({ color: 0x00BFFF, transparent: true, opacity: 0.20 });
    for (let i = 0; i < NODES.length; i++) {
      for (let j = i + 1; j < NODES.length; j++) {
        const geo = new THREE.BufferGeometry().setFromPoints([
          _latLon(NODES[i].lat, NODES[i].lon, 1.0),
          _latLon(NODES[j].lat, NODES[j].lon, 1.0),
        ]);
        _orbitGroup.add(new THREE.Line(geo, lineMat));
      }
    }

    // Recommendation vectors (neon purple, node → outward)
    _vectorLines = [];
    NODES.forEach((node) => {
      const pos = _latLon(node.lat, node.lon, 1.0);
      const tip = pos.clone().multiplyScalar(1.55);
      const geo = new THREE.BufferGeometry().setFromPoints([pos, tip]);
      const mat = new THREE.LineBasicMaterial({
        color: 0xBF00FF,
        transparent: true,
        opacity: 0.75,
        blending: THREE.AdditiveBlending,
      });
      const line = new THREE.Line(geo, mat);
      _orbitGroup.add(line);
      _vectorLines.push(line);
    });

    // Use ResizeObserver for responsive sizing
    const ro = new ResizeObserver(() => _resizeToContainer(canvas));
    ro.observe(canvas.parentElement);

    // Delay first size check to after layout is complete
    requestAnimationFrame(() => requestAnimationFrame(() => _resizeToContainer(canvas)));

    _animate();
  }

  function _updateWithSignals(signals) {
    if (!_nodeMeshes || !signals) return;
    const list = signals.signals || [];
    const buyCount = list.filter(s => s.signal_type === 'buy').length;
    const ratio = list.length ? buyCount / list.length : 0.5;

    const bullish = new THREE.Color(0x00E5FF);
    const bearish = new THREE.Color(0x551155);
    const blended = bullish.clone().lerp(bearish, 1 - ratio);

    _nodeMeshes.forEach((mesh) => mesh.material.color.copy(blended));

    _vectorLines.forEach((line, i) => {
      const score = list[i % Math.max(list.length, 1)]?.score ?? 0.5;
      line.material.opacity = 0.25 + score * 0.65;
    });
  }

  window.AlephNetworkMap = { init: _init, updateWithSignals: _updateWithSignals };
}());
