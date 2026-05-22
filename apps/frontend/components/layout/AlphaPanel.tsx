'use client'
import { useRegime, useSignals } from '@/hooks/useAlephData'
import { regimeColor, signalColor, signalBadgeClass } from '@/lib/utils'
import type { AlephStreamData, SignalSummaryDTO } from '@/lib/types'

function HealthArc({ score }: { score: number }) {
  const r = 28
  const circ = 2 * Math.PI * r
  const fill = circ * (score / 100)
  const color = score >= 70 ? '#00E5FF' : score >= 40 ? '#FF9800' : '#BF00FF'
  return (
    <svg width="72" height="72" viewBox="0 0 72 72" className="mx-auto">
      <circle cx="36" cy="36" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="4" />
      <circle
        cx="36" cy="36" r={r} fill="none"
        stroke={color} strokeWidth="4"
        strokeDasharray={`${fill} ${circ}`}
        strokeDashoffset={circ * 0.25}
        strokeLinecap="round"
        style={{ transition: 'stroke-dasharray 0.5s ease', filter: `drop-shadow(0 0 6px ${color})` }}
      />
      <text x="36" y="40" textAnchor="middle" fill={color}
        fontSize="16" fontFamily="'Space Mono', monospace" fontWeight="bold">
        {score}
      </text>
    </svg>
  )
}

function SignalRow({ sig }: { sig: SignalSummaryDTO }) {
  const badgeClass = signalBadgeClass(sig.signal_type)
  return (
    <div className="flex items-center gap-2 py-1 border-b border-[rgba(255,255,255,0.05)] last:border-0 animate-fade-in">
      <span className={`${badgeClass} text-[8px] font-bold uppercase tracking-widest border rounded px-1.5 py-0.5 shrink-0`}>
        {sig.signal_type}
      </span>
      <span className="text-[10px] text-[rgba(232,240,254,0.65)] truncate flex-1">{sig.signal_id}</span>
      <span className="text-[10px] tabular-nums shrink-0" style={{ color: signalColor(sig.signal_type) }}>
        {Math.round(sig.score * 100)}%
      </span>
    </div>
  )
}

function StreamSignalRow({ sig }: { sig: AlephStreamData['active_signals'][number] }) {
  const type = sig.action.toLowerCase()
  return (
    <div className="flex items-center gap-2 py-1 border-b border-[rgba(255,255,255,0.05)] last:border-0 transition-all duration-500">
      <span className={`${signalBadgeClass(type)} text-[8px] font-bold uppercase tracking-widest border rounded px-1.5 py-0.5 shrink-0`}>
        {sig.action}
      </span>
      <span className="text-[10px] text-[rgba(232,240,254,0.65)] truncate flex-1">{sig.strategy}</span>
      <span className="text-[10px] tabular-nums shrink-0" style={{ color: signalColor(type) }}>
        {Math.round(sig.probability * 100)}%
      </span>
    </div>
  )
}

interface Props { streamData?: AlephStreamData | null }

export default function AlphaPanel({ streamData }: Props) {
  const { data: regime, isLoading: rLoading } = useRegime()
  const { data: signals, isLoading: sLoading } = useSignals()

  const hasStream = !!streamData
  const loading   = !hasStream && (rLoading || sLoading)

  // ── Health ──────────────────────────────────────────────────────────────────
  const health = hasStream
    ? Math.round(streamData!.portfolio_health.score)
    : (() => {
        const sigList = signals?.signals ?? []
        const avg = sigList.length ? sigList.reduce((s: number, x: SignalSummaryDTO) => s + x.score, 0) / sigList.length : 0
        return Math.round(avg * 100)
      })()

  // ── Regime ──────────────────────────────────────────────────────────────────
  const rColor = hasStream
    ? regimeColor(streamData!.macro_regime.regime_name)
    : regimeColor(regime?.regime_label ?? '')

  const rLabel = hasStream
    ? streamData!.macro_regime.regime_name.replace(/_/g, ' ')
    : regime?.regime_label ?? '—'

  const rFamily = hasStream
    ? streamData!.macro_regime.market_phase.replace(/_/g, ' ')
    : regime?.regime_family ?? ''

  const rConf = hasStream
    ? `${Math.round(streamData!.macro_regime.confidence_score * 100)}%`
    : regime?.confidence ?? '—'

  // ── Signals ─────────────────────────────────────────────────────────────────
  const streamSigs  = streamData?.active_signals ?? []
  const swrSigs     = (signals?.signals ?? []).slice(0, 4)

  return (
    <aside className="w-[220px] shrink-0 flex flex-col gap-3 p-3 overflow-y-auto
      border-r border-[rgba(255,255,255,0.06)]"
      style={{ height: '100%' }}>

      <p className="label-dim pt-0.5">Personal Alpha</p>

      {/* Health arc */}
      <div className="glass-card p-3 text-center">
        <p className="label-dim mb-2">Alpha Health</p>
        <HealthArc score={loading ? 0 : health} />
        <p className="text-[9px] text-[rgba(232,240,254,0.35)] mt-1">
          {hasStream ? streamData!.portfolio_health.source : 'Signal strength index'}
        </p>
      </div>

      {/* Macro regime */}
      <div className="glass-card p-3">
        <p className="label-dim mb-1.5">Macro Regime</p>
        {loading ? (
          <p className="text-[rgba(232,240,254,0.3)] text-xs">···</p>
        ) : (
          <>
            <p className="text-sm font-bold uppercase tracking-wider transition-all duration-500"
              style={{ color: rColor, textShadow: `0 0 10px ${rColor}66` }}>
              {rLabel}
            </p>
            <p className="text-[10px] text-[rgba(232,240,254,0.45)] capitalize mt-0.5 transition-all duration-500">
              {rFamily}
            </p>
            <p className="text-[9px] text-[rgba(232,240,254,0.35)] mt-1 uppercase tracking-wide transition-all duration-500">
              {rConf} confidence
            </p>
            {!hasStream && regime?.is_seeded && (
              <p className="text-[9px] text-[rgba(255,152,0,0.7)] mt-1.5">⚠ BOOTSTRAP DATA</p>
            )}
          </>
        )}
      </div>

      {/* Signals list */}
      <div className="glass-card p-3 flex-1">
        <p className="label-dim mb-2">Active Signals
          {!hasStream && signals && (
            <span className="ml-1 text-[rgba(0,229,255,0.6)]">
              ({signals.buy_count}B / {signals.sell_count}S / {signals.hold_count}H)
            </span>
          )}
          {hasStream && (
            <span className="ml-1 text-[rgba(0,229,255,0.6)]">
              ({streamSigs.filter(s => s.action === 'BUY').length}B /&nbsp;
               {streamSigs.filter(s => s.action === 'SELL').length}S /&nbsp;
               {streamSigs.filter(s => s.action === 'HOLD').length}H)
            </span>
          )}
        </p>
        {hasStream ? (
          streamSigs.length === 0
            ? <p className="text-[10px] text-[rgba(232,240,254,0.25)]">No signals</p>
            : streamSigs.map((sig, i) => <StreamSignalRow key={i} sig={sig} />)
        ) : (
          swrSigs.length === 0
            ? <p className="text-[10px] text-[rgba(232,240,254,0.25)]">
                {loading ? 'Loading…' : 'No signals'}
              </p>
            : swrSigs.map((sig) => <SignalRow key={sig.signal_id} sig={sig} />)
        )}
      </div>
    </aside>
  )
}
