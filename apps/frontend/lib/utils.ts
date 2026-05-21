import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import type { SignalType } from './types'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

// Maps regime label → neon hex color
const REGIME_COLOR_MAP: Record<string, string> = {
  goldilocks:   '#00E5FF',
  expansion:    '#00FF88',
  overheating:  '#FF9800',
  slowdown:     '#FF5722',
  contraction:  '#BF00FF',
  recession:    '#FF1744',
  stagflation:  '#FF6D00',
  recovery:     '#69F0AE',
  reflation:    '#FFEA00',
  stagnation:   '#B0BEC5',
}

export function regimeColor(label: string): string {
  const key = label.toLowerCase().replace(/[\s_\-]/g, '')
  for (const [k, color] of Object.entries(REGIME_COLOR_MAP)) {
    if (key.includes(k)) return color
  }
  return '#8899AA'
}

export function signalColor(type: SignalType | string): string {
  switch (type) {
    case 'buy':     return '#00E5FF'
    case 'sell':    return '#BF00FF'
    case 'hold':    return '#FF9800'
    default:        return '#8899AA'
  }
}

export function signalBadgeClass(type: SignalType | string): string {
  switch (type) {
    case 'buy':  return 'badge-buy'
    case 'sell': return 'badge-sell'
    case 'hold': return 'badge-hold'
    default:     return 'badge-neutral'
  }
}

export function confidenceAlpha(confidence: string): number {
  switch (confidence.toLowerCase()) {
    case 'high':   return 1.0
    case 'medium': return 0.7
    case 'low':    return 0.45
    default:       return 0.35
  }
}

export function formatUtcClock(): string {
  const now = new Date()
  return now.toUTCString().slice(17, 25) + ' UTC'
}

export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
    })
  } catch {
    return iso.slice(0, 10)
  }
}

// Deterministic seeded random (sine-based, no imul required)
export function seededRand(seed: number): number {
  const x = Math.sin(seed + 1) * 10000
  return x - Math.floor(x)
}
