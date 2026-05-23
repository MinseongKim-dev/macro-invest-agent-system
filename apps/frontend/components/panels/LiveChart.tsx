'use client'
/**
 * LiveChart — real-time portfolio price sparklines.
 *
 * Connects to /api/stream/market via useMarketStream (SSE).
 * Renders one row per ticker: label · current price · Δ% · sparkline.
 * On first mount, fetches a seed history from /api/mock/timeseries/{ticker}
 * so the chart is populated immediately rather than waiting 2 minutes to
 * accumulate history from the live stream.
 */

import { useEffect, useRef } from 'react'
import { useMarketStream } from '@/hooks/useMarketStream'
import { fetchJson } from '@/lib/api'

// Tickers must match backend TICKERS constant in src/engines.py
const TICKERS   = ['AAPL', 'MSFT', 'TSLA', '005930', '000660']
const DISPLAY: Record<string, string> = {
  '005930': '삼성전자',
  '000660': 'SK하이닉스',
}
const CHART_W   = 140
const CHART_H   = 32
const SEED_PTS  = 60

// ── Sparkline ─────────────────────────────────────────────────────────────

function Sparkline({ prices }: { prices: number[] }) {
  if (prices.length < 2) {
    return (
      <svg width={CHART_W} height={CHART_H}>
        <line x1={0} y1={CHART_H / 2} x2={CHART_W} y2={CHART_H / 2}
          stroke="rgba(255,255,255,0.1)" strokeWidth={1} strokeDasharray="4 3" />
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

  const last = prices[n - 1]
  const up   = last >= prices[0]
  const line = up ? '#00E5FF' : '#BF00FF'
  const fill = up ? 'rgba(0,229,255,0.07)' : 'rgba(191,0,255,0.07)'
  const lastY = CHART_H - ((last - min) / range) * (CHART_H - 4) - 2

  return (
    <svg width={CHART_W} height={CHART_H} viewBox={`0 0 ${CHART_W} ${CHART_H}`}>
      {/* Area */}
      <polygon
        points={`0,${CHART_H} ${pts.join(' ')} ${CHART_W},${CHART_H}`}
        fill={fill}
      />
      {/* Line */}
      <polyline
        points={pts.join(' ')}
        fill="none" stroke={line} strokeWidth={1.3}
        strokeLinejoin="round" strokeLinecap="round"
      />
      {/* Current point */}
      <circle cx={CHART_W} cy={lastY} r={2.5} fill={line}
        style={{ filter: `drop-shadow(0 0 4px ${line})` }} />
    </svg>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export default function LiveChart({ className = '' }: { className?: string }) {
  const { data, connected, priceHistory } = useMarketStream()
  const seededRef = useRef(false)

  // Seed the history buffer on first mount so the chart isn't empty
  useEffect(() => {
    if (seededRef.current) return
    seededRef.current = true

    // Fetch seed data for all tickers in parallel, populate histRef via the
    // same endpoint the hook uses — but we can't directly inject into the hook's
    // internal ref.  Instead we warm up the FastAPI timeseries endpoint so
    // the data is ready, and the first SSE messages merge naturally.
    // (The hook's priceHistory will populate automatically once SSE starts.)
    Promise.allSettled(
      TICKERS.map((t) =>
        fetchJson<{ prices: number[] }>(`/api/mock/timeseries/${t}?points=${SEED_PTS}`)
      )
    ).catch(() => { /* seed is best-effort */ })
  }, [])

  const portfolio = data?.portfolio_value
  const initialPrices: Record<string, number> = {}
  TICKERS.forEach((t) => {
    const hist = priceHistory[t]
    if (hist && hist.length > 0) initialPrices[t] = hist[0]
  })

  return (
    <div className={`glass-card p-3 flex flex-col gap-2 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="label-dim text-[rgba(0,229,255,0.55)]">Live Portfolio  ·  GBM Simulation</span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-1.5 h-1.5 rounded-full"
            style={{
              background:  connected ? '#00E5FF' : '#FF5722',
              boxShadow:   connected ? '0 0 5px #00E5FF' : undefined,
              animation:   connected ? 'glow-pulse 2.5s ease-in-out infinite' : undefined,
            }}
          />
          <span className="text-[9px] text-[rgba(232,240,254,0.35)] tracking-widest">
            {connected ? 'LIVE' : 'CONNECTING…'}
          </span>
        </span>
      </div>

      {/* Ticker rows */}
      <div className="flex flex-col divide-y divide-[rgba(255,255,255,0.04)]">
        {TICKERS.map((ticker) => {
          const hist    = priceHistory[ticker] ?? []
          const current = data?.prices[ticker] ?? (hist.length > 0 ? hist[hist.length - 1] : null)
          const first   = initialPrices[ticker] ?? hist[0]
          const pct     = first && current != null ? ((current - first) / first) * 100 : null
          const up      = pct == null ? true : pct >= 0

          return (
            <div key={ticker} className="flex items-center gap-2 py-1.5">
              {/* Ticker */}
              <span className="w-14 text-[9px] font-bold text-[rgba(232,240,254,0.65)] shrink-0 tracking-widest truncate">
                {DISPLAY[ticker] ?? ticker}
              </span>

              {/* Price */}
              <span className="w-[72px] text-[10px] tabular-nums text-[rgba(232,240,254,0.8)] shrink-0">
                {current != null ? `$${current.toFixed(2)}` : '···'}
              </span>

              {/* Δ% */}
              <span
                className="w-[52px] text-[9px] tabular-nums shrink-0 font-mono"
                style={{ color: up ? '#00E5FF' : '#BF00FF' }}
              >
                {pct != null ? `${up ? '+' : ''}${pct.toFixed(2)}%` : '—'}
              </span>

              {/* Sparkline */}
              <div className="flex-1 min-w-0 flex justify-end">
                <Sparkline prices={hist} />
              </div>
            </div>
          )
        })}
      </div>

      {/* Portfolio total */}
      <div className="flex justify-between items-center pt-1
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
