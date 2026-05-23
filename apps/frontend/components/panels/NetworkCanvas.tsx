'use client'
import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { useSignals } from '@/hooks/useAlephData'
import type { SignalsLatestResponse } from '@/lib/types'

// Tickers must match backend TICKERS constant in src/engines.py
const NODE_LABELS = ['AAPL', 'MSFT', 'TSLA', '005930', '000660']

function fibonacciSphere(n: number, r: number): THREE.Vector3[] {
  return Array.from({ length: n }, (_, i) => {
    const theta = Math.acos(1 - (2 * (i + 0.5)) / n)
    const phi   = Math.PI * (1 + Math.sqrt(5)) * i
    return new THREE.Vector3(
      r * Math.sin(theta) * Math.cos(phi),
      r * Math.cos(theta),
      r * Math.sin(theta) * Math.sin(phi),
    )
  })
}

function nodeColor(signals: SignalsLatestResponse | undefined, idx: number): number {
  const sig = signals?.signals?.[idx % Math.max((signals?.signals?.length ?? 1), 1)]
  if (!sig) return 0x8899AA
  if (sig.signal_type === 'buy')  return 0x00E5FF
  if (sig.signal_type === 'sell') return 0xBF00FF
  return 0xFF9800
}

function nodeScore(signals: SignalsLatestResponse | undefined, idx: number): number {
  const sig = signals?.signals?.[idx % Math.max((signals?.signals?.length ?? 1), 1)]
  return sig?.score ?? 0.5
}

function buildScene(
  container: HTMLDivElement,
  signals: SignalsLatestResponse | undefined,
): {
  renderer: THREE.WebGLRenderer
  group: THREE.Group
  raf: { id: number }
  ro: ResizeObserver
} {
  const W = container.clientWidth
  const H = container.clientHeight

  const scene    = new THREE.Scene()
  const camera   = new THREE.PerspectiveCamera(58, W / H, 0.1, 100)
  camera.position.z = 4.8

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(W, H)
  renderer.setClearColor(0x000000, 0)
  container.appendChild(renderer.domElement)

  // All objects rotate together
  const group = new THREE.Group()
  scene.add(group)

  // Translucent wireframe sphere shell
  group.add(new THREE.Mesh(
    new THREE.SphereGeometry(1.8, 28, 28),
    new THREE.MeshBasicMaterial({ color: 0x00E5FF, wireframe: true, transparent: true, opacity: 0.07 }),
  ))

  // Inner glow sphere
  group.add(new THREE.Mesh(
    new THREE.SphereGeometry(1.75, 16, 16),
    new THREE.MeshBasicMaterial({ color: 0x001133, transparent: true, opacity: 0.25, side: THREE.BackSide }),
  ))

  const positions = fibonacciSphere(NODE_LABELS.length, 1.8)

  // Per-node: core sphere + halo ring + outward arrow
  positions.forEach((pos, i) => {
    const color = nodeColor(signals, i)
    const score = nodeScore(signals, i)

    // Core
    const core = new THREE.Mesh(
      new THREE.SphereGeometry(0.055 + score * 0.04, 10, 10),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95 }),
    )
    core.position.copy(pos)
    group.add(core)

    // Halo ring — billboard-facing camera (updated in tick)
    const halo = new THREE.Mesh(
      new THREE.RingGeometry(0.10, 0.14, 18),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.35, side: THREE.DoubleSide }),
    )
    halo.position.copy(pos)
    halo.lookAt(camera.position)
    group.add(halo)

    // Purple recommendation vector (outward radial)
    const dir    = pos.clone().normalize()
    const origin = pos.clone().multiplyScalar(0.92)
    const arrow  = new THREE.ArrowHelper(dir, origin, 0.22 + score * 0.4, 0xBF00FF, 0.08, 0.048)
    group.add(arrow)
  })

  // Connection edges between all node pairs
  const verts: number[] = []
  positions.forEach((a, i) => {
    positions.slice(i + 1).forEach((b) => {
      verts.push(...a.toArray(), ...b.toArray())
    })
  })
  const edgeGeo = new THREE.BufferGeometry()
  edgeGeo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3))
  group.add(new THREE.LineSegments(
    edgeGeo,
    new THREE.LineBasicMaterial({ color: 0x00E5FF, transparent: true, opacity: 0.13 }),
  ))

  // Subtle ambient light
  scene.add(new THREE.AmbientLight(0x112255, 4))

  // Animation loop
  const raf = { id: 0 }
  const tick = () => {
    raf.id = requestAnimationFrame(tick)
    group.rotation.y += 0.003
    group.rotation.x += 0.0005
    renderer.render(scene, camera)
  }
  tick()

  // Responsive resize
  const ro = new ResizeObserver(() => {
    const w = container.clientWidth
    const h = container.clientHeight
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    renderer.setSize(w, h)
  })
  ro.observe(container)

  return { renderer, group, raf, ro }
}

export default function NetworkCanvas({ className = '' }: { className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { data: signals } = useSignals()

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const { renderer, raf, ro } = buildScene(container, signals)

    return () => {
      cancelAnimationFrame(raf.id)
      ro.disconnect()
      renderer.dispose()
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement)
      }
    }
  // Re-initialize when signal data arrives so node colors update
  }, [signals]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={containerRef} className={`w-full h-full ${className}`}>
      {/* Fallback shown before Three.js initializes */}
    </div>
  )
}
