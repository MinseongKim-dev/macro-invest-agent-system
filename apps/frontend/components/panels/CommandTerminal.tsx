'use client'
import { useState, useRef, useCallback } from 'react'
import { useRegime, useSignals } from '@/hooks/useAlephData'

type TermStatus = 'ready' | 'scanning' | 'complete' | 'error'

const CANNED: Record<string, string> = {
  regime:   'Current macro regime loaded from persisted store. Confidence and rationale attached — see Advisory Panel.',
  signals:  'Signal engine run complete. Results are regime-grounded and heuristic. Not a trade directive.',
  health:   'Alpha health index computed from signal score distribution. No statistical calibration claimed.',
  default:  'OMNI analysis complete. Context derived from deterministic domain layer. Treat all outputs as advisory.',
}

function pickResponse(query: string, regime?: string, signalCount?: number): string {
  const q = query.toLowerCase()
  const prefix = regime ? `[${regime.toUpperCase()}] ` : ''
  if (q.includes('regime'))  return prefix + CANNED.regime
  if (q.includes('signal'))  return prefix + `${signalCount ?? 0} active signals evaluated. ` + CANNED.signals
  if (q.includes('health'))  return prefix + CANNED.health
  return prefix + CANNED.default
}

export default function CommandTerminal() {
  const [query, setQuery]       = useState('')
  const [status, setStatus]     = useState<TermStatus>('ready')
  const [scanY, setScanY]       = useState(0)
  const [response, setResponse] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const rafRef   = useRef<number | null>(null)

  const { data: regime }  = useRegime()
  const { data: signals } = useSignals()

  const runScan = useCallback(() => {
    if (!query.trim()) { inputRef.current?.focus(); return }
    setStatus('scanning')
    setResponse(null)
    setScanY(0)

    let pos = 0
    const step = () => {
      pos += 4
      setScanY(pos)
      if (pos < 100) {
        rafRef.current = requestAnimationFrame(step)
      } else {
        setStatus('complete')
        setResponse(pickResponse(query, regime?.regime_label, signals?.signals_count))
      }
    }
    rafRef.current = requestAnimationFrame(step)
  }, [query, regime, signals])

  const statusDot = {
    ready:    { color: 'rgba(0,229,255,0.5)',  label: '● READY' },
    scanning: { color: '#FF9800',              label: '◌ SCANNING' },
    complete: { color: '#00E5FF',              label: '● COMPLETE' },
    error:    { color: '#FF1744',              label: '✕ ERROR' },
  }[status]

  return (
    <div className="glass-card-cyan p-4 flex flex-col gap-3 shrink-0">

      {/* Input row */}
      <div className="flex items-center gap-3 border-b border-[rgba(0,229,255,0.15)] pb-3">
        <span className="neon-cyan text-xs font-bold shrink-0 tracking-widest">OMNI://</span>
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && runScan()}
          placeholder="enter macro query  (e.g. 'regime status', 'signal health')"
          className="flex-1 bg-transparent outline-none text-xs text-[#E8F0FE]
            placeholder-[rgba(232,240,254,0.2)] font-mono caret-[#00E5FF]"
        />
        <button
          onClick={runScan}
          className="shrink-0 text-[9px] font-bold uppercase tracking-[0.18em]
            px-3 py-1 rounded border border-[rgba(0,229,255,0.4)] text-[#00E5FF]
            hover:bg-[rgba(0,229,255,0.1)] active:scale-95 transition-all"
        >
          ANALYZE
        </button>
      </div>

      {/* Status + scan-line + response */}
      <div className="relative min-h-[36px] overflow-hidden">
        <div className="flex items-center gap-2 text-[10px]" style={{ color: statusDot.color }}>
          {statusDot.label}
        </div>

        {/* Scan line */}
        {status === 'scanning' && (
          <div
            className="absolute left-0 right-0 h-px pointer-events-none"
            style={{
              top: `${scanY}%`,
              background: 'linear-gradient(90deg, transparent, #00E5FF, transparent)',
              opacity: 0.8,
            }}
          />
        )}

        {/* Response text */}
        {response && (
          <p className="mt-2 text-[10px] leading-relaxed text-[rgba(232,240,254,0.7)]
            border-l-2 border-[rgba(0,229,255,0.35)] pl-3 animate-fade-in">
            {response}
          </p>
        )}
      </div>
    </div>
  )
}
