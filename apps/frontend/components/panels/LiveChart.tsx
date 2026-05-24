'use client'
/**
 * LiveChart — real-time portfolio price sparklines with JARVIS-style hover
 * interactions and a sliding detail panel per asset.
 */

import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useMarketStream } from '@/hooks/useMarketStream'
import { fetchJson } from '@/lib/api'
import type { AlephRiskRow } from '@/lib/types'

// ── Constants ──────────────────────────────────────────────────────────────────
const TICKERS  = ['AAPL', 'MSFT', 'TSLA', '005930', '000660']
const KR_SET   = new Set(['005930', '000660'])
const ALLOC    = 0.20   // equal-weight 20% per ticker

const DISPLAY: Record<string, string> = {
  '005930': '삼성전자',
  '000660': 'SK하이닉스',
}

// Maps LiveChart internal codes to riskMatrix display names
const TO_MATRIX: Record<string, string> = {
  '005930': '삼성전자',
  '000660': 'SK하이닉스',
}

const CHART_W  = 130
const CHART_H  = 28
const SEED_PTS = 60

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatPrice(ticker: string, price: number): string {
  return KR_SET.has(ticker)
    ? `₩${Math.round(price).toLocaleString('ko-KR')}`
    : `$${price.toFixed(2)}`
}

/** Rolling std-dev / mean as a 0-99 score (proxy for short-term volatility). */
function volScore(hist: number[]): number {
  if (hist.length < 4) return 0
  const slice = hist.slice(-20)
  const mean  = slice.reduce((s, v) => s + v, 0) / slice.length
  const std   = Math.sqrt(slice.reduce((s, v) => s + (v - mean) ** 2, 0) / slice.length)
  return Math.min(99, Math.round((std / (mean || 1)) * 2000))
}

// ── Sparkline SVG ──────────────────────────────────────────────────────────────

function Sparkline({ prices, up }: { prices: number[]; up: boolean }) {
  if (prices.length < 2) {
    return (
      <svg width={CHART_W} height={CHART_H}>
        <line x1={0} y1={CHART_H / 2} x2={CHART_W} y2={CHART_H / 2}
          stroke="rgba(255,255,255,0.08)" strokeWidth={1} strokeDasharray="4 3" />
      </svg>
    )
  }

  const min   = Math.min(...prices)
  const max   = Math.max(...prices)
  const range = max - min || 1
  const n     = prices.length

  const pts = prices.map((p, i) => {
    const x = (i / (n - 1)) * CHART_W
    const y = CHART_H - ((p - min) / range) * (CHART_H - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })

  const line = up ? '#00E5FF' : '#BF00FF'
  const fill = up ? 'rgba(0,229,255,0.07)' : 'rgba(191,0,255,0.07)'
  const last = prices[n - 1]
  const lastY = CHART_H - ((last - min) / range) * (CHART_H - 4) - 2

  return (
    <svg width={CHART_W} height={CHART_H} viewBox={`0 0 ${CHART_W} ${CHART_H}`}>
      <polygon
        points={`0,${CHART_H} ${pts.join(' ')} ${CHART_W},${CHART_H}`}
        fill={fill}
      />
      <polyline
        points={pts.join(' ')}
        fill="none" stroke={line} strokeWidth={1.2}
        strokeLinejoin="round" strokeLinecap="round"
      />
      <circle cx={CHART_W} cy={lastY} r={2.5} fill={line}
        style={{ filter: `drop-shadow(0 0 4px ${line})` }} />
    </svg>
  )
}

// ── JARVIS detail panel ────────────────────────────────────────────────────────

interface PanelProps {
  ticker:  string
  hist:    number[]
  pct:     number | null
  row:     AlephRiskRow | undefined
  visible: boolean
}

function JarvisPanel({ ticker, hist, pct, row, visible }: PanelProps) {
  const vol      = volScore(hist)
  const sigLabel = row?.sig_score ?? '—'
  const sigConf  = row?.sig_confidence != null ? Math.round(row.sig_confidence * 100) : null
  const qScore   = row?.quant_score   != null ? Math.round(row.quant_score * 100)   : null
  const sScore   = row?.sentiment_score != null
    ? Math.round(((row.sentiment_score + 1) / 2) * 100)
    : null

  const sigColor = sigLabel === 'BUY' ? '#00E5FF' : sigLabel === 'SELL' ? '#BF00FF' : 'rgba(232,240,254,0.55)'

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          key={ticker}
          initial={{ height: 0, opacity: 0, marginTop: 0 }}
          animate={{ height: 'auto', opacity: 1, marginTop: 6 }}
          exit={{ height: 0, opacity: 0, marginTop: 0 }}
          transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
          style={{ overflow: 'hidden' }}
        >
          <div
            className="rounded-lg px-3 py-2.5"
            style={{
              background:  'rgba(0,229,255,0.035)',
              border:      '1px solid rgba(0,229,255,0.18)',
              boxShadow:   '0 0 18px rgba(0,229,255,0.10), inset 0 0 10px rgba(0,229,255,0.025)',
            }}
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-2">
              <span
                className="text-[9px] font-bold tracking-[0.15em] uppercase"
                style={{ color: '#00E5FF', textShadow: '0 0 8px rgba(0,229,255,0.6)' }}
              >
                {DISPLAY[ticker] ?? ticker} · INTEL
              </span>
              <span
                className="text-[8px] font-bold px-1.5 py-0.5 rounded"
                style={{
                  color:      sigColor,
                  border:     `1px solid ${sigColor}55`,
                  background: `${sigColor}11`,
                  textShadow: `0 0 6px ${sigColor}`,
                }}
              >
                {sigLabel}{sigConf != null ? ` · ${sigConf}%` : ''}
              </span>
            </div>

            {/* Metrics grid */}
            <div className="grid grid-cols-4 gap-2">
              {/* Volatility */}
              <div className="flex flex-col gap-0.5">
                <span className="text-[7.5px] text-[rgba(232,240,254,0.35)] tracking-wider uppercase">VOL·IDX</span>
                <span className="text-[11px] font-bold tabular-nums"
                  style={{ color: vol > 60 ? '#BF00FF' : vol > 30 ? '#FF9800' : '#00E5FF' }}>
                  {vol}
                </span>
                <div className="h-0.5 rounded-full bg-[rgba(255,255,255,0.08)] overflow-hidden">
                  <div className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${vol}%`,
                      background: vol > 60 ? '#BF00FF' : vol > 30 ? '#FF9800' : '#00E5FF',
                    }} />
                </div>
              </div>

              {/* Momentum */}
              <div className="flex flex-col gap-0.5">
                <span className="text-[7.5px] text-[rgba(232,240,254,0.35)] tracking-wider uppercase">MOMENTUM</span>
                <span className="text-[11px] font-bold tabular-nums text-[rgba(232,240,254,0.75)]">
                  {qScore != null ? qScore : '—'}
                </span>
                <span className="text-[7px] text-[rgba(232,240,254,0.3)]">
                  {row?.momentum ?? '—'}
                </span>
              </div>

              {/* Sentiment */}
              <div className="flex flex-col gap-0.5">
                <span className="text-[7.5px] text-[rgba(232,240,254,0.35)] tracking-wider uppercase">SENTIMENT</span>
                <span className="text-[11px] font-bold tabular-nums text-[rgba(232,240,254,0.75)]">
                  {sScore != null ? sScore : '—'}
                </span>
                <span className="text-[7px] text-[rgba(232,240,254,0.3)]">
                  {row?.sentiment ?? '—'}
                </span>
              </div>

              {/* Allocation */}
              <div className="flex flex-col gap-0.5">
                <span className="text-[7.5px] text-[rgba(232,240,254,0.35)] tracking-wider uppercase">ALLOC</span>
                <span className="text-[11px] font-bold tabular-nums"
                  style={{ color: '#00E5FF', textShadow: '0 0 6px rgba(0,229,255,0.5)' }}>
                  {Math.round(ALLOC * 100)}%
                </span>
                <span className="text-[7px] text-[rgba(232,240,254,0.3)]">EQ·WT</span>
              </div>
            </div>

            {/* Δ% reading */}
            {pct != null && (
              <div className="mt-1.5 pt-1.5 border-t border-[rgba(255,255,255,0.05)]
                text-[8px] text-[rgba(232,240,254,0.35)] flex gap-2">
                <span>Session Δ</span>
                <span style={{ color: pct >= 0 ? '#00E5FF' : '#BF00FF', fontWeight: 'bold' }}>
                  {pct >= 0 ? '+' : ''}{pct.toFixed(3)}%
                </span>
              </div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

interface Props {
  className?:  string
  riskMatrix?: AlephRiskRow[] | null
}

export default function LiveChart({ className = '', riskMatrix }: Props) {
  const { data, connected, priceHistory } = useMarketStream()
  const seededRef = useRef(false)
  const [hovered, setHovered] = useState<string | null>(null)

  useEffect(() => {
    if (seededRef.current) return
    seededRef.current = true
    Promise.allSettled(
      TICKERS.map((t) =>
        fetchJson<{ prices: number[] }>(`/api/mock/timeseries/${t}?points=${SEED_PTS}`)
      )
    ).catch(() => {})
  }, [])

  const portfolio = data?.portfolio_value
  const initialPrices: Record<string, number> = {}
  TICKERS.forEach((t) => {
    const h = priceHistory[t]
    if (h && h.length > 0) initialPrices[t] = h[0]
  })

  return (
    <div className={`glass-card p-3 flex flex-col gap-0 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <span className="label-dim text-[rgba(0,229,255,0.55)]">Live Portfolio · GBM Simulation</span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-1.5 h-1.5 rounded-full"
            style={{
              background: connected ? '#00E5FF' : '#FF5722',
              boxShadow:  connected ? '0 0 5px #00E5FF' : undefined,
              animation:  connected ? 'glow-pulse 2.5s ease-in-out infinite' : undefined,
            }}
          />
          <span className="text-[9px] text-[rgba(232,240,254,0.35)] tracking-widest">
            {connected ? 'LIVE' : 'CONNECTING…'}
          </span>
        </span>
      </div>

      {/* Ticker rows */}
      <div className="flex flex-col">
        {TICKERS.map((ticker) => {
          const hist    = priceHistory[ticker] ?? []
          const current = data?.prices[ticker] ?? (hist.length > 0 ? hist[hist.length - 1] : null)
          const first   = initialPrices[ticker] ?? hist[0]
          const pct     = first && current != null ? ((current - first) / first) * 100 : null
          const up      = pct == null ? true : pct >= 0
          const isHov   = hovered === ticker

          // Find matching riskMatrix row (internal code → display name)
          const matrixKey = TO_MATRIX[ticker] ?? ticker
          const row = riskMatrix?.find(r => r.ticker === matrixKey)

          return (
            <div key={ticker}>
              {/* ── Asset row ── */}
              <div
                className="flex items-center gap-2 py-2 px-2 rounded-lg cursor-default select-none"
                style={{
                  transition: 'background 0.25s ease, box-shadow 0.25s ease, transform 0.2s ease',
                  background: isHov ? 'rgba(0,229,255,0.045)' : 'transparent',
                  boxShadow:  isHov
                    ? '0 0 14px rgba(0,229,255,0.18), inset 0 0 10px rgba(0,229,255,0.03)'
                    : 'none',
                  transform:  isHov ? 'translateY(-1px)' : 'translateY(0)',
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                }}
                onMouseEnter={() => setHovered(ticker)}
                onMouseLeave={() => setHovered(null)}
              >
                {/* Ticker label */}
                <span
                  className="w-14 text-[9px] font-bold shrink-0 tracking-widest truncate transition-all duration-200"
                  style={{
                    color:      isHov ? '#00E5FF' : 'rgba(232,240,254,0.65)',
                    textShadow: isHov ? '0 0 8px rgba(0,229,255,0.6)' : 'none',
                  }}
                >
                  {DISPLAY[ticker] ?? ticker}
                </span>

                {/* Price */}
                <span className="w-[76px] text-[10px] tabular-nums shrink-0 transition-all duration-200"
                  style={{ color: isHov ? 'rgba(232,240,254,0.95)' : 'rgba(232,240,254,0.75)' }}>
                  {current != null ? formatPrice(ticker, current) : '···'}
                </span>

                {/* Δ% */}
                <span
                  className="w-[54px] text-[9px] tabular-nums shrink-0 font-mono font-bold"
                  style={{ color: up ? '#00E5FF' : '#BF00FF' }}
                >
                  {pct != null ? `${up ? '+' : ''}${pct.toFixed(2)}%` : '—'}
                </span>

                {/* Sparkline */}
                <div className="flex-1 min-w-0 flex justify-end">
                  <Sparkline prices={hist} up={up} />
                </div>
              </div>

              {/* ── JARVIS detail panel (slides in below hovered row) ── */}
              <JarvisPanel
                ticker={ticker}
                hist={hist}
                pct={pct}
                row={row}
                visible={isHov}
              />
              {/* visible prop drives AnimatePresence inside JarvisPanel */}
            </div>
          )
        })}
      </div>

      {/* Portfolio total */}
      <div className="flex justify-between items-center mt-2 pt-2
        border-t border-[rgba(255,255,255,0.06)] text-[9px]">
        <span className="text-[rgba(232,240,254,0.35)] tracking-wider">PORTFOLIO VALUE</span>
        <span className="tabular-nums font-bold"
          style={{ color: '#00E5FF', textShadow: '0 0 8px rgba(0,229,255,0.5)' }}>
          {portfolio != null
            ? `$${portfolio.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            : '···'}
        </span>
      </div>
    </div>
  )
}
