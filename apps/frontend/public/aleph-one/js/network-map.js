/* network-map.js — Three.js 3D portfolio sphere */

const PORTFOLIO_NODES = [
  { id: 'AAPL',   weight: 0.28, group: 'TECH' },
  { id: 'MSFT',   weight: 0.22, group: 'TECH' },
  { id: 'TSLA',   weight: 0.14, group: 'AUTO' },
  { id: '005930', weight: 0.18, group: 'SEMI' },
  { id: '000660', weight: 0.18, group: 'SEMI' },
];

function fibonacciSphere(n) {
  const pts = [];
  const phi = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = phi * i;
    pts.push(new THREE.Vector3(r * Math.cos(theta), y, r * Math.sin(theta)));
  }
  return pts;
}

function makeLabel(text) {
  const canvas = document.createElement('canvas');
  canvas.width = 128; canvas.height = 32;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'rgba(0,0,0,0)';
  ctx.clearRect(0, 0, 128, 32);
  ctx.fillStyle = '#00E5FF';
  ctx.font = 'bold 18px "Space Mono", monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 64, 16);
  const tex = new THREE.CanvasTexture(canvas);
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(0.7, 0.175, 1);
  return sprite;
}

function initNetworkMap(canvas, networkNodes) {
  const W = canvas.clientWidth  || 400;
  const H = canvas.clientHeight || 360;

  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(W, H);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, W / H, 0.1, 100);
  camera.position.set(0, 0, 5);

  scene.add(new THREE.AmbientLight(0x00E5FF, 0.4));
  const pt = new THREE.PointLight(0xBF00FF, 1.2, 20);
  pt.position.set(3, 3, 3);
  scene.add(pt);

  /* ── Sphere shell ─────────────────────────────────────────────────────── */
  const shell = new THREE.Mesh(
    new THREE.SphereGeometry(1.8, 24, 24),
    new THREE.MeshBasicMaterial({ color: 0x00E5FF, wireframe: true, transparent: true, opacity: 0.12 }),
  );
  scene.add(shell);

  /* ── Nodes ────────────────────────────────────────────────────────────── */
  const positions = fibonacciSphere(PORTFOLIO_NODES.length).map(v => v.multiplyScalar(1.8));
  const nodeGroup = new THREE.Group();

  positions.forEach((pos, i) => {
    const node = PORTFOLIO_NODES[i];

    // Use live network_nodes data if available
    let livePos = pos.clone();
    if (networkNodes && networkNodes[i]) {
      const n = networkNodes[i];
      livePos = new THREE.Vector3(
        (n.x ?? pos.x / 1.8) * 1.8,
        (n.y ?? pos.y / 1.8) * 1.8,
        (n.z ?? pos.z / 1.8) * 1.8,
      );
    }

    const dot = new THREE.Mesh(
      new THREE.CircleGeometry(0.07, 12),
      new THREE.MeshBasicMaterial({ color: 0x00E5FF, side: THREE.DoubleSide }),
    );
    dot.position.copy(livePos);
    dot.lookAt(camera.position);
    nodeGroup.add(dot);

    const label = makeLabel(node.id);
    label.position.set(livePos.x * 1.18, livePos.y * 1.18 + 0.15, livePos.z * 1.18);
    nodeGroup.add(label);

    // Arrow: radial outward, length weighted by portfolio weight
    const dir = livePos.clone().normalize();
    const arrow = new THREE.ArrowHelper(dir, livePos, node.weight * 0.9, 0xBF00FF, 0.12, 0.07);
    nodeGroup.add(arrow);
  });

  /* ── Edges ────────────────────────────────────────────────────────────── */
  const edgePositions = [];
  for (let a = 0; a < positions.length; a++) {
    for (let b = a + 1; b < positions.length; b++) {
      edgePositions.push(positions[a].x, positions[a].y, positions[a].z);
      edgePositions.push(positions[b].x, positions[b].y, positions[b].z);
    }
  }
  const edgeGeo = new THREE.BufferGeometry();
  edgeGeo.setAttribute('position', new THREE.Float32BufferAttribute(edgePositions, 3));
  const edges = new THREE.LineSegments(
    edgeGeo,
    new THREE.LineBasicMaterial({ color: 0x00E5FF, transparent: true, opacity: 0.15 }),
  );
  scene.add(edges);
  scene.add(nodeGroup);

  /* ── Animation loop ───────────────────────────────────────────────────── */
  function animate() {
    requestAnimationFrame(animate);
    shell.rotation.y += 0.003;
    nodeGroup.rotation.y += 0.003;
    edges.rotation.y += 0.003;
    renderer.render(scene, camera);
  }
  animate();

  /* ── Resize ───────────────────────────────────────────────────────────── */
  const ro = new ResizeObserver(() => {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  });
  ro.observe(canvas);

  return {
    update(newNetworkNodes) {
      // No-op live update: full re-init would flicker; sphere rotation conveys life
    },
  };
}
