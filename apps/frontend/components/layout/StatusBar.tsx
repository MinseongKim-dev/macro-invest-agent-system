'use client'
import { useEffect, useState } from 'react'
import { useRegime } from '@/hooks/useAlephData'
import { regimeColor, formatUtcClock } from '@/lib/utils'

const STATUS_COLORS: Record<string, string> = {
  success:   '#00E5FF',
  degraded:  '#FF9800',
  stale:     '#FF9800',
  bootstrap: '#BF00FF',
}

export default function StatusBar() {
  const [clock, setClock] = useState('')
  const { data: regime, isLoading, error } = useRegime()

  useEffect(() => {
    setClock(formatUtcClock())
    const id = setInterval(() => setClock(formatUtcClock()), 1000)
    return () => clearInterval(id)
  }, [])

  const rLabel   = regime?.regime_label ?? (isLoading ? '···' : '—')
  const rColor   = regimeColor(regime?.regime_label ?? '')
  const status   = regime?.status ?? 'unknown'
  const dotColor = error ? '#FF1744' : STATUS_COLORS[status] ?? '#8899AA'
  const dotLabel = error ? 'ERR' : regime ? status.toUpperCase() : '···'

  return (
    <header className="fixed top-0 left-0 right-0 z-50 flex items-center gap-4 px-4
      h-10 border-b border-[rgba(255,255,255,0.07)]
      bg-[rgba(8,8,26,0.92)] backdrop-blur-[24px]
      font-mono text-[11px] select-none">

      {/* Brand */}
      <span className="neon-cyan font-bold tracking-[0.25em]">ALEPH-ONE</span>
      <span className="text-[rgba(232,240,254,0.25)]">▸</span>

      {/* Clock */}
      <span className="text-[rgba(232,240,254,0.5)] tabular-nums">{clock}</span>

      <span className="flex-1" />

      {/* Regime badge */}
      <span
        className="uppercase tracking-widest font-bold px-2 py-0.5 rounded text-[10px]"
        style={{
          color: rColor,
          border: `1px solid ${rColor}44`,
          background: `${rColor}11`,
        }}
      >
        {rLabel}
      </span>

      {/* System status dot */}
      <span className="flex items-center gap-1.5 text-[rgba(232,240,254,0.45)]">
        <span
          className="inline-block w-1.5 h-1.5 rounded-full"
          style={{ background: dotColor, boxShadow: `0 0 6px ${dotColor}` }}
        />
        <span className="text-[9px] tracking-widest">{dotLabel}</span>
      </span>
    </header>
  )
}
