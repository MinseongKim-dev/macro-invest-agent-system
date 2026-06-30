'use client'
import { useState, useEffect, useMemo, useRef } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'
import { useAlephStream } from '@/hooks/useAlephStream'
import { useMarketStream } from '@/hooks/useMarketStream'
import { useNewsStream } from '@/hooks/useNewsStream'
import { useRegime, useSignals } from '@/hooks/useAlephData'
import { ResearchPanel } from '@/components/ResearchPanel'
import { DetailPanel, type TickerDetail } from '@/components/DetailPanel'
import type { AlephStreamData, ExternalEventDTO } from '@/lib/types'

// ─── Version ──────────────────────────────────────────────────────────────────
export const APP_VERSION = 'v0.4.2'

// ─── Global Styles ────────────────────────────────────────────────────────────
const STYLES = `
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&family=Rajdhani:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;700&display=swap');
*{box-sizing:border-box;}
@keyframes glow-pulse{0%,100%{opacity:1}50%{opacity:.6}}
@keyframes blink{0%,100%{opacity:1}49%{opacity:1}50%,99%{opacity:0}}
@keyframes float-pt{0%{transform:translateY(0) scale(1);opacity:0}10%{opacity:.7}85%{opacity:.4}100%{transform:translateY(-100vh) scale(.5);opacity:0}}
@keyframes slide-up{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
@keyframes widget-pop{from{opacity:0;transform:translateX(18px) scale(.96)}to{opacity:1;transform:translateX(0) scale(1)}}
@keyframes orbit-spin{from{transform:translate(-50%,-50%) rotateX(72deg) rotateZ(0deg)}to{transform:translate(-50%,-50%) rotateX(72deg) rotateZ(360deg)}}
@keyframes holo-scan{0%{top:-2px}100%{top:102%}}

.glass{background:rgba(2,12,30,.78);backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px);border:1px solid rgba(0,229,255,.12);border-radius:12px;}
.glass-hi{background:rgba(0,25,55,.82);backdrop-filter:blur(22px);border:1px solid rgba(0,229,255,.22);border-radius:12px;}

.omni-input{background:transparent;border:none;outline:none;font-family:'JetBrains Mono',monospace;font-size:13px;color:#00e5ff;width:100%;caret-color:#00e5ff;}
.omni-input::placeholder{color:rgba(0,229,255,.28);}
.omni-input:disabled{opacity:.5;}

.cell-hover{cursor:pointer;transition:transform .18s,box-shadow .18s;}
.cell-hover:hover{transform:scale(1.07);z-index:5;}
.row-hover{transition:background .15s;border-radius:6px;cursor:pointer;}
.row-hover:hover{background:rgba(0,229,255,.05);}
.news-hover{transition:background .15s;border-radius:6px;cursor:pointer;}
.news-hover:hover{background:rgba(0,229,255,.04);}

.ai-w{animation:widget-pop .38s ease-out both;}
.ai-w:nth-child(2){animation-delay:.08s}
.ai-w:nth-child(3){animation-delay:.16s}
.ai-w:nth-child(4){animation-delay:.24s}
.ai-w:nth-child(5){animation-delay:.32s}

::-webkit-scrollbar{width:3px;height:3px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(0,229,255,.18);border-radius:2px}

.report-scroll::-webkit-scrollbar{width:3px}
.report-scroll::-webkit-scrollbar-thumb{background:rgba(168,85,247,.3);border-radius:2px}
`

// ─── Types ────────────────────────────────────────────────────────────────────

interface Widget {
  type:   'metric' | 'alert'
  title:  string
  value?: string
  sub?:   string
  trend?: 'up' | 'down' | 'neutral'
  level?: 'HIGH' | 'MED' | 'LOW'
  text?:  string
}

interface RespState {
  insight:    string
  action:     string
  confidence: number
  report?:    string
  widgets:    Widget[]
}

interface Sector   { n: string; c: number }
interface Particle { l: number; d: number; dur: number; s: number }

// ─── Static config ────────────────────────────────────────────────────────────

// Metadata stays static; prices come from the market stream
const TICKER_META: Record<string, { n: string; t: string; col: string; group: 'STOCK' | 'ETF' }> = {
  'AAPL':   { n: 'AAPL',      t: 'AAPL US',   col: '#ff9800', group: 'STOCK' },
  'MSFT':   { n: 'MSFT',      t: 'MSFT US',   col: '#00ff88', group: 'STOCK' },
  'TSLA':   { n: 'TESLA',     t: 'TSLA US',   col: '#ffaa00', group: 'STOCK' },
  '005930': { n: '삼성전자',   t: '005930 KS', col: '#00e5ff', group: 'STOCK' },
  '000660': { n: 'SK하이닉스', t: '000660 KS', col: '#a855f7', group: 'STOCK' },
  '035420': { n: 'NAVER',     t: '035420 KS', col: '#4ade80', group: 'STOCK' },
  '051910': { n: 'LG화학',    t: '051910 KS', col: '#fb923c', group: 'STOCK' },
  '006400': { n: '삼성SDI',   t: '006400 KS', col: '#f472b6', group: 'STOCK' },
  '122630': { n: 'KODEX LEV', t: '122630 KS', col: '#a78bfa', group: 'ETF'   },
  'QQQ':    { n: 'QQQ ETF',   t: 'QQQ US',    col: '#22d3ee', group: 'ETF'   },
  'BND':    { n: 'BND ETF',   t: 'BND US',    col: '#86efac', group: 'ETF'   },
  'GLD':    { n: 'GLD ETF',   t: 'GLD US',    col: '#fcd34d', group: 'ETF'   },
}
const TICKER_ORDER = ['AAPL', 'MSFT', 'TSLA', '005930', '000660', '035420', '051910', '006400', '122630', 'QQQ', 'BND', 'GLD']
const ETF_TICKERS  = ['QQQ', 'BND', 'GLD']


const SECTORS: Sector[] = [
  { n: 'SEMI', c: +4.5 }, { n: 'ENERGY', c: -3.9 }, { n: 'TELECOM', c: +2.1 },
  { n: 'FINANCE', c: +1.3 }, { n: 'CONSUMER', c: -0.5 }, { n: 'HEALTH', c: +3.2 },
  { n: 'MATERIALS', c: -2.1 }, { n: 'IT', c: +5.7 }, { n: 'UTILITIES', c: -0.8 },
]

const PARTICLES: Particle[] = [
  { l: 8,  d: 0,   dur: 18, s: 1.5 }, { l: 18, d: 3.2, dur: 22, s: 1 },
  { l: 32, d: 1.1, dur: 17, s: 2   }, { l: 47, d: 5.5, dur: 20, s: 1 },
  { l: 58, d: 2.4, dur: 25, s: 1.5 }, { l: 71, d: 0.7, dur: 19, s: 2 },
  { l: 82, d: 4.1, dur: 23, s: 1   }, { l: 91, d: 1.8, dur: 16, s: 1.5 },
  { l: 24, d: 6.2, dur: 21, s: 1   }, { l: 65, d: 3.7, dur: 24, s: 2   },
]

const CHART_MAX_PTS = 120  // 2 min rolling window for portfolio chart

// ─── Typewriter hook ──────────────────────────────────────────────────────────

function useTypingText(text: string | undefined, speed = 12): string {
  const [displayed, setDisplayed] = useState('')
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    if (!text) { setDisplayed(''); return }
    setDisplayed('')
    let i = 0
    timerRef.current = setInterval(() => {
      i++
      setDisplayed(text.slice(0, i))
      if (i >= text.length && timerRef.current) clearInterval(timerRef.current)
    }, speed)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [text, speed])

  return displayed
}

// ─── Small sub-components ─────────────────────────────────────────────────────

const SBadge = ({ type }: { type: 'POS' | 'NEG' | 'NEU' }) => {
  const m = { POS: ['#00ff88', '▲'] as const, NEG: ['#ff4d6d', '▼'] as const, NEU: ['#fbbf24', '◆'] as const }
  const [col, ic] = m[type] ?? ['#888', '•']
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      width: 18, height: 18, borderRadius: 4, flexShrink: 0,
      background: `${col}18`, border: `1px solid ${col}44`,
      color: col, fontSize: 7,
    }}>{ic}</span>
  )
}

// MiniSpark uses real price history when provided, random fallback when not
const MiniSpark = ({ up = true, prices }: { up?: boolean; prices?: number[] }) => {
  const data = useMemo(() => {
    if (prices && prices.length >= 2) {
      const slice = prices.slice(-18)
      const min = Math.min(...slice)
      const max = Math.max(...slice)
      const range = max - min || 1
      return slice.map(v => ({ v: ((v - min) / range) * 70 + 15 }))
    }
    const d: Array<{ v: number }> = []
    let v = 50
    for (let i = 0; i < 18; i++) {
      v += (Math.random() - (up ? 0.42 : 0.58)) * 9
      v = Math.max(15, Math.min(85, v))
      d.push({ v })
    }
    return d
  }, [prices, up])

  return (
    <div style={{ width: 56, height: 22, flexShrink: 0 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 1, right: 1, left: 1, bottom: 1 }}>
          <Area type="monotone" dataKey="v"
            stroke={up ? '#00ff88' : '#ff4d6d'}
            fill={up ? 'rgba(0,255,136,.12)' : 'rgba(255,77,109,.12)'}
            strokeWidth={1.5} dot={false} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

const PBar = ({ lbl, pct, col }: { lbl: string; pct: string; col: string }) => (
  <div style={{ marginBottom: 7 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
      <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, letterSpacing: '1px', color: 'rgba(255,255,255,.4)' }}>{lbl}</span>
      <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: col }}>{pct}</span>
    </div>
    <div style={{ height: 2, borderRadius: 2, background: 'rgba(255,255,255,.06)' }}>
      <div style={{ height: '100%', width: pct, borderRadius: 2, background: col, boxShadow: `0 0 5px ${col}`, transition: 'width 1.2s ease' }} />
    </div>
  </div>
)

const MacroStat = ({ lbl, val, col }: { lbl: string; val: string; col?: string }) => (
  <div style={{ marginBottom: 9 }}>
    <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, letterSpacing: '1.5px', color: 'rgba(0,229,255,.45)', textTransform: 'uppercase', marginBottom: 1 }}>{lbl}</div>
    <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 17, fontWeight: 700, color: col ?? '#00e5ff', textShadow: `0 0 10px ${col ?? '#00e5ff'}55` }}>{val}</div>
  </div>
)

const Globe = () => (
  <div style={{ position: 'relative', width: 128, height: 128, flexShrink: 0 }}>
    <div style={{
      width: 128, height: 128, borderRadius: '50%',
      background: 'radial-gradient(circle at 36% 34%, rgba(0,80,180,.65), rgba(0,8,30,.97))',
      border: '1px solid rgba(0,229,255,.22)',
      boxShadow: '0 0 30px rgba(0,80,200,.25), inset 0 0 40px rgba(0,0,60,.6)',
      position: 'relative', overflow: 'hidden',
    }}>
      {[21, 42, 64, 85, 107].map((y, i) => (
        <div key={i} style={{ position: 'absolute', top: y, left: 0, right: 0, height: 1, background: 'rgba(0,229,255,.1)' }} />
      ))}
      {[21, 42, 64, 85, 107].map((x, i) => (
        <div key={i} style={{ position: 'absolute', left: x, top: 0, bottom: 0, width: 1, background: 'rgba(0,229,255,.1)' }} />
      ))}
      <div style={{
        position: 'absolute', left: 0, right: 0, height: 1.5,
        background: 'linear-gradient(90deg,transparent,rgba(0,229,255,.5),transparent)',
        animation: 'holo-scan 3s linear infinite', top: 0,
      }} />
      {[{ t: '26%', l: '20%', d: 0 }, { t: '50%', l: '60%', d: 0.6 }, { t: '68%', l: '36%', d: 1.2 }, { t: '33%', l: '76%', d: 0.9 }].map((p, i) => (
        <div key={i} style={{
          position: 'absolute', top: p.t, left: p.l,
          width: 5, height: 5, borderRadius: '50%',
          background: '#00e5ff',
          boxShadow: '0 0 7px #00e5ff, 0 0 14px rgba(0,229,255,.4)',
          animation: `glow-pulse 1.8s ${p.d}s ease-in-out infinite`,
        }} />
      ))}
      <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', background: 'radial-gradient(circle at 68% 68%, transparent 38%, rgba(0,5,18,.55) 100%)' }} />
    </div>
    <div style={{
      position: 'absolute', top: '50%', left: '50%',
      width: 158, height: 158, borderRadius: '50%',
      border: '1px solid rgba(0,229,255,.18)',
      animation: 'orbit-spin 14s linear infinite',
    }} />
  </div>
)

const HCell = ({ n, c }: { n: string; c: number }) => {
  const pos = c >= 0
  const int = Math.min(Math.abs(c) / 6, 1)
  const base = pos ? '0,255,136' : '255,77,109'
  return (
    <div className="cell-hover" style={{
      background: `rgba(${base},${(0.12 + int * 0.42).toFixed(2)})`,
      border: `1px solid rgba(${base},${(0.3 + int * 0.3).toFixed(2)})`,
      borderRadius: 7, padding: '5px 7px',
      display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
    }}>
      <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, letterSpacing: '1px', color: 'rgba(255,255,255,.65)', textTransform: 'uppercase' }}>{n}</div>
      <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 11, fontWeight: 700, color: pos ? '#00ff88' : '#ff4d6d' }}>{pos ? '+' : ''}{c}%</div>
    </div>
  )
}

const AIWidget = ({ w, idx }: { w: Widget; idx: number }) => (
  <div className="ai-w glass" style={{ padding: '10px 14px', minWidth: 120, flex: 1, animationDelay: `${idx * 0.08}s` }}>
    <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, letterSpacing: '1.5px', color: 'rgba(0,229,255,.45)', marginBottom: 4, textTransform: 'uppercase' }}>{w.title}</div>
    {w.type === 'metric' && (
      <>
        <div style={{
          fontFamily: "'Orbitron',sans-serif", fontSize: 16, fontWeight: 700,
          color: w.trend === 'up' ? '#00ff88' : w.trend === 'down' ? '#ff4d6d' : '#00e5ff',
          textShadow: `0 0 10px ${w.trend === 'up' ? 'rgba(0,255,136,.4)' : w.trend === 'down' ? 'rgba(255,77,109,.4)' : 'rgba(0,229,255,.4)'}`,
        }}>{w.value}</div>
        {w.sub && <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: 'rgba(255,255,255,.32)', marginTop: 2 }}>{w.sub}</div>}
      </>
    )}
    {w.type === 'alert' && (
      <div style={{
        fontFamily: "'Rajdhani',sans-serif", fontSize: 11, color: 'rgba(255,255,255,.7)',
        lineHeight: 1.45,
        borderLeft: `2px solid ${w.level === 'HIGH' ? '#ff4d6d' : w.level === 'MED' ? '#fbbf24' : '#00ff88'}`,
        paddingLeft: 8, marginTop: 4,
      }}>{w.text}</div>
    )}
  </div>
)

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export default function AlephDashboard() {
  const [now,         setNow]         = useState(new Date())
  const [query,       setQuery]       = useState('')
  const [busy,        setBusy]        = useState(false)
  const [resp,        setResp]        = useState<RespState | null>(null)
  const [panelOpen,   setPanelOpen]   = useState(false)
  const [panelContent,setPanelContent]= useState('')
  const [panelMeta,   setPanelMeta]   = useState<{ regime?: string; phase?: string; confidence?: number; signal?: string; health?: number } | undefined>()
  const [streaming,   setStreaming]   = useState(false)
  const [panelQuery,  setPanelQuery]  = useState('')
  const [assetTab,    setAssetTab]    = useState<'ALL' | 'STOCKS' | 'ETFS' | 'FUNDS'>('ALL')
  const [detailOpen,  setDetailOpen]  = useState(false)
  const [detailTicker,setDetailTicker]= useState<TickerDetail | null>(null)
  const [detailNews,  setDetailNews]  = useState<ExternalEventDTO | null>(null)
  const [activeIndex, setActiveIndex] = useState<'PORTFOLIO' | 'KOSPI' | 'SP500' | 'USDKRW'>('PORTFOLIO')
  const [indexHistory, setIndexHistory] = useState<Record<string, Array<{t: number; v: number}>>>({})
  const indexIdxRef = useRef(0)

  // ── Real backend data ──────────────────────────────────────────────────────
  const { data: streamData }                          = useAlephStream()
  const { data: marketTick, connected, priceHistory } = useMarketStream()
  const liveNews                                      = useNewsStream(15)
  const { data: regimeData, isLoading: regimeLoading, error: regimeError } = useRegime()
  const { data: signalsData, isLoading: signalsLoading }                   = useSignals()

  // Portfolio value rolling history → drives the KRX chart
  const [chartData, setChartData] = useState<Array<{ t: number; v: number }>>([])
  const chartIdxRef = useRef(0)

  useEffect(() => {
    if (marketTick?.portfolio_value == null) return
    setChartData(prev => {
      const next = [...prev, { t: chartIdxRef.current++, v: marketTick.portfolio_value }]
      return next.length > CHART_MAX_PTS ? next.slice(-CHART_MAX_PTS) : next
    })
    console.debug('[AlephDashboard] portfolio_value tick', marketTick.portfolio_value.toFixed(2))
  }, [marketTick?.portfolio_value])

  useEffect(() => {
    const indices = (streamData as AlephStreamData & { market_indices?: Record<string, number> })?.market_indices
    if (!indices) return
    setIndexHistory(prev => {
      const next = { ...prev }
      Object.entries(indices).forEach(([id, val]) => {
        const arr = [...(prev[id] ?? []), { t: indexIdxRef.current, v: val }]
        next[id] = arr.length > CHART_MAX_PTS ? arr.slice(-CHART_MAX_PTS) : arr
      })
      indexIdxRef.current++
      return next
    })
  }, [streamData])

  // Asset-tab filtered ticker list (FUNDS tab deferred — no feed yet)
  const filteredOrder = useMemo(() => {
    if (assetTab === 'STOCKS') return TICKER_ORDER.filter(t => !ETF_TICKERS.includes(t))
    if (assetTab === 'ETFS')   return ETF_TICKERS
    if (assetTab === 'FUNDS')  return []   // pipeline not yet open
    return TICKER_ORDER
  }, [assetTab])

  // Live holdings derived from market stream — filtered by active tab
  const holdings = useMemo(() => filteredOrder.map(ticker => {
    const meta    = TICKER_META[ticker]
    const prices  = priceHistory[ticker] ?? []
    const current = marketTick?.prices[ticker] ?? prices[prices.length - 1] ?? null
    const first   = prices[0] ?? null
    const pct     = first && current ? ((current - first) / first) * 100 : 0
    return {
      ...meta,
      ticker,
      chg:    current ? `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%` : '···',
      dir:    pct >= 0 ? 1 : -1,
      prices,
      current,
    }
  }), [filteredOrder, marketTick, priceHistory])

  // Live algorithmic signals from SSE stream
  const liveSignals = useMemo(() => {
    const sigs = streamData?.active_signals ?? []
    if (sigs.length === 0) return null
    return sigs.slice(0, 3).map((s, i) => ({
      sig:   s.action as string,
      asset: ['KOSPI 200', 'USD / KRW', 'ENERGY XTF'][i] ?? `SIGNAL-${i}`,
      conf:  Math.round(s.probability * 100),
      desc:  s.strategy,
    }))
  }, [streamData?.active_signals])

  // Derived values — SSE stream takes priority; REST endpoint is the fallback
  const regimeLabel     = streamData?.macro_regime?.regime_name ?? regimeData?.regime_label ?? (regimeLoading ? '···' : null)
  const portfolioHealth = streamData?.portfolio_health?.score   ?? null

  // Trust metadata from /api/signals/latest
  const trust            = signalsData?.trust
  const trustFreshness   = trust?.freshness_status ?? (signalsLoading ? '···' : '—')
  const trustAvailability = trust?.availability    ?? '—'
  const trustDegraded    = trust?.is_degraded ?? (!signalsData && !!regimeError)

  const kospi  = streamData?.market_indices?.KOSPI  ?? null
  const sp500  = streamData?.market_indices?.SP500   ?? null
  const usdkrw = streamData?.market_indices?.USDKRW  ?? null

  // ── Typewriter for OMNI insight + report ──────────────────────────────────
  const typedInsight = useTypingText(resp?.insight, 14)
  const typedReport  = useTypingText(resp?.report,  8)

  // Inject global styles once
  useEffect(() => {
    const el = document.createElement('style')
    el.textContent = STYLES
    document.head.appendChild(el)
    return () => { document.head.removeChild(el) }
  }, [])

  // Clock
  useEffect(() => {
    const id = setInterval(() => {
      setNow(new Date())
    }, 1000)
    return () => clearInterval(id)
  }, [])

  const pad = (n: number) => String(n).padStart(2, '0')
  const ts  = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`

  // ── OMNI-COMMAND — SSE streaming + ResearchPanel ─────────────────────────
  const exec = async () => {
    if (!query.trim() || busy) return
    setBusy(true)
    setResp(null)
    setPanelContent('')
    setPanelMeta(undefined)
    setPanelQuery(query)
    setPanelOpen(true)
    setDetailOpen(false)
    setStreaming(true)

    try {
      const r = await fetch('/api/v1/intelligence/command/stream', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ query, persona: 'AGGRESSIVE' }),
      })
      if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`)

      const reader  = r.body.getReader()
      const decoder = new TextDecoder()
      let   buffer  = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === 'meta') {
              const regime = evt.macro_regime ?? {}
              const health = evt.portfolio_health ?? {}
              const sig    = (evt.active_signals ?? [])[0]
              setPanelMeta({
                regime:     regime.regime_name,
                phase:      regime.market_phase,
                confidence: regime.confidence_score,
                signal:     sig?.action,
                health:     health.score,
              })
              // Also update inline widgets
              const widgets: Widget[] = []
              if (regime.regime_name) widgets.push({ type: 'metric', title: 'MACRO REGIME',     value: regime.regime_name,               sub: regime.market_phase ?? '',  trend: (regime.confidence_score ?? 0.5) > 0.7 ? 'up' : 'down' })
              if (health.score != null) widgets.push({ type: 'metric', title: 'PORTFOLIO HEALTH', value: `${Math.round(health.score)}`, sub: health.source ?? '', trend: health.score > 60 ? 'up' : 'down' })
              setResp({ insight: regime.regime_name ?? 'Analysis complete.', action: sig?.action ?? '', confidence: Math.round((sig?.probability ?? 0.5) * 100), report: '', widgets })
            } else if (evt.type === 'token') {
              setPanelContent(prev => prev + (evt.content ?? ''))
            } else if (evt.type === 'done') {
              setStreaming(false)
            }
          } catch {
            // malformed SSE line — skip
          }
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'NETWORK ERROR'
      setPanelContent(`NEURAL LINK ERROR — ${msg}`)
      setResp({ insight: `NEURAL LINK ERROR — ${msg}`, action: '', confidence: 0, report: '', widgets: [] })
    } finally {
      setBusy(false)
      setStreaming(false)
      setQuery('')
    }
  }

  const openTickerDetail = (h: TickerDetail) => {
    setPanelOpen(false)
    setDetailNews(null)
    setDetailTicker(h)
    setDetailOpen(true)
  }

  const openNewsDetail = (item: ExternalEventDTO) => {
    setPanelOpen(false)
    setDetailTicker(null)
    setDetailNews(item)
    setDetailOpen(true)
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ width: '100vw', height: '100vh', background: '#020b18', display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>
      <ResearchPanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        streaming={streaming}
        content={panelContent}
        meta={panelMeta}
        query={panelQuery}
      />
      <DetailPanel
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        ticker={detailTicker}
        news={detailNews}
      />

      {/* BG grid */}
      <div style={{
        position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none',
        backgroundImage: 'linear-gradient(rgba(0,229,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,229,255,.025) 1px,transparent 1px)',
        backgroundSize: '44px 44px',
      }} />
      <div style={{ position: 'absolute', top: -160, left: '18%', right: '18%', height: 380, background: 'radial-gradient(ellipse,rgba(0,40,130,.22) 0%,transparent 70%)', zIndex: 0, pointerEvents: 'none' }} />
      <div style={{ position: 'absolute', inset: 0, zIndex: 1, pointerEvents: 'none', background: 'repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.025) 2px,rgba(0,0,0,.025) 4px)' }} />
      {PARTICLES.map((p, i) => (
        <div key={i} style={{ position: 'absolute', left: `${p.l}%`, bottom: 0, zIndex: 2, pointerEvents: 'none', width: p.s, height: p.s, borderRadius: '50%', background: 'rgba(0,229,255,.5)', boxShadow: '0 0 4px rgba(0,229,255,.4)', animation: `float-pt ${p.dur}s ${p.d}s linear infinite` }} />
      ))}

      {/* ══ TOP HEADER ══════════════════════════════════════════════════════════ */}
      <div style={{ zIndex: 10, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '7px 18px', borderBottom: '1px solid rgba(0,229,255,.09)', background: 'rgba(2,8,20,.93)', backdropFilter: 'blur(12px)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#00e5ff', boxShadow: '0 0 8px #00e5ff', animation: 'glow-pulse 2s ease-in-out infinite' }} />
            <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 13, fontWeight: 900, color: '#00e5ff', letterSpacing: '3.5px', textShadow: '0 0 18px rgba(0,229,255,.7)' }}>ALEPH-ONE</span>
            <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, letterSpacing: '2px', color: 'rgba(0,229,255,.35)', marginLeft: 3 }}>CORE {APP_VERSION}</span>
          </div>
          {/* Regime badge — SSE stream first, REST fallback, loading state */}
          {(regimeLabel || regimeLoading) && (
            <div style={{
              padding: '2px 8px', borderRadius: 4,
              background: regimeError ? 'rgba(255,71,87,.07)' : 'rgba(0,229,255,.07)',
              border: `1px solid ${regimeError ? 'rgba(255,71,87,.3)' : 'rgba(0,229,255,.22)'}`,
              fontFamily: "'Rajdhani',sans-serif", fontSize: 8, letterSpacing: '1.5px',
              color: regimeError ? '#FF4757' : '#00e5ff', textTransform: 'uppercase',
            }}>
              {regimeError ? 'REGIME ERR' : (regimeLabel ?? '···')}
            </div>
          )}
          {/* Index tickers — live from SSE stream market_indices */}
          <div style={{ display: 'flex', gap: 18, marginLeft: 12 }}>
            {([['KOSPI', kospi != null ? kospi.toLocaleString('en-US', {maximumFractionDigits: 2}) : '···'], ['S&P 500', sp500 != null ? sp500.toLocaleString('en-US', {maximumFractionDigits: 2}) : '···'], ['USD/KRW', usdkrw != null ? usdkrw.toFixed(1) : '···']] as [string, string][]).map(([l, v]) => (
              <div key={l} style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, letterSpacing: '1px', color: 'rgba(255,255,255,.32)' }}>{l}</span>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 11, fontWeight: 500, color: '#00e5ff' }}>{v}</span>
              </div>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          {/* Stream status dot */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', background: connected ? '#00ff88' : '#ff4d6d', boxShadow: connected ? '0 0 6px #00ff88' : 'none', animation: connected ? 'blink 1.2s step-end infinite' : 'none' }} />
            <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, letterSpacing: '1.5px', color: connected ? 'rgba(0,255,136,.7)' : 'rgba(255,77,109,.7)' }}>{connected ? 'LIVE' : 'RECONNECTING'}</span>
          </div>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 12, color: 'rgba(0,229,255,.65)', letterSpacing: '1px' }}>{ts}</span>
          <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, letterSpacing: '1.5px', color: 'rgba(255,255,255,.22)' }}>KST UTC+9</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 10px', borderRadius: 20, background: 'rgba(0,229,255,.07)', border: '1px solid rgba(0,229,255,.18)' }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#00ff88', boxShadow: '0 0 5px #00ff88' }} />
            <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, color: '#00e5ff', letterSpacing: '1px' }}>KIM MIN-SEONG</span>
          </div>
        </div>
      </div>

      {/* ══ MAIN BODY ═══════════════════════════════════════════════════════════ */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', zIndex: 5, minHeight: 0 }}>

        {/* ── LEFT PANEL ─────────────────────────────────────────────────────── */}
        <div style={{ width: 272, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 7, padding: '9px 8px 9px 12px', borderRight: '1px solid rgba(0,229,255,.07)', overflowY: 'auto' }}>

          {/* NEWS FEED */}
          <div className="glass" style={{ padding: 12, display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 9 }}>
              <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#00ff88', boxShadow: '0 0 5px #00ff88', animation: 'blink 1.2s step-end infinite' }} />
              <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: '#00e5ff' }}>NEWS FEED</span>
              <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.22)', marginLeft: 'auto', letterSpacing: '1px' }}>HEADLINES | SENTIMENT</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7, maxHeight: 220, overflowY: 'auto' }}>
              {liveNews.length > 0
                ? liveNews.map((item, i) => {
                    const s: 'POS' | 'NEG' | 'NEU' = item.metadata?.sentiment === 'positive' ? 'POS'
                      : item.metadata?.sentiment === 'negative' ? 'NEG' : 'NEU'
                    const age = item.published_at
                      ? new Date(item.published_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
                      : '—'
                    return (
                      <div key={item.event_id ?? i} className="news-hover" onClick={() => openNewsDetail(item)} style={{ display: 'flex', gap: 7, padding: '5px 4px' }}>
                        <SBadge type={s} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 10.5, color: 'rgba(255,255,255,.72)', lineHeight: 1.45, fontFamily: "'Rajdhani',sans-serif", overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{item.title}</div>
                        </div>
                        <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(255,255,255,.2)', flexShrink: 0 }}>{age}</div>
                      </div>
                    )
                  })
                : /* 백엔드 이벤트 없을 때 placeholder */
                  [
                    { s: 'NEU' as const, txt: 'Connecting to live event stream…', age: '' },
                  ].map((item, i) => (
                    <div key={i} className="news-hover" style={{ display: 'flex', gap: 7, padding: '5px 4px' }}>
                      <SBadge type={item.s} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 10.5, color: 'rgba(255,255,255,.35)', lineHeight: 1.45, fontFamily: "'Rajdhani',sans-serif" }}>{item.txt}</div>
                      </div>
                    </div>
                  ))
              }
            </div>
          </div>

          {/* ALTERNATIVE DATA */}
          <div className="glass" style={{ padding: 12 }}>
            <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: '#00e5ff', marginBottom: 2 }}>ALTERNATIVE DATA</div>
            <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.25)', letterSpacing: '1px', marginBottom: 8 }}>COMMODITY PRICES | SHIPPING DATA</div>
            {/* Mini chart uses portfolio history when available */}
            <div style={{ height: 48, marginBottom: 8 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData.slice(-20)} margin={{ top: 1, right: 1, left: 1, bottom: 1 }}>
                  <Area type="monotone" dataKey="v" stroke="rgba(0,229,255,.5)" fill="rgba(0,229,255,.05)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            {([['CL1:COM', 'Crude Oil', '+1.50%', 1], ['BR2:COM', 'Brent Oil', '-0.93%', -1], ['BDI:IND', 'Baltic Dry', '+0.38%', 1]] as const).map(([code, name, val, dir]) => (
              <div key={code} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '3px 0', borderTop: '1px solid rgba(255,255,255,.04)' }}>
                <div>
                  <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'rgba(255,255,255,.45)' }}>{code}</div>
                  <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, color: 'rgba(255,255,255,.25)' }}>{name}</div>
                </div>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 11, fontWeight: 600, color: dir > 0 ? '#00ff88' : '#ff4d6d', textShadow: dir > 0 ? '0 0 6px rgba(0,255,136,.45)' : '0 0 6px rgba(255,77,109,.45)' }}>{val}</span>
              </div>
            ))}
          </div>

          {/* ALGORITHMIC SIGNALS — live from SSE stream */}
          <div className="glass" style={{ padding: 12, flex: 1 }}>
            <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: '#00e5ff', marginBottom: 10 }}>ALGORITHMIC SIGNALS</div>
            {(liveSignals ?? [
              { sig: 'BUY',  asset: 'KOSPI 200',  conf: 78, desc: 'Momentum breakout confirmed — trend continuation pattern.' },
              { sig: 'HOLD', asset: 'USD / KRW',  conf: 53, desc: 'Algorithmic consensus: consolidation phase, range-bound.' },
              { sig: 'SELL', asset: 'ENERGY XTF', conf: 66, desc: 'Bearish divergence detected; sector rotation underway.' },
            ]).map((s, i) => {
              const col = s.sig === 'BUY' || s.sig === 'buy' ? '#00ff88' : s.sig === 'SELL' || s.sig === 'sell' ? '#ff4d6d' : '#fbbf24'
              return (
                <div key={i} style={{ marginBottom: 8, padding: '8px 10px', background: 'rgba(0,229,255,.03)', border: '1px solid rgba(0,229,255,.09)', borderRadius: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '1px', color: col, background: `${col}18`, border: `1px solid ${col}44`, padding: '2px 6px', borderRadius: 4 }}>{s.sig.toUpperCase()}</span>
                    <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: '#00e5ff' }}>{s.asset}</span>
                    <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'rgba(255,255,255,.28)', marginLeft: 'auto' }}>{s.conf}%</span>
                  </div>
                  <div style={{ fontSize: 9.5, color: 'rgba(255,255,255,.42)', fontFamily: "'Rajdhani',sans-serif", lineHeight: 1.4 }}>{s.desc}</div>
                  <div style={{ height: 2, borderRadius: 1, background: 'rgba(255,255,255,.06)', marginTop: 6 }}>
                    <div style={{ height: '100%', width: `${s.conf}%`, borderRadius: 1, background: col, boxShadow: `0 0 4px ${col}` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* ── CENTER PANEL ────────────────────────────────────────────────────── */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 7, padding: '9px 8px', overflow: 'hidden', minWidth: 0 }}>

          {/* GLOBAL MACRO card */}
          <div className="glass" style={{ padding: 14, flexShrink: 0 }}>
            <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 10, fontWeight: 700, letterSpacing: '2px', color: '#00e5ff', marginBottom: 12 }}>GLOBAL MACRO &amp; MARKET OVERVIEW</div>
            <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
              <div style={{ width: 96, flexShrink: 0 }}>
                <MacroStat lbl="VIX" val={streamData?.macro_indicators?.VIX != null ? streamData.macro_indicators.VIX.toFixed(2) : '···'} col={streamData?.macro_indicators?.VIX != null && streamData.macro_indicators.VIX > 25 ? '#ff4444' : '#00ff88'} />
                <MacroStat lbl="T10Y" val={streamData?.macro_indicators?.T10Y != null ? streamData.macro_indicators.T10Y.toFixed(2) + '%' : '···'} col="#00e5ff" />
                <div>
                  <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, letterSpacing: '1.5px', color: 'rgba(0,229,255,.45)', textTransform: 'uppercase', marginBottom: 4 }}>INTEREST RATES</div>
                  {([['FED', streamData?.macro_indicators?.FED_RATE, streamData?.macro_indicators?.T3M], ['T10Y', streamData?.macro_indicators?.T10Y, null]] as [string, number|undefined, number|undefined][]).map(([c, v]) => (
                    <div key={c} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                      <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, color: 'rgba(255,255,255,.38)' }}>{c}</span>
                      <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: '#00e5ff' }}>{v != null ? v.toFixed(2) + '%' : '···'}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, padding: '0 8px' }}>
                <Globe />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, letterSpacing: '2px', color: 'rgba(255,255,255,.25)', marginBottom: 6 }}>MARKET SENTIMENT HEATMAP</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 4, height: 116 }}>
                  {SECTORS.map((s, i) => <HCell key={i} n={s.n} c={s.c} />)}
                </div>
              </div>
            </div>
          </div>

          {/* KRX Chart — portfolio_value live history */}
          <div className="glass" style={{ flex: 1, padding: 14, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 10, flexShrink: 0 }}>
              <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, letterSpacing: '2px', color: '#00e5ff', fontWeight: 700 }}>PORTFOLIO VALUE</span>
              {/* Show live portfolio value in chart header */}
              {marketTick?.portfolio_value != null && (
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 13, color: '#00e5ff', fontWeight: 700, textShadow: '0 0 8px rgba(0,229,255,.5)' }}>
                  ${marketTick.portfolio_value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              )}
              <div style={{ display: 'flex', gap: 6, marginLeft: 8 }}>
                {([['PORTFOLIO', 'PTF', null], ['KOSPI', 'KOSPI', kospi], ['SP500', 'S&P', sp500], ['USDKRW', 'KRW', usdkrw]] as [string, string, number | null][]).map(([id, lbl, val]) => (
                  <button key={id} onClick={() => setActiveIndex(id as typeof activeIndex)} style={{
                    fontFamily: "'JetBrains Mono',monospace", fontSize: 8, letterSpacing: '1px',
                    padding: '2px 8px', borderRadius: 4, cursor: 'pointer',
                    background: activeIndex === id ? 'rgba(0,229,255,.14)' : 'transparent',
                    border: `1px solid ${activeIndex === id ? 'rgba(0,229,255,.5)' : 'rgba(255,255,255,.1)'}`,
                    color: activeIndex === id ? '#00e5ff' : 'rgba(255,255,255,.38)',
                    transition: 'all .15s',
                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1,
                  }}>
                    <span>{lbl}</span>
                    {val != null && <span style={{ fontSize: 7, opacity: 0.7 }}>{id === 'USDKRW' ? val.toFixed(1) : val.toLocaleString('en-US', {maximumFractionDigits: 0})}</span>}
                  </button>
                ))}
              </div>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 5 }}>
                {(['1D', '1W', '1M', '3M'] as const).map((t, i) => (
                  <button key={t} style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, letterSpacing: '1px', padding: '2px 7px', borderRadius: 4, cursor: 'pointer', background: i === 0 ? 'rgba(0,229,255,.14)' : 'transparent', border: `1px solid ${i === 0 ? 'rgba(0,229,255,.38)' : 'rgba(255,255,255,.07)'}`, color: i === 0 ? '#00e5ff' : 'rgba(255,255,255,.28)' }}>{t}</button>
                ))}
              </div>
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              {(() => {
                const activeData = activeIndex === 'PORTFOLIO'
                  ? chartData
                  : (indexHistory[activeIndex] ?? [])
                const hasData = activeData.length >= 2
                const isKRW   = activeIndex === 'USDKRW'
                const label   = activeIndex === 'PORTFOLIO' ? 'Portfolio' : activeIndex
                const fmtY    = isKRW
                  ? (v: number) => `₩${v.toFixed(0)}`
                  : activeIndex === 'PORTFOLIO'
                    ? (v: number) => `$${(v / 1000).toFixed(0)}k`
                    : (v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 0 })
                const fmtTip  = isKRW
                  ? (v: number) => `₩${v.toFixed(1)}`
                  : activeIndex === 'PORTFOLIO'
                    ? (v: number) => `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                    : (v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 2 })
                return hasData ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={activeData} margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="kg" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#00e5ff" stopOpacity={0.18} />
                          <stop offset="95%" stopColor="#00e5ff" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="t" tick={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, fill: 'rgba(255,255,255,.18)' }} axisLine={false} tickLine={false} interval={Math.floor(activeData.length / 6)} />
                      <YAxis tick={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, fill: 'rgba(255,255,255,.18)' }} axisLine={false} tickLine={false} domain={['auto', 'auto']} width={54} tickFormatter={fmtY} />
                      <Tooltip
                        contentStyle={{ background: 'rgba(2,12,30,.96)', border: '1px solid rgba(0,229,255,.2)', borderRadius: 8, fontFamily: "'JetBrains Mono',monospace", fontSize: 10, color: '#00e5ff' }}
                        itemStyle={{ color: '#00e5ff' }} labelStyle={{ color: 'rgba(255,255,255,.35)' }}
                        formatter={(v) => [fmtTip(Number(v)), label]} />
                      <Area type="monotone" dataKey="v" stroke="#00e5ff" strokeWidth={1.8} fill="url(#kg)" dot={false} activeDot={{ r: 4, fill: '#00e5ff', stroke: '#fff', strokeWidth: 1 }} isAnimationActive={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'rgba(0,229,255,.3)', letterSpacing: '2px' }}>
                    AWAITING STREAM DATA…
                  </div>
                )
              })()}
            </div>
          </div>
        </div>

        {/* ── RIGHT PANEL ─────────────────────────────────────────────────────── */}
        <div style={{ width: 292, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 7, padding: '9px 12px 9px 8px', borderLeft: '1px solid rgba(0,229,255,.07)', overflowY: 'auto' }}>

          {/* Portfolio header + live holdings */}
          <div className="glass" style={{ padding: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: '#00e5ff' }}>PORTFOLIO ALPHA</span>
              {portfolioHealth != null && (
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: portfolioHealth > 60 ? '#00ff88' : '#ff4d6d', textShadow: portfolioHealth > 60 ? '0 0 6px rgba(0,255,136,.4)' : '0 0 6px rgba(255,77,109,.4)' }}>
                  HEALTH {Math.round(portfolioHealth)}
                </span>
              )}
              <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.28)' }}>USER: KIM MIN-SEONG</span>
            </div>
            {/* Asset class tab filter */}
            <div style={{ display: 'flex', gap: 5, marginBottom: 9 }}>
              {(['ALL', 'STOCKS', 'ETFS', 'FUNDS'] as const).map(tab => {
                const isFunds = tab === 'FUNDS'
                return (
                  <button
                    key={tab}
                    onClick={() => setAssetTab(tab)}
                    title={isFunds ? 'Fund NAV pipeline — v0.3.0' : undefined}
                    style={{
                      fontFamily: "'JetBrains Mono',monospace",
                      fontSize: 7.5,
                      letterSpacing: '1.5px',
                      padding: '3px 8px',
                      borderRadius: 4,
                      border: assetTab === tab
                        ? isFunds ? '1px solid rgba(191,0,255,.5)' : '1px solid rgba(0,229,255,.7)'
                        : '1px solid rgba(255,255,255,.12)',
                      background: assetTab === tab
                        ? isFunds ? 'rgba(191,0,255,.08)' : 'rgba(0,229,255,.1)'
                        : 'transparent',
                      color: assetTab === tab
                        ? isFunds ? '#bf00ff' : '#00e5ff'
                        : isFunds ? 'rgba(191,0,255,.4)' : 'rgba(255,255,255,.35)',
                      cursor: 'pointer',
                      transition: 'all .15s',
                      opacity: isFunds ? 0.75 : 1,
                    }}
                  >{tab}{isFunds ? ' ·' : ''}</button>
                )
              })}
            </div>
            <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, letterSpacing: '2px', color: 'rgba(255,255,255,.28)', marginBottom: 7, textTransform: 'uppercase' }}>Holdings · Live</div>
            {/* FUNDS tab: pipeline not yet open */}
            {assetTab === 'FUNDS' && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '24px 12px', gap: 8 }}>
                <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, color: 'rgba(191,0,255,.6)', letterSpacing: '2px' }}>AWAITING FEEDS</div>
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7.5, color: 'rgba(255,255,255,.2)', textAlign: 'center', lineHeight: 1.6 }}>
                  Fund NAV pipeline<br />scheduled for v0.3.0<br />(KOFIA OpenAPI)
                </div>
              </div>
            )}
            {/* Scrollable holdings — live prices from useMarketStream */}
            {assetTab !== 'FUNDS' && (
              <div style={{ maxHeight: 'calc(100vh - 420px)', overflowY: 'auto', paddingRight: 2 }}>
                {holdings.map((h, i) => (
                  <div key={h.ticker} className="row-hover" onClick={() => openTickerDetail(h)} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 5px', borderBottom: i < holdings.length - 1 ? '1px solid rgba(255,255,255,.04)' : 'none' }}>
                    <div style={{ width: 26, height: 26, borderRadius: 6, flexShrink: 0, background: `${h.col}18`, border: `1px solid ${h.col}38`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Orbitron',sans-serif", fontSize: 6.5, color: h.col }}>
                      {h.n.slice(0, 2)}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, color: 'rgba(255,255,255,.88)', letterSpacing: '1px' }}>{h.n}</div>
                      <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7.5, color: 'rgba(255,255,255,.28)' }}>
                        {h.current != null ? (h.ticker.startsWith('0') ? `₩${Math.round(h.current).toLocaleString('ko-KR')}` : `$${h.current.toFixed(2)}`) : h.t}
                      </div>
                    </div>
                    <MiniSpark up={h.dir > 0} prices={h.prices} />
                    <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 10, fontWeight: 600, flexShrink: 0, color: h.dir > 0 ? '#00ff88' : '#ff4d6d', textShadow: h.dir > 0 ? '0 0 6px rgba(0,255,136,.4)' : '0 0 6px rgba(255,77,109,.4)' }}>{h.chg}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Performance */}
          <div className="glass" style={{ padding: 12 }}>
            <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: '#00e5ff', marginBottom: 10 }}>PERFORMANCE</div>
            <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
              {([['59.5%', '#00e5ff', 'HOLDING'], ['41.5%', '#a855f7', 'RISK']] as const).map(([v, c, l]) => (
                <div key={l} style={{ flex: 1, textAlign: 'center', padding: '8px 4px', background: `${c}08`, borderRadius: 8, border: `1px solid ${c}20` }}>
                  <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 20, fontWeight: 900, color: c, textShadow: `0 0 14px ${c}88` }}>{v}</div>
                  <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.3)', letterSpacing: '1px' }}>{l}</div>
                </div>
              ))}
            </div>
            <PBar lbl="HIGH Risk" pct="19.5%" col="#ff4d6d" />
            <PBar lbl="MED Risk"  pct="77.0%" col="#fbbf24" />
            <PBar lbl="LOW Risk"  pct="8.0%"  col="#00ff88" />
            <PBar lbl="Loss"      pct="2.0%"  col="#a855f7" />
          </div>

          {/* AI Advice */}
          <div className="glass" style={{ padding: 12, flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
              <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#a855f7', boxShadow: '0 0 7px #a855f7', animation: 'glow-pulse 2.2s ease-in-out infinite' }} />
              <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: '#a855f7' }}>AI ADVICE</span>
            </div>
            <div style={{ padding: '10px 12px', marginBottom: 10, background: 'rgba(168,85,247,.09)', border: '1px solid rgba(168,85,247,.28)', borderRadius: 9 }}>
              <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 10, fontWeight: 700, color: '#a855f7', letterSpacing: '1px', lineHeight: 1.4, textShadow: '0 0 10px rgba(168,85,247,.4)' }}>AI REBALANCE<br />RECOMMENDED:</div>
              <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 13, fontWeight: 900, color: '#fff', marginTop: 4, letterSpacing: '1px' }}>DIVERSIFY TECH</div>
              <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: 'rgba(255,255,255,.42)', marginTop: 6, lineHeight: 1.5 }}>Tech concentration at 73.2% exceeds optimal threshold. Consider rotating 15–20% into defensive sectors.</div>
            </div>
            <div style={{ display: 'flex', gap: 5, marginBottom: 10 }}>
              {([['SHARPE', '1.84', '#00ff88'], ['BETA', '0.92', '#fbbf24'], ['α', '2.3%', '#00e5ff']] as const).map(([l, v, c]) => (
                <div key={l} style={{ flex: 1, padding: '7px 6px', background: 'rgba(0,229,255,.04)', border: '1px solid rgba(0,229,255,.1)', borderRadius: 7, textAlign: 'center' }}>
                  <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.3)', letterSpacing: '1px' }}>{l}</div>
                  <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 11, fontWeight: 700, color: c }}>{v}</div>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button style={{ flex: 1, padding: '7px 0', borderRadius: 7, cursor: 'pointer', background: 'rgba(168,85,247,.18)', border: '1px solid rgba(168,85,247,.38)', fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px', color: '#a855f7' }}>APPLY</button>
              <button style={{ flex: 1, padding: '7px 0', borderRadius: 7, cursor: 'pointer', background: 'rgba(0,229,255,.07)', border: '1px solid rgba(0,229,255,.18)', fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px', color: '#00e5ff' }}>ANALYZE</button>
            </div>
          </div>
        </div>
      </div>

      {/* ══ OMNI-COMMAND ═══════════════════════════════════════════════════════ */}
      <div style={{ zIndex: 20, flexShrink: 0, borderTop: '1px solid rgba(0,229,255,.09)', background: 'rgba(2,6,18,.97)', backdropFilter: 'blur(24px)' }}>

        {/* AI response widgets */}
        {resp && (
          <div style={{ padding: '10px 16px 0', display: 'flex', gap: 8, flexWrap: 'wrap', animation: 'slide-up .35s ease-out' }}>
            <div className="ai-w glass" style={{ padding: '10px 14px', minWidth: 220, flex: 2 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 4 }}>
                <div style={{ width: 4, height: 4, borderRadius: '50%', background: '#a855f7', boxShadow: '0 0 5px #a855f7' }} />
                <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7, color: '#a855f7', letterSpacing: '2px' }}>AI NEURAL ANALYSIS</span>
              </div>
              {/* Typewriter effect on insight text */}
              <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 12, color: 'rgba(255,255,255,.8)', lineHeight: 1.5 }}>
                {typedInsight}<span style={{ animation: 'blink 0.8s step-end infinite', color: '#a855f7' }}>▌</span>
              </div>
              {resp.action && <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 11, color: '#00ff88', marginTop: 5, fontWeight: 600 }}>→ {resp.action}</div>}
            </div>
            {resp.widgets.map((w, i) => <AIWidget key={i} w={w} idx={i + 1} />)}
            {resp.confidence > 0 && (
              <div className="ai-w glass" style={{ padding: '10px 14px', minWidth: 90, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', animationDelay: '.32s' }}>
                <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.28)', letterSpacing: '1px', marginBottom: 4 }}>CONFIDENCE</div>
                <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 18, fontWeight: 900, color: '#00e5ff', textShadow: '0 0 14px rgba(0,229,255,.5)' }}>{resp.confidence}%</div>
              </div>
            )}
          </div>
        )}

        {/* Long-form report — typewriter streaming effect */}
        {resp?.report && resp.report.trim().length > 0 && (
          <div className="report-scroll" style={{ margin: '8px 16px 0', maxHeight: 110, overflowY: 'auto', padding: '8px 12px', background: 'rgba(168,85,247,.06)', border: '1px solid rgba(168,85,247,.22)', borderRadius: 8, animation: 'slide-up .3s ease-out' }}>
            <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, letterSpacing: '1.5px', color: 'rgba(168,85,247,.55)', textTransform: 'uppercase', marginBottom: 5 }}>◈ INTELLIGENCE REPORT</div>
            <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 11, color: 'rgba(255,255,255,.62)', lineHeight: 1.65, whiteSpace: 'pre-wrap' }}>
              {typedReport}<span style={{ animation: 'blink 0.8s step-end infinite', color: '#a855f7' }}>▌</span>
            </div>
          </div>
        )}

        {/* Input row */}
        <div style={{ padding: '9px 16px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '2px', color: 'rgba(0,229,255,.42)', flexShrink: 0 }}>OMNI-COMMAND</span>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(0,229,255,.04)', border: '1px solid rgba(0,229,255,.18)', borderRadius: 8, padding: '7px 13px' }}>
            <span style={{ color: 'rgba(0,229,255,.4)', fontFamily: "'JetBrains Mono',monospace", fontSize: 13, flexShrink: 0 }}>›</span>
            <input
              className="omni-input"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && exec()}
              placeholder="포트폴리오 최적화, 시장 리스크 분석, 섹터 로테이션 추천... (Enter)"
              disabled={busy}
            />
            {busy && (
              <div style={{ display: 'flex', gap: 3, flexShrink: 0 }}>
                {[0, 1, 2, 3].map(i => (
                  <div key={i} style={{ width: 4, height: 4, borderRadius: '50%', background: '#a855f7', boxShadow: '0 0 5px #a855f7', animation: `glow-pulse .7s ${i * 0.15}s ease-in-out infinite` }} />
                ))}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexShrink: 0 }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', transition: 'all .3s', background: busy ? '#a855f7' : 'rgba(255,255,255,.12)', boxShadow: busy ? '0 0 7px #a855f7' : 'none', animation: busy ? 'glow-pulse .7s ease-in-out infinite' : 'none' }} />
            <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8.5, letterSpacing: '1px', color: busy ? 'rgba(168,85,247,.7)' : 'rgba(255,255,255,.18)' }}>
              {busy ? 'AI THOUGHT PROCESS' : 'AI STANDBY'}
            </span>
          </div>
          <button onClick={exec} disabled={busy || !query.trim()} style={{ padding: '7px 14px', borderRadius: 7, cursor: busy || !query.trim() ? 'default' : 'pointer', background: busy || !query.trim() ? 'rgba(0,229,255,.04)' : 'rgba(0,229,255,.13)', border: `1px solid rgba(0,229,255,${busy || !query.trim() ? '.09' : '.36'})`, fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '1px', color: busy || !query.trim() ? 'rgba(0,229,255,.22)' : '#00e5ff', transition: 'all .2s', flexShrink: 0 }}>EXECUTE</button>
        </div>

        {/* Status bar */}
        <div style={{ padding: '2px 16px 6px', display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(255,255,255,.13)' }}>
            ALEPH-ONE CORE {APP_VERSION} · NEURAL ENGINE ACTIVE · MARKET DATA {connected ? 'CONNECTED' : 'RECONNECTING'} · DATA{' '}
            <span style={{ color: trustDegraded ? '#FF9800' : trustFreshness === 'fresh' ? '#00ff88' : 'rgba(255,255,255,.13)' }}>
              {trustFreshness.toUpperCase()}
            </span>
            {' '}· {trustAvailability.toUpperCase()}
          </span>
          <span style={{ marginLeft: 'auto', fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(0,229,255,.28)' }}>{ts} KST</span>
        </div>
      </div>
    </div>
  )
}
