'use client'
import { useState, useEffect, useMemo, useRef } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'
import { useAlephStream } from '@/hooks/useAlephStream'
import { useMarketStream } from '@/hooks/useMarketStream'
import { useNewsStream } from '@/hooks/useNewsStream'
import { useRegime, useSignals, usePortfolio, useSectorSummary, useVirtualPortfolio, useScenarioPresets, runScenario, usePortfolioAllocation, useCorrelationMatrix, useDailyBrief, useAlertsFeed, useVirtualOrders, useNavHistory, useQuantScore, useRegimeHistory } from '@/hooks/useAlephData'
import { useOmniStream } from '@/hooks/useOmniStream'
import { useAuth } from '@/hooks/useAuth'
import type { OmniWidget, OmniResp } from '@/hooks/useOmniStream'
import { ResearchPanel } from '@/components/ResearchPanel'
import { DetailPanel, type TickerDetail } from '@/components/DetailPanel'
import type { AlephStreamData, ExternalEventDTO, ScenarioPreset, ScenarioRunResponse, PortfolioAllocationDTO, DailyBriefDTO, LiveAlertItem, VirtualOrderDTO, QuantScoreLatestResponse, RegimeHistoryResponse } from '@/lib/types'

// ─── Version ──────────────────────────────────────────────────────────────────
export const APP_VERSION = 'v0.4.16'

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

/* ── Mobile responsive ── */
.aleph-body{display:flex;overflow:hidden;flex:1;min-height:0;}
.aleph-col-left{width:272px;flex-shrink:0;display:flex;flex-direction:column;gap:7px;padding:9px 8px 9px 12px;border-right:1px solid rgba(0,229,255,.07);overflow-y:auto;}
.aleph-col-center{flex:1;display:flex;flex-direction:column;gap:7px;padding:9px 8px;overflow:hidden;min-width:0;}
.aleph-col-right{width:292px;flex-shrink:0;display:flex;flex-direction:column;gap:7px;padding:9px 12px 9px 8px;border-left:1px solid rgba(0,229,255,.07);overflow-y:auto;}

@media(max-width:900px){
  .aleph-body{flex-direction:column;overflow-y:auto;overflow-x:hidden;}
  .aleph-col-left{width:100%;flex-shrink:1;border-right:none;border-bottom:1px solid rgba(0,229,255,.07);padding:8px 12px;overflow-y:visible;max-height:260px;}
  .aleph-col-center{padding:8px 12px;overflow:visible;}
  .aleph-col-right{width:100%;flex-shrink:1;border-left:none;border-top:1px solid rgba(0,229,255,.07);padding:8px 12px;overflow-y:visible;}
}
`

// ─── Types ────────────────────────────────────────────────────────────────────

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
  '005380': { n: '현대차',      t: '005380 KS', col: '#ef4444', group: 'STOCK' },
  '207940': { n: '삼성바이오',  t: '207940 KS', col: '#34d399', group: 'STOCK' },
  '005490': { n: 'POSCO홀딩스', t: '005490 KS', col: '#eab308', group: 'STOCK' },
  '105560': { n: 'KB금융',      t: '105560 KS', col: '#60a5fa', group: 'STOCK' },
  'QQQ':    { n: 'QQQ ETF',   t: 'QQQ US',    col: '#22d3ee', group: 'ETF'   },
  'BND':    { n: 'BND ETF',   t: 'BND US',    col: '#86efac', group: 'ETF'   },
  'GLD':    { n: 'GLD ETF',   t: 'GLD US',    col: '#fcd34d', group: 'ETF'   },
}
const TICKER_ORDER = ['AAPL', 'MSFT', 'TSLA', '005930', '000660', '035420', '051910', '006400', '122630', '005380', '207940', '005490', '105560', 'QQQ', 'BND', 'GLD']
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

function regimeErrorMessage(err: unknown): string {
  if (!(err instanceof Error)) return '분석 오류'
  const m = err.message
  if (m.includes('503') || m.includes('502')) return '서버 연결 실패'
  if (m.includes('504') || m.includes('408')) return '응답 시간 초과'
  if (m.includes('5'))                        return '서버 오류'
  if (m.includes('4'))                        return '분석에 필요한 지표 부족'
  if (m.includes('fetch') || m.includes('NetworkError')) return '네트워크 오류'
  return '분석 오류'
}

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

const AIWidget = ({ w, idx }: { w: OmniWidget; idx: number }) => (
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

// ─── Sector Allocation View ───────────────────────────────────────────────────

const SectorAllocationView = ({
  allocation,
  height,
}: {
  allocation: PortfolioAllocationDTO | undefined
  height: number
}) => {
  if (!allocation || allocation.sectors.length === 0) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(255,255,255,.2)', letterSpacing: '1.5px' }}>
        AWAITING HOLDINGS…
      </div>
    )
  }
  return (
    <div style={{ height, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4, scrollbarWidth: 'none' }}>
      {allocation.sectors.map(s => {
        const w = s.weight_pct
        const hot = w > 40
        const col = hot ? '#ff4d6d' : w > 25 ? '#fbbf24' : '#00e5ff'
        return (
          <div key={s.sector} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.45)', width: 80, flexShrink: 0, textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>{s.sector}</div>
            <div style={{ flex: 1, height: 10, background: 'rgba(255,255,255,.06)', borderRadius: 3, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${w}%`, background: `${col}bb`, borderRadius: 3, transition: 'width .4s' }} />
            </div>
            <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: col, width: 36, textAlign: 'right', flexShrink: 0 }}>{w.toFixed(1)}%</div>
          </div>
        )
      })}
      {allocation.concentration_warning && (
        <div style={{ marginTop: 4, padding: '4px 8px', background: 'rgba(255,77,109,.08)', border: '1px solid rgba(255,77,109,.3)', borderRadius: 5, fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: '#ff4d6d', lineHeight: 1.4 }}>
          ⚠ {allocation.concentration_warning}
        </div>
      )}
    </div>
  )
}

// ─── Alert Bell (header notification icon) ────────────────────────────────────

const SEV_COLOR: Record<string, string> = {
  critical: '#ff4d6d',
  warning:  '#fbbf24',
  info:     '#00e5ff',
}

function timeAgo(iso: string): string {
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}

const AlertBell = () => {
  const [open, setOpen] = useState(false)
  const [seenCount, setSeenCount] = useState(0)
  const dropRef = useRef<HTMLDivElement>(null)
  const { data } = useAlertsFeed(20)
  const alerts: LiveAlertItem[] = data?.alerts ?? []
  const total = data?.total ?? 0
  const unread = Math.max(0, total - seenCount)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const handleToggle = () => {
    setOpen(o => {
      if (!o) setSeenCount(total) // mark all read on open
      return !o
    })
  }

  return (
    <div ref={dropRef} style={{ position: 'relative' }}>
      <button
        onClick={handleToggle}
        title="레짐 알림"
        style={{
          position: 'relative', background: open ? 'rgba(251,191,36,.14)' : 'none',
          border: `1px solid rgba(251,191,36,${open ? '.45' : unread > 0 ? '.35' : '.15'})`,
          borderRadius: 7, width: 28, height: 28, cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 13, transition: 'all .2s',
          boxShadow: unread > 0 ? '0 0 8px rgba(251,191,36,.3)' : 'none',
        }}
      >
        🔔
        {unread > 0 && (
          <span style={{
            position: 'absolute', top: -4, right: -4, minWidth: 14, height: 14,
            borderRadius: 7, background: '#ff4d6d', border: '1px solid rgba(2,8,20,.9)',
            fontFamily: "'JetBrains Mono',monospace", fontSize: 8, fontWeight: 700,
            color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '0 2px',
          }}>{unread > 9 ? '9+' : unread}</span>
        )}
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 6px)', right: 0,
          width: 320, maxHeight: 380, overflowY: 'auto', zIndex: 200,
          background: 'rgba(2,9,22,0.98)', backdropFilter: 'blur(24px)',
          border: '1px solid rgba(251,191,36,.25)', borderRadius: 10,
          boxShadow: '0 12px 40px rgba(0,0,0,.6)',
        }}>
          <div style={{ padding: '10px 14px 8px', borderBottom: '1px solid rgba(255,255,255,.06)', display: 'flex', alignItems: 'center', gap: 7 }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#fbbf24', boxShadow: '0 0 6px #fbbf24' }} />
            <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: '#fbbf24', flex: 1 }}>REGIME ALERTS</span>
            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7.5, color: 'rgba(255,255,255,.18)' }}>{total} total</span>
          </div>
          {alerts.length === 0 ? (
            <div style={{ padding: '24px 14px', textAlign: 'center', fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'rgba(255,255,255,.22)' }}>
              NO ALERTS — 레짐 안정
            </div>
          ) : (
            <div>
              {alerts.map((a) => {
                const col = SEV_COLOR[a.severity] ?? '#fbbf24'
                return (
                  <div key={a.alert_id} style={{ padding: '9px 14px', borderBottom: '1px solid rgba(255,255,255,.04)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                      <div style={{ width: 4, height: 4, borderRadius: '50%', background: col, flexShrink: 0 }} />
                      <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7, letterSpacing: '1.5px', color: col }}>{a.severity.toUpperCase()}</span>
                      <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7.5, color: 'rgba(255,255,255,.22)', marginLeft: 'auto' }}>{timeAgo(a.occurred_at)}</span>
                    </div>
                    <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 11, color: 'rgba(255,255,255,.75)', lineHeight: 1.4 }}>{a.message}</div>
                    <div style={{ marginTop: 3, fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(255,255,255,.3)' }}>
                      {a.old_regime} → {a.new_regime} · {(a.confidence * 100).toFixed(0)}%
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Daily Brief Panel (slide-out) ────────────────────────────────────────────

const SIGNAL_COLOR: Record<string, string> = {
  'RISK-ON':  '#00ff88',
  'RISK-OFF': '#ff4d6d',
  'NEUTRAL':  '#fbbf24',
}

const ORDER_SIDE_COLOR = { BUY: '#00ff88', SELL: '#ff4d6d' } as const
const ORDER_STATUS_COLOR: Record<string, string> = { FILLED: '#00e5ff', PENDING: '#fbbf24', REJECTED: '#ff4d6d' }

function fmtOrderTime(iso: string): string {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const OrderLogPanel = ({
  open,
  onClose,
  orders,
  onReset,
}: {
  open: boolean
  onClose: () => void
  orders: VirtualOrderDTO[]
  onReset: () => void
}) => {
  const PANEL_W = 480
  return (
    <>
      {open && (
        <div
          onClick={onClose}
          style={{ position: 'fixed', inset: 0, zIndex: 88, background: 'rgba(2,6,18,.5)', backdropFilter: 'blur(2px)' }}
        />
      )}
      <div style={{
        position: 'fixed', top: 0, right: open ? 0 : -PANEL_W, bottom: 0,
        width: PANEL_W, zIndex: 89,
        background: 'rgba(2,9,22,0.98)', backdropFilter: 'blur(28px)',
        borderLeft: '1px solid rgba(0,255,136,.18)',
        display: 'flex', flexDirection: 'column',
        transition: 'right .35s cubic-bezier(.4,0,.2,1)',
      }}>
        <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid rgba(0,255,136,.12)', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#00ff88', boxShadow: '0 0 8px #00ff88' }} />
          <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, letterSpacing: '3px', color: '#00ff88', flex: 1 }}>◈ VIRTUAL ORDER LOG</span>
          <button onClick={onClose} style={{ background: 'none', border: '1px solid rgba(255,255,255,.12)', borderRadius: 5, color: 'rgba(255,255,255,.38)', fontSize: 11, cursor: 'pointer', width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>✕</button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', scrollbarWidth: 'thin' }}>
          {orders.length === 0 ? (
            <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'rgba(255,255,255,.22)', textAlign: 'center', marginTop: 48 }}>NO ORDERS YET<br /><span style={{ fontSize: 8, marginTop: 6, display: 'block', color: 'rgba(255,255,255,.12)' }}>Use OMNI-COMMAND to execute virtual trades</span></div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 8.5, fontFamily: "'JetBrains Mono',monospace" }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,.08)' }}>
                  {(['TIME', 'TICKER', 'SIDE', 'QTY', 'PRICE', 'CCY', 'STATUS'] as const).map(h => (
                    <th key={h} style={{ padding: '4px 6px', textAlign: h === 'QTY' || h === 'PRICE' ? 'right' : 'left', color: 'rgba(255,255,255,.28)', fontWeight: 400, letterSpacing: '1px', fontSize: 7.5 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {orders.map(o => (
                  <tr key={o.order_id} style={{ borderBottom: '1px solid rgba(255,255,255,.04)' }}>
                    <td style={{ padding: '5px 6px', color: 'rgba(255,255,255,.35)', whiteSpace: 'nowrap' }}>{fmtOrderTime(o.created_at)}</td>
                    <td style={{ padding: '5px 6px', color: 'rgba(255,255,255,.7)', fontWeight: 500 }}>{o.ticker}</td>
                    <td style={{ padding: '5px 6px', color: ORDER_SIDE_COLOR[o.side] ?? '#fff', fontWeight: 700 }}>{o.side}</td>
                    <td style={{ padding: '5px 6px', textAlign: 'right', color: 'rgba(255,255,255,.6)' }}>{o.quantity.toFixed(2)}</td>
                    <td style={{ padding: '5px 6px', textAlign: 'right', color: 'rgba(255,255,255,.55)' }}>{o.currency === 'KRW' ? `₩${o.fill_price.toLocaleString()}` : `$${o.fill_price.toFixed(2)}`}</td>
                    <td style={{ padding: '5px 6px', color: 'rgba(255,255,255,.3)', fontSize: 8 }}>{o.currency}</td>
                    <td style={{ padding: '5px 6px' }}>
                      <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7, letterSpacing: '1px', color: ORDER_STATUS_COLOR[o.status] ?? '#fff', padding: '2px 5px', border: `1px solid ${ORDER_STATUS_COLOR[o.status] ?? '#fff'}30`, borderRadius: 3 }}>{o.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div style={{ padding: '8px 16px', flexShrink: 0, borderTop: '1px solid rgba(0,255,136,.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7.5, color: 'rgba(255,255,255,.18)' }}>{orders.length} ORDER{orders.length !== 1 ? 'S' : ''} · PAPER TRADING</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={onReset} style={{ padding: '4px 10px', borderRadius: 5, cursor: 'pointer', background: 'rgba(255,77,109,.08)', border: '1px solid rgba(255,77,109,.3)', fontFamily: "'Orbitron',sans-serif", fontSize: 7, letterSpacing: '1px', color: '#ff4d6d' }}>RESET</button>
            <button onClick={onClose} style={{ padding: '4px 12px', borderRadius: 5, cursor: 'pointer', background: 'rgba(0,255,136,.08)', border: '1px solid rgba(0,255,136,.3)', fontFamily: "'Orbitron',sans-serif", fontSize: 7, letterSpacing: '1px', color: '#00ff88' }}>CLOSE</button>
          </div>
        </div>
      </div>
    </>
  )
}

const DailyBriefPanel = ({
  open,
  onClose,
  brief,
  loading,
}: {
  open: boolean
  onClose: () => void
  brief: import('@/lib/types').DailyBriefDTO | undefined
  loading: boolean
}) => {
  const PANEL_W = 400
  const sigCol = brief ? (SIGNAL_COLOR[brief.signal] ?? '#fbbf24') : '#fbbf24'
  return (
    <>
      {open && (
        <div
          onClick={onClose}
          style={{ position: 'fixed', inset: 0, zIndex: 88, background: 'rgba(2,6,18,.5)', backdropFilter: 'blur(2px)' }}
        />
      )}
      <div style={{
        position: 'fixed', top: 0, right: open ? 0 : -PANEL_W, bottom: 0,
        width: PANEL_W, zIndex: 89,
        background: 'rgba(2,9,22,0.98)', backdropFilter: 'blur(28px)',
        borderLeft: '1px solid rgba(168,85,247,.2)',
        display: 'flex', flexDirection: 'column',
        transition: 'right .35s cubic-bezier(.4,0,.2,1)',
      }}>
        <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid rgba(168,85,247,.15)', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#a855f7', boxShadow: '0 0 8px #a855f7', animation: 'glow-pulse 2s ease-in-out infinite' }} />
          <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, letterSpacing: '3px', color: '#a855f7', flex: 1 }}>◈ DAILY MARKET BRIEF</span>
          <button onClick={onClose} style={{ background: 'none', border: '1px solid rgba(255,255,255,.12)', borderRadius: 5, color: 'rgba(255,255,255,.38)', fontSize: 11, cursor: 'pointer', width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>✕</button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '16px', scrollbarWidth: 'thin' }}>
          {loading || !brief ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 160, gap: 12 }}>
              <div style={{ display: 'flex', gap: 4 }}>
                {[0,1,2].map(i => (
                  <div key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: '#a855f7', animation: `glow-pulse .7s ${i * 0.2}s ease-in-out infinite` }} />
                ))}
              </div>
              <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'rgba(255,255,255,.25)' }}>AI ANALYZING MARKETS…</div>
            </div>
          ) : (
            <>
              {/* Signal badge + headline */}
              <div style={{ marginBottom: 14 }}>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', background: `${sigCol}14`, border: `1px solid ${sigCol}44`, borderRadius: 20, marginBottom: 10 }}>
                  <div style={{ width: 5, height: 5, borderRadius: '50%', background: sigCol, boxShadow: `0 0 6px ${sigCol}` }} />
                  <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: sigCol }}>{brief.signal}</span>
                </div>
                <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 14, fontWeight: 600, color: '#fff', lineHeight: 1.4 }}>{brief.headline}</div>
              </div>

              {/* Key observations */}
              {brief.bullets.length > 0 && (
                <div style={{ marginBottom: 14 }}>
                  <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '2px', color: 'rgba(168,85,247,.6)', marginBottom: 8 }}>KEY OBSERVATIONS</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                    {brief.bullets.map((b, i) => (
                      <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                        <span style={{ color: '#a855f7', fontSize: 8, flexShrink: 0, marginTop: 3 }}>◈</span>
                        <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 11, color: 'rgba(255,255,255,.72)', lineHeight: 1.5 }}>{b}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Narrative body */}
              {brief.body && (
                <div style={{ padding: '10px 12px', background: 'rgba(168,85,247,.07)', border: '1px solid rgba(168,85,247,.2)', borderRadius: 8 }}>
                  <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7, letterSpacing: '2px', color: 'rgba(168,85,247,.5)', marginBottom: 6 }}>NARRATIVE</div>
                  <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 11, color: 'rgba(255,255,255,.6)', lineHeight: 1.65 }}>{brief.body}</div>
                </div>
              )}
            </>
          )}
        </div>

        <div style={{ padding: '8px 16px', flexShrink: 0, borderTop: '1px solid rgba(168,85,247,.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7, color: 'rgba(255,255,255,.15)' }}>
            {brief?.generated_at ? new Date(brief.generated_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) : '—'} · {brief?.source ?? '—'}
          </span>
          <button onClick={onClose} style={{ padding: '4px 12px', borderRadius: 5, cursor: 'pointer', background: 'rgba(168,85,247,.1)', border: '1px solid rgba(168,85,247,.3)', fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px', color: '#a855f7' }}>CLOSE</button>
        </div>
      </div>
    </>
  )
}

// ─── Regime History Timeline Bar ─────────────────────────────────────────────

const REGIME_COLORS: Record<string, string> = {
  goldilocks:          '#00ff88',
  expansion:           '#4ade80',
  overheating:         '#fbbf24',
  stagflation:         '#f97316',
  policy_tightening:   '#ff4d6d',
  recession:           '#ff4d6d',
  recovery:            '#a855f7',
  contraction:         '#ef4444',
  unknown:             'rgba(255,255,255,.3)',
}

const RegimeTimelineBar = ({ history }: { history: RegimeHistoryResponse | undefined }) => {
  if (!history?.records || history.records.length === 0) return null
  const records = [...history.records].reverse()  // oldest first
  return (
    <div className="glass" style={{ padding: '6px 12px', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
        <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7, letterSpacing: '2px', color: 'rgba(0,229,255,.6)' }}>REGIME TIMELINE</span>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 6.5, color: 'rgba(255,255,255,.25)' }}>(last {records.length} records)</span>
      </div>
      <div style={{ display: 'flex', gap: 2, alignItems: 'stretch' }}>
        {records.map((r, i) => {
          const col = REGIME_COLORS[r.regime_label.toLowerCase()] ?? REGIME_COLORS.unknown
          const isLatest = i === records.length - 1
          const label = r.regime_label.replace(/_/g, ' ').toUpperCase()
          const date = r.as_of_date.slice(0, 10)
          return (
            <div
              key={r.regime_id}
              title={`${label} | ${date} | conf: ${r.confidence}${r.changed ? ' | CHANGED' : ''}`}
              style={{
                flex: 1, minWidth: 0, padding: '4px 5px',
                background: `${col}${isLatest ? '22' : '0d'}`,
                border: `1px solid ${col}${isLatest ? '55' : '25'}`,
                borderRadius: 4,
                display: 'flex', flexDirection: 'column', gap: 2,
                boxShadow: isLatest ? `0 0 6px ${col}44` : 'none',
              }}
            >
              <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 5.5, color: col, letterSpacing: '.5px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {label}
              </div>
              <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 5, color: 'rgba(255,255,255,.3)' }}>
                {date.slice(5)}
              </div>
              {r.changed && (
                <div style={{ width: 4, height: 4, borderRadius: '50%', background: '#fbbf24', boxShadow: '0 0 3px #fbbf24', flexShrink: 0, alignSelf: 'flex-end' }} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Quant Synthesis Panel ────────────────────────────────────────────────────

const QuantSynthesisPanel = ({
  quantScore,
  regime,
}: {
  quantScore: QuantScoreLatestResponse | undefined
  regime:     import('@/lib/types').RegimeLatestResponse | undefined
}) => {
  const dims = quantScore
    ? [
        { k: 'GROWTH',  v: quantScore.growth.score,               lv: quantScore.growth.level },
        { k: 'INFLAT',  v: quantScore.inflation.score,            lv: quantScore.inflation.level },
        { k: 'LABOR',   v: quantScore.labor.score,                lv: quantScore.labor.level },
        { k: 'POLICY',  v: quantScore.policy.score,               lv: quantScore.policy.level },
        { k: 'FIN.CND', v: quantScore.financial_conditions.score, lv: quantScore.financial_conditions.level },
      ]
    : []

  const levelColor = (lv: string) => {
    if (lv === 'HIGH' || lv === 'STRONG') return '#00ff88'
    if (lv === 'MEDIUM' || lv === 'MODERATE') return '#fbbf24'
    return '#ff4d6d'
  }

  const overallColor = quantScore
    ? quantScore.overall_support > 0.6 ? '#00ff88'
      : quantScore.overall_support > 0.35 ? '#fbbf24'
      : '#ff4d6d'
    : 'rgba(255,255,255,.3)'

  return (
    <div className="glass" style={{ padding: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: '#fbbf24' }}>ENGINE SYNTHESIS</span>
        {quantScore && (
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7, color: overallColor, letterSpacing: '1px' }}>
            SUPPORT {(quantScore.overall_support * 100).toFixed(0)}%
          </span>
        )}
      </div>
      {/* Regime row */}
      {regime && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 7px', marginBottom: 6, background: 'rgba(251,191,36,.06)', border: '1px solid rgba(251,191,36,.18)', borderRadius: 6 }}>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7.5, color: '#fbbf24', letterSpacing: '1px' }}>
            {regime.regime_label.replace(/_/g, ' ')}
          </span>
          <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7, color: 'rgba(255,255,255,.4)' }}>
            {regime.confidence}
          </span>
        </div>
      )}
      {/* Dimension bars */}
      {dims.length > 0 ? dims.map(d => (
        <div key={d.k} style={{ marginBottom: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 6.5, color: 'rgba(255,255,255,.45)', letterSpacing: '1px' }}>{d.k}</span>
            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 6.5, color: levelColor(d.lv) }}>{d.lv}</span>
          </div>
          <div style={{ height: 3, background: 'rgba(255,255,255,.08)', borderRadius: 2 }}>
            <div style={{ height: '100%', width: `${Math.round(Math.abs(d.v) * 100)}%`, background: levelColor(d.lv), borderRadius: 2, transition: 'width .6s ease' }} />
          </div>
        </div>
      )) : (
        <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7.5, color: 'rgba(0,229,255,.3)', letterSpacing: '2px', textAlign: 'center', padding: '8px 0' }}>ENGINE: AWAITING FEED</div>
      )}
      {/* Breadth + Momentum row */}
      {quantScore && (
        <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
          {[
            { lbl: 'BREADTH',   v: quantScore.breadth },
            { lbl: 'MOMENTUM',  v: quantScore.momentum },
            { lbl: 'INTENSITY', v: quantScore.change_intensity },
          ].map(it => (
            <div key={it.lbl} style={{ flex: 1, textAlign: 'center', padding: '4px 2px', background: 'rgba(0,229,255,.04)', borderRadius: 5, border: '1px solid rgba(0,229,255,.1)' }}>
              <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, fontWeight: 700, color: it.v > 0 ? '#00ff88' : '#ff4d6d' }}>
                {it.v > 0 ? '+' : ''}{(it.v * 100).toFixed(0)}%
              </div>
              <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 5.5, color: 'rgba(255,255,255,.3)', marginTop: 1, letterSpacing: '.8px' }}>{it.lbl}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Correlation Panel (slide-out) ────────────────────────────────────────────

const CorrelationPanel = ({
  open,
  onClose,
  tickers,
  matrix,
}: {
  open: boolean
  onClose: () => void
  tickers: string[] | undefined
  matrix: number[][] | undefined
}) => {
  const PANEL_W = 460
  return (
    <>
      {open && (
        <div
          onClick={onClose}
          style={{ position: 'fixed', inset: 0, zIndex: 88, background: 'rgba(2,6,18,.5)', backdropFilter: 'blur(2px)' }}
        />
      )}
      <div style={{
        position: 'fixed', top: 0, right: open ? 0 : -PANEL_W, bottom: 0,
        width: PANEL_W, zIndex: 89,
        background: 'rgba(2,9,22,0.98)', backdropFilter: 'blur(28px)',
        borderLeft: '1px solid rgba(0,229,255,.2)',
        display: 'flex', flexDirection: 'column',
        transition: 'right .35s cubic-bezier(.4,0,.2,1)',
      }}>
        <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid rgba(0,229,255,.15)', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#00e5ff', boxShadow: '0 0 8px #00e5ff' }} />
          <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, letterSpacing: '3px', color: '#00e5ff', flex: 1 }}>◈ CORRELATION MATRIX · 30D</span>
          <button onClick={onClose} style={{ background: 'none', border: '1px solid rgba(255,255,255,.12)', borderRadius: 5, color: 'rgba(255,255,255,.38)', fontSize: 11, cursor: 'pointer', width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>✕</button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '16px', scrollbarWidth: 'thin' }}>
          {!tickers || !matrix ? (
            <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'rgba(255,255,255,.25)', textAlign: 'center', marginTop: 40 }}>LOADING…</div>
          ) : (
            <>
              <div style={{ marginBottom: 10, fontFamily: "'Rajdhani',sans-serif", fontSize: 9, color: 'rgba(255,255,255,.28)', lineHeight: 1.5 }}>
                Pearson 30-day daily return correlation. Range: −1 (inverse) → +1 (perfect).
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ borderCollapse: 'collapse', fontSize: 8, fontFamily: "'JetBrains Mono',monospace" }}>
                  <thead>
                    <tr>
                      <td style={{ width: 52, padding: '4px 4px 4px 0' }} />
                      {tickers.map(t => (
                        <td key={t} style={{ padding: '0 3px 6px', color: 'rgba(0,229,255,.55)', textAlign: 'center', fontSize: 7, whiteSpace: 'nowrap', transform: 'rotate(-35deg)', display: 'inline-block', minWidth: 28 }}>{t.length > 5 ? t.slice(0, 5) : t}</td>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tickers.map((row, ri) => (
                      <tr key={row}>
                        <td style={{ padding: '2px 6px 2px 0', color: 'rgba(255,255,255,.45)', whiteSpace: 'nowrap', fontSize: 7.5 }}>{row}</td>
                        {matrix[ri]?.map((v, ci) => {
                          const abs = Math.abs(v)
                          const isPos = v >= 0
                          const isDiag = ri === ci
                          const bg = isDiag
                            ? 'rgba(0,229,255,.08)'
                            : isPos
                              ? `rgba(0,255,136,${(abs * 0.4).toFixed(2)})`
                              : `rgba(255,77,109,${(abs * 0.4).toFixed(2)})`
                          const fg = isDiag ? '#00e5ff' : isPos ? '#00ff88' : '#ff4d6d'
                          return (
                            <td key={ci} title={`${row} × ${tickers[ci]}: ${v.toFixed(3)}`} style={{
                              padding: '2px 3px', textAlign: 'center', minWidth: 28,
                              background: bg, borderRadius: 3, color: isDiag ? fg : abs > 0.5 ? fg : 'rgba(255,255,255,.45)',
                              fontWeight: abs > 0.7 ? 700 : 400,
                            }}>{v.toFixed(2)}</td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
                {([['HIGH CORR', '#00ff88', '>0.7'], ['LOW CORR', '#fbbf24', '0.3–0.7'], ['NEGATIVE', '#ff4d6d', '<0']] as const).map(([lbl, col, range]) => (
                  <div key={lbl} style={{ flex: 1, padding: '7px 8px', background: `${col}08`, border: `1px solid ${col}28`, borderRadius: 7, textAlign: 'center' }}>
                    <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 7.5, color: 'rgba(255,255,255,.3)', letterSpacing: '1px', marginBottom: 3 }}>{lbl}</div>
                    <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 10, color: col }}>{range}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div style={{ padding: '8px 16px', flexShrink: 0, borderTop: '1px solid rgba(0,229,255,.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7.5, color: 'rgba(255,255,255,.18)' }}>ALEPH-ONE · 30-DAY PEARSON</span>
          <button onClick={onClose} style={{ padding: '4px 12px', borderRadius: 5, cursor: 'pointer', background: 'rgba(0,229,255,.1)', border: '1px solid rgba(0,229,255,.3)', fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px', color: '#00e5ff' }}>CLOSE</button>
        </div>
      </div>
    </>
  )
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export default function AlephDashboard() {
  const [now,         setNow]         = useState(new Date())
  const [query,       setQuery]       = useState('')
  const [panelOpen,   setPanelOpen]   = useState(false)
  const [assetTab,    setAssetTab]    = useState<'ALL' | 'STOCKS' | 'ETFS' | 'FUNDS'>('ALL')
  const [detailOpen,  setDetailOpen]  = useState(false)
  const [detailTicker,setDetailTicker]= useState<TickerDetail | null>(null)
  const [detailNews,  setDetailNews]  = useState<ExternalEventDTO | null>(null)
  const [activeIndex, setActiveIndex] = useState<'PORTFOLIO' | 'KOSPI' | 'SP500' | 'USDKRW'>('PORTFOLIO')
  const [indexHistory, setIndexHistory] = useState<Record<string, Array<{t: number; v: number}>>>({})
  const indexIdxRef = useRef(0)
  const [chartPeriod, setChartPeriod] = useState<'1D' | '1W' | '1M' | '3M'>('1D')
  const [whatifOpen,  setWhatifOpen]  = useState(false)
  const [whatifPreset, setWhatifPreset] = useState<string | null>(null)
  const [whatifResult, setWhatifResult] = useState<ScenarioRunResponse | null>(null)
  const [whatifRunning, setWhatifRunning] = useState(false)
  const [whatifError, setWhatifError] = useState<string | null>(null)
  const [sectorViewMode, setSectorViewMode] = useState<'CHANGE' | 'ALLOCATION'>('CHANGE')
  const [correlOpen, setCorrelOpen] = useState(false)
  const [briefOpen,  setBriefOpen]  = useState(false)
  const [ordersOpen, setOrdersOpen] = useState(false)
  const [compactMode, setCompactMode] = useState(() => {
    if (typeof localStorage !== 'undefined') return localStorage.getItem('aleph-compact') === '1'
    return false
  })

  // ── Real backend data ──────────────────────────────────────────────────────
  const { data: streamData, lastMsgAt: sseLastMsgAt } = useAlephStream()
  const { data: marketTick, connected, priceHistory } = useMarketStream()
  const liveNews                                      = useNewsStream(15)
  const { data: regimeData, isLoading: regimeLoading, error: regimeError } = useRegime()
  const { data: signalsData, isLoading: signalsLoading }                   = useSignals()
  const { data: sectorData }                                                = useSectorSummary()
  const { history: histData, metrics: metricsData }                         = usePortfolio(chartPeriod)
  const { data: vpData, mutate: vpMutate }                                   = useVirtualPortfolio()
  const { data: presetsData }                                                = useScenarioPresets()
  const { data: allocationData }                                             = usePortfolioAllocation()
  const { data: correlData }                                                 = useCorrelationMatrix(30)
  const { data: briefData, isLoading: briefLoading }                         = useDailyBrief()
  const { data: ordersData }                                                  = useVirtualOrders(30)
  const { data: navHistoryData }                                              = useNavHistory(30)
  const { data: quantScoreData }                                              = useQuantScore()
  const { data: regimeHistData }                                              = useRegimeHistory(8)
  const omni                                                                 = useOmniStream()
  const { user, signOut }                                                    = useAuth()

  // Order execution toast
  const [orderToast, setOrderToast] = useState<string | null>(null)
  const showToast = (msg: string) => {
    setOrderToast(msg)
    setTimeout(() => setOrderToast(null), 4000)
  }

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

  // "마지막 데이터 수집" — human-readable age of the last snapshot
  const lastUpdate = useMemo(() => {
    const snap = trust?.snapshot_timestamp
    if (!snap) return null
    const diffMs = Date.now() - new Date(snap).getTime()
    const hrs    = Math.floor(diffMs / 3_600_000)
    const mins   = Math.floor((diffMs % 3_600_000) / 60_000)
    if (hrs > 48)  return `${Math.floor(hrs / 24)}일 전`
    if (hrs > 0)   return `${hrs}시간 전`
    return mins > 0 ? `${mins}분 전` : '방금'
  }, [trust?.snapshot_timestamp])

  const kospi  = streamData?.market_indices?.KOSPI  ?? null
  const sp500  = streamData?.market_indices?.SP500   ?? null
  const usdkrw = streamData?.market_indices?.USDKRW  ?? null

  // Live sector heatmap — fallback to static config when API not yet ready
  const liveSectors: Sector[] = useMemo(() => {
    if (!sectorData?.sectors?.length) return SECTORS
    return sectorData.sectors.map(s => ({ n: s.name, c: parseFloat(s.change_pct.toFixed(1)) }))
  }, [sectorData])

  // Historical chart data for non-1D periods
  const historicalChartData = useMemo<Array<{ t: number; v: number }> | null>(() => {
    if (!histData?.points?.length) return null
    return histData.points.map((p, i) => ({ t: i, v: p.value }))
  }, [histData])

  // Sharpe, Beta, Alpha from real backend metrics
  const sharpeDisplay = metricsData?.sharpe != null ? metricsData.sharpe.toFixed(2) : '—'
  const betaDisplay   = metricsData?.beta   != null ? metricsData.beta.toFixed(2)   : 'N/A'
  const alphaDisplay  = metricsData?.alpha  != null ? `${metricsData.alpha.toFixed(1)}%` : 'N/A'

  // Virtual portfolio — HOLDING vs CASH breakdown
  const vp = (streamData as AlephStreamData)?.virtual_portfolio
  const vpHoldingPct = useMemo(() => {
    if (!vp?.accounts) return null
    const totalMarket = Object.values(vp.accounts).reduce((s, a) => s + a.market_value, 0)
    const totalValue  = Object.values(vp.accounts).reduce((s, a) => s + a.total_value,  0)
    return totalValue > 0 ? (totalMarket / totalValue) * 100 : null
  }, [vp])
  const vpCashPct = vpHoldingPct != null ? 100 - vpHoldingPct : null

  // Signal distribution — drives risk bars (SELL=HIGH, HOLD=MED, BUY=LOW)
  const riskDist = useMemo(() => {
    const matrix = streamData?.intelligence_synthesis?.risk_matrix
    if (!matrix?.length) return null
    const total = matrix.length
    const sell  = matrix.filter(r => r.sig_score === 'SELL').length
    const hold  = matrix.filter(r => r.sig_score === 'HOLD').length
    const buy   = matrix.filter(r => r.sig_score === 'BUY').length
    return {
      high: ((sell / total) * 100).toFixed(1) + '%',
      med:  ((hold / total) * 100).toFixed(1) + '%',
      low:  ((buy  / total) * 100).toFixed(1) + '%',
    }
  }, [streamData])

  // ── Typewriter for OMNI insight + report ──────────────────────────────────
  const typedInsight = useTypingText(omni.resp?.insight, 14)
  const typedReport  = useTypingText(omni.resp?.report,  8)

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
  // SSE staleness: stale if last frame > 60 s ago and we've received at least one frame
  const sseStale = sseLastMsgAt > 0 && (now.getTime() - sseLastMsgAt) > 60_000

  // ── OMNI-COMMAND — delegate to useOmniStream ─────────────────────────────
  const handleExec = (forceQuery?: string) => {
    const q = (forceQuery ?? query).trim()
    if (!q || omni.busy) return
    omni.exec(q, () => { setPanelOpen(true); setDetailOpen(false) })
    if (!forceQuery) setQuery('')
  }

  const handleApply = () => {
    handleExec('현재 포트폴리오 리스크를 분석하고 최적 리밸런싱을 실행해줘. execute_virtual_order 툴을 사용해서 실제로 가상 매매를 실행하고 결과를 알려줘.')
    showToast('가상 매매 명령 전송 중…')
  }

  const handlePortfolioReset = async () => {
    if (!confirm('가상 포트폴리오를 초기 잔고로 리셋하시겠습니까?')) return
    try {
      await fetch('/api/v1/portfolio/reset', { method: 'POST' })
      await vpMutate()
      showToast('포트폴리오가 초기 상태로 리셋됐습니다.')
    } catch {
      showToast('리셋 실패 — 잠시 후 다시 시도해주세요.')
    }
  }

  const handleWhatifRun = async (presetId: string) => {
    setWhatifPreset(presetId)
    setWhatifRunning(true)
    setWhatifResult(null)
    setWhatifError(null)
    try {
      const res = await runScenario(presetId, null)
      setWhatifResult(res)
    } catch (e) {
      setWhatifError(e instanceof Error ? e.message : '시나리오 실행 실패')
    } finally {
      setWhatifRunning(false)
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
      {/* Order toast */}
      {orderToast && (
        <div style={{ position: 'fixed', bottom: 72, left: '50%', transform: 'translateX(-50%)', zIndex: 9999, padding: '10px 20px', background: 'rgba(0,20,45,.95)', border: '1px solid rgba(0,229,255,.4)', borderRadius: 10, fontFamily: "'Orbitron',sans-serif", fontSize: 10, color: '#00e5ff', letterSpacing: '1px', boxShadow: '0 0 20px rgba(0,229,255,.2)', animation: 'slide-up .3s ease-out', whiteSpace: 'nowrap' }}>
          {orderToast}
        </div>
      )}
      <ResearchPanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        streaming={omni.streaming}
        content={omni.panelContent}
        meta={omni.panelMeta}
        query={omni.panelQuery}
      />
      <DetailPanel
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        ticker={detailTicker}
        news={detailNews}
      />

      {/* ── CORRELATION PANEL ──────────────────────────────────────────────── */}
      <CorrelationPanel
        open={correlOpen}
        onClose={() => setCorrelOpen(false)}
        tickers={correlData?.tickers}
        matrix={correlData?.matrix}
      />

      {/* ── DAILY BRIEF PANEL ──────────────────────────────────────────────── */}
      <DailyBriefPanel
        open={briefOpen}
        onClose={() => setBriefOpen(false)}
        brief={briefData}
        loading={briefLoading}
      />

      {/* ── ORDER LOG PANEL ────────────────────────────────────────────────── */}
      <OrderLogPanel
        open={ordersOpen}
        onClose={() => setOrdersOpen(false)}
        orders={ordersData?.orders ?? []}
        onReset={async () => {
          await fetch('/api/v1/portfolio/reset', { method: 'POST' })
          setOrdersOpen(false)
        }}
      />

      {/* ── WHAT-IF SCENARIO PANEL ─────────────────────────────────────────── */}
      {whatifOpen && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 800, pointerEvents: 'none' }}>
          {/* Backdrop */}
          <div
            onClick={() => setWhatifOpen(false)}
            style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,.55)', pointerEvents: 'all' }}
          />
          {/* Panel */}
          <div style={{
            position: 'absolute', top: 48, right: 0, bottom: 0, width: 380,
            background: 'rgba(2,8,22,.97)', backdropFilter: 'blur(28px)',
            borderLeft: '1px solid rgba(251,191,36,.2)',
            display: 'flex', flexDirection: 'column',
            pointerEvents: 'all', animation: 'slide-up .25s ease-out',
            overflow: 'hidden',
          }}>
            {/* Header */}
            <div style={{ padding: '12px 16px 10px', borderBottom: '1px solid rgba(251,191,36,.12)', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#fbbf24', boxShadow: '0 0 7px #fbbf24' }} />
                <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, letterSpacing: '2.5px', color: '#fbbf24' }}>WHAT-IF SCENARIO</span>
              </div>
              <button
                onClick={() => setWhatifOpen(false)}
                style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,.4)', cursor: 'pointer', fontFamily: "'JetBrains Mono',monospace", fontSize: 14, lineHeight: 1 }}>✕</button>
            </div>

            {/* Preset grid */}
            <div style={{ padding: '12px 14px', flexShrink: 0 }}>
              <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, letterSpacing: '1.5px', color: 'rgba(251,191,36,.55)', textTransform: 'uppercase', marginBottom: 8 }}>시나리오 선택</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                {(presetsData?.presets ?? ([] as ScenarioPreset[])).map(p => (
                  <button
                    key={p.id}
                    onClick={() => handleWhatifRun(p.id)}
                    disabled={whatifRunning}
                    style={{
                      padding: '8px 10px', borderRadius: 8, cursor: whatifRunning ? 'default' : 'pointer',
                      textAlign: 'left', transition: 'all .2s',
                      background: whatifPreset === p.id ? 'rgba(251,191,36,.18)' : 'rgba(251,191,36,.05)',
                      border: `1px solid rgba(251,191,36,${whatifPreset === p.id ? '.5' : '.15'})`,
                      opacity: whatifRunning && whatifPreset !== p.id ? 0.45 : 1,
                    }}
                  >
                    <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, color: '#fbbf24', letterSpacing: '1px', marginBottom: 3 }}>{p.label}</div>
                    <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, color: 'rgba(255,255,255,.42)', lineHeight: 1.4 }}>{p.description}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Loading */}
            {whatifRunning && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px' }}>
                {[0,1,2,3].map(i => (
                  <div key={i} style={{ width: 4, height: 4, borderRadius: '50%', background: '#fbbf24', animation: `glow-pulse .7s ${i * 0.15}s ease-in-out infinite` }} />
                ))}
                <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: 'rgba(251,191,36,.7)', letterSpacing: '1px' }}>시나리오 분석 중…</span>
              </div>
            )}

            {/* Error */}
            {whatifError && (
              <div style={{ margin: '0 14px 10px', padding: '8px 12px', background: 'rgba(255,77,109,.08)', border: '1px solid rgba(255,77,109,.3)', borderRadius: 8, fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: '#ff4d6d' }}>
                {whatifError}
              </div>
            )}

            {/* Result */}
            {whatifResult && !whatifRunning && (
              <div style={{ flex: 1, overflowY: 'auto', padding: '0 14px 14px' }}>
                <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, letterSpacing: '1.5px', color: 'rgba(251,191,36,.55)', textTransform: 'uppercase', marginBottom: 8 }}>
                  시나리오 결과 — {whatifResult.result.scenario_label}
                </div>

                {/* Before / After comparison */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
                  {([
                    ['현재', whatifResult.result.baseline, 'rgba(0,229,255,.7)'],
                    ['시나리오', whatifResult.result.projected, '#fbbf24'],
                  ] as [string, typeof whatifResult.result.baseline, string][]).map(([lbl, view, col]) => {
                    const statusColor = view.synthesis_status.includes('bullish') ? '#00ff88'
                      : view.synthesis_status.includes('cautious') ? '#fbbf24'
                      : view.synthesis_status.includes('risk') ? '#ff4d6d'
                      : '#a855f7'
                    return (
                      <div key={lbl} style={{ padding: '10px', background: 'rgba(0,0,0,.3)', border: `1px solid ${col}22`, borderRadius: 9 }}>
                        <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: col, letterSpacing: '1px', marginBottom: 6 }}>{lbl}</div>
                        <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, color: statusColor, marginBottom: 4, letterSpacing: '1px', lineHeight: 1.4 }}>{view.synthesis_status.toUpperCase().replace(/_/g, ' ')}</div>
                        <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 14, fontWeight: 700, color: col }}>{(view.conviction_score * 100).toFixed(0)}</div>
                        <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.3)', marginTop: 1 }}>CONVICTION</div>
                      </div>
                    )
                  })}
                </div>

                {/* Delta badge */}
                <div style={{
                  padding: '9px 12px', borderRadius: 8, marginBottom: 10,
                  background: whatifResult.result.conviction_delta >= 0 ? 'rgba(0,255,136,.07)' : 'rgba(255,77,109,.07)',
                  border: `1px solid ${whatifResult.result.conviction_delta >= 0 ? 'rgba(0,255,136,.3)' : 'rgba(255,77,109,.3)'}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                  <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: 'rgba(255,255,255,.5)' }}>컨빅션 변화</span>
                  <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 14, fontWeight: 700, color: whatifResult.result.conviction_delta >= 0 ? '#00ff88' : '#ff4d6d' }}>
                    {whatifResult.result.conviction_delta >= 0 ? '+' : ''}{(whatifResult.result.conviction_delta * 100).toFixed(1)}pts
                  </span>
                </div>

                {/* Status changed indicator */}
                {whatifResult.result.status_changed && (
                  <div style={{ padding: '7px 12px', borderRadius: 7, background: 'rgba(168,85,247,.1)', border: '1px solid rgba(168,85,247,.35)', fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: '#a855f7', marginBottom: 10, letterSpacing: '1px' }}>
                    ◈ 투자 전략 전환 감지 — 레짐 재평가 권고
                  </div>
                )}

                {/* Notes */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {([
                    ['베이스라인', whatifResult.result.baseline.note],
                    ['시나리오', whatifResult.result.projected.note],
                  ] as [string, string][]).map(([lbl, note]) => (
                    <div key={lbl} style={{ padding: '7px 10px', background: 'rgba(255,255,255,.03)', borderRadius: 7, borderLeft: '2px solid rgba(251,191,36,.3)' }}>
                      <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(251,191,36,.5)', marginBottom: 3, letterSpacing: '1px' }}>{lbl}</div>
                      <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: 'rgba(255,255,255,.6)', lineHeight: 1.5 }}>{note}</div>
                    </div>
                  ))}
                </div>

                {/* Baseline regime info */}
                <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                  <div style={{ flex: 1, padding: '6px 9px', background: 'rgba(0,0,0,.3)', borderRadius: 7, border: '1px solid rgba(255,255,255,.07)' }}>
                    <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.3)', marginBottom: 2 }}>베이스라인 레짐</div>
                    <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: '#00e5ff' }}>{whatifResult.baseline_regime}</div>
                  </div>
                  <div style={{ flex: 1, padding: '6px 9px', background: 'rgba(0,0,0,.3)', borderRadius: 7, border: '1px solid rgba(255,255,255,.07)' }}>
                    <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.3)', marginBottom: 2 }}>매크로 신뢰도</div>
                    <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: '#a855f7' }}>{(whatifResult.baseline_confidence * 100).toFixed(0)}%</div>
                  </div>
                </div>
              </div>
            )}

            {/* Empty state */}
            {!whatifRunning && !whatifResult && !whatifError && (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, padding: 24 }}>
                <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, color: 'rgba(251,191,36,.4)', letterSpacing: '2px' }}>시나리오를 선택하세요</div>
                <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: 'rgba(255,255,255,.22)', textAlign: 'center', lineHeight: 1.6 }}>
                  현재 포트폴리오 기준 베이스라인과<br />가상 시나리오를 비교 분석합니다
                </div>
              </div>
            )}
          </div>
        </div>
      )}

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
          {/* Regime badge — SSE stream first, REST fallback; only show error when both sources fail */}
          {(regimeLabel || regimeLoading || regimeError) && (
            <div style={{
              padding: '2px 8px', borderRadius: 4,
              background: (regimeError && !regimeLabel) ? 'rgba(255,71,87,.07)' : 'rgba(0,229,255,.07)',
              border: `1px solid ${(regimeError && !regimeLabel) ? 'rgba(255,71,87,.3)' : 'rgba(0,229,255,.22)'}`,
              fontFamily: "'Rajdhani',sans-serif", fontSize: 8, letterSpacing: '1.5px',
              color: (regimeError && !regimeLabel) ? '#FF4757' : '#00e5ff', textTransform: 'uppercase',
            }}>
              {(regimeError && !regimeLabel) ? regimeErrorMessage(regimeError) : (regimeLabel ?? '···')}
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
            {sseStale && (
              <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7, letterSpacing: '1.5px', color: '#fbbf24', padding: '1px 5px', border: '1px solid rgba(251,191,36,.4)', borderRadius: 3, animation: 'glow-pulse 2s ease-in-out infinite' }}>STALE</span>
            )}
          </div>
          <AlertBell />
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 12, color: 'rgba(0,229,255,.65)', letterSpacing: '1px' }}>{ts}</span>
          <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, letterSpacing: '1.5px', color: 'rgba(255,255,255,.22)' }}>KST UTC+9</span>
          <button
            onClick={() => {
              const next = !compactMode
              setCompactMode(next)
              localStorage.setItem('aleph-compact', next ? '1' : '0')
            }}
            title={compactMode ? '전체 레이아웃 보기' : '중앙 패널만 보기'}
            style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7, letterSpacing: '1.5px', padding: '3px 9px', borderRadius: 4, border: `1px solid rgba(0,229,255,${compactMode ? '.5' : '.2'})`, background: compactMode ? 'rgba(0,229,255,.14)' : 'transparent', color: compactMode ? '#00e5ff' : 'rgba(0,229,255,.4)', cursor: 'pointer', transition: 'all .2s' }}
          >
            {compactMode ? '⊞ FULL' : '⊟ FOCUS'}
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 10px', borderRadius: 20, background: 'rgba(0,229,255,.07)', border: '1px solid rgba(0,229,255,.18)' }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#00ff88', boxShadow: '0 0 5px #00ff88' }} />
            <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, color: '#00e5ff', letterSpacing: '1px' }}>
              {user ? user.email?.split('@')[0].toUpperCase() : 'KIM MIN-SEONG'}
            </span>
            {user && (
              <button onClick={signOut} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 0 0 4px', color: 'rgba(0,229,255,0.4)', fontSize: 9, fontFamily: 'inherit', letterSpacing: '1px' }} title="로그아웃">
                ×
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ══ MAIN BODY ═══════════════════════════════════════════════════════════ */}
      <div className="aleph-body" style={{ zIndex: 5 }}>

        {/* ── LEFT PANEL ─────────────────────────────────────────────────────── */}
        <div className="aleph-col-left" style={compactMode ? { display: 'none' } : {}}>

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
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '8px 0', gap: 4 }}>
              <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(0,229,255,.3)', letterSpacing: '2px' }}>AWAITING FEED</div>
              <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.18)', textAlign: 'center' }}>Commodity pipeline — v0.5.0</div>
            </div>
          </div>

          {/* ALGORITHMIC SIGNALS — live from SSE stream */}
          <div className="glass" style={{ padding: 12, flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
              <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: '#00e5ff' }}>ALGORITHMIC SIGNALS</span>
              {trust && (
                <div title={trust.is_degraded ? (trust.degraded_reason ?? '데이터 품질 저하') : trust.freshness_status} style={{
                  width: 5, height: 5, borderRadius: '50%', marginLeft: 'auto',
                  background: trust.is_degraded ? '#FF9800' : trust.freshness_status === 'fresh' ? '#00ff88' : trust.freshness_status === 'stale' ? '#ff4d6d' : '#fbbf24',
                  boxShadow: `0 0 5px ${trust.is_degraded ? '#FF9800' : trust.freshness_status === 'fresh' ? '#00ff88' : '#ff4d6d'}`,
                }} />
              )}
            </div>
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
        <div className="aleph-col-center">

          {/* GLOBAL MACRO card */}
          <div className="glass" style={{ padding: 14, flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
              <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 10, fontWeight: 700, letterSpacing: '2px', color: '#00e5ff' }}>GLOBAL MACRO &amp; MARKET OVERVIEW</span>
              {trustDegraded && (
                <span style={{ marginLeft: 10, fontFamily: "'Rajdhani',sans-serif", fontSize: 8, letterSpacing: '1px', color: '#FF9800', border: '1px solid rgba(255,152,0,.3)', borderRadius: 4, padding: '1px 6px' }}>DEGRADED</span>
              )}
            </div>
            <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
              <div style={{ width: 96, flexShrink: 0 }}>
                <MacroStat lbl="VIX" val={streamData?.macro_indicators?.VIX != null ? streamData.macro_indicators.VIX.toFixed(2) : '···'} col={streamData?.macro_indicators?.VIX != null && streamData.macro_indicators.VIX > 25 ? '#ff4444' : '#00ff88'} />
                <MacroStat lbl="T10Y" val={streamData?.macro_indicators?.T10Y != null ? streamData.macro_indicators.T10Y.toFixed(2) + '%' : '···'} col="#00e5ff" />
                <div>
                  <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, letterSpacing: '1.5px', color: 'rgba(0,229,255,.45)', textTransform: 'uppercase', marginBottom: 4 }}>INTEREST RATES</div>
                  {([['FED', streamData?.macro_indicators?.FED_RATE], ['T10Y', streamData?.macro_indicators?.T10Y]] as [string, number|undefined][]).map(([c, v]) => {
                    const dotCol = v != null
                      ? (trustFreshness === 'fresh' ? '#00ff88' : trustFreshness === 'stale' ? '#ff4d6d' : '#fbbf24')
                      : 'rgba(255,255,255,.15)'
                    return (
                      <div key={c} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 3 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <div style={{ width: 4, height: 4, borderRadius: '50%', background: dotCol, boxShadow: v != null ? `0 0 3px ${dotCol}` : 'none', flexShrink: 0 }} />
                          <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, color: 'rgba(255,255,255,.38)' }}>{c}</span>
                        </div>
                        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: '#00e5ff' }}>{v != null ? v.toFixed(2) + '%' : '···'}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, padding: '0 8px' }}>
                <Globe />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, letterSpacing: '2px', color: 'rgba(255,255,255,.25)' }}>
                    {sectorViewMode === 'CHANGE' ? 'MARKET SENTIMENT HEATMAP' : 'SECTOR ALLOCATION'}
                  </div>
                  <div style={{ display: 'flex', gap: 3 }}>
                    {(['CHANGE', 'ALLOCATION'] as const).map(mode => (
                      <button key={mode} onClick={() => setSectorViewMode(mode)} style={{
                        padding: '2px 6px', borderRadius: 4, cursor: 'pointer',
                        background: sectorViewMode === mode ? 'rgba(0,229,255,.14)' : 'transparent',
                        border: `1px solid ${sectorViewMode === mode ? 'rgba(0,229,255,.4)' : 'rgba(255,255,255,.1)'}`,
                        fontFamily: "'Orbitron',sans-serif", fontSize: 6.5, letterSpacing: '0.5px',
                        color: sectorViewMode === mode ? '#00e5ff' : 'rgba(255,255,255,.3)',
                        transition: 'all .15s',
                      }}>{mode === 'CHANGE' ? '% CHG' : 'ALLOC'}</button>
                    ))}
                  </div>
                </div>
                {sectorViewMode === 'CHANGE' ? (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 4, height: 108 }}>
                    {liveSectors.map((s, i) => <HCell key={i} n={s.n} c={s.c} />)}
                  </div>
                ) : (
                  <SectorAllocationView allocation={allocationData} height={108} />
                )}
              </div>
            </div>
          </div>

          {/* Regime History Timeline */}
          <RegimeTimelineBar history={regimeHistData} />

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
                {(['1D', '1W', '1M', '3M'] as const).map((t) => (
                  <button key={t} onClick={() => setChartPeriod(t)} style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, letterSpacing: '1px', padding: '2px 7px', borderRadius: 4, cursor: 'pointer', background: chartPeriod === t ? 'rgba(0,229,255,.14)' : 'transparent', border: `1px solid ${chartPeriod === t ? 'rgba(0,229,255,.38)' : 'rgba(255,255,255,.07)'}`, color: chartPeriod === t ? '#00e5ff' : 'rgba(255,255,255,.28)', transition: 'all .15s' }}>{t}</button>
                ))}
              </div>
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              {(() => {
                const useHistorical = activeIndex === 'PORTFOLIO' && chartPeriod !== '1D'
                const activeData = activeIndex === 'PORTFOLIO'
                  ? (useHistorical ? (historicalChartData ?? chartData) : chartData)
                  : (indexHistory[activeIndex] ?? [])
                const isLoading  = useHistorical && !histData
                const isEmpty    = useHistorical && histData?.empty === true && !historicalChartData
                const hasData    = activeData.length >= 2
                const isKRW      = activeIndex === 'USDKRW'
                const label      = activeIndex === 'PORTFOLIO' ? 'Portfolio' : activeIndex
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
                if (isLoading || isEmpty) return (
                  <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'rgba(0,229,255,.3)', letterSpacing: '2px' }}>
                      {isLoading ? '데이터 불러오는 중…' : '데이터 준비 중'}
                    </div>
                    {isEmpty && <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: 'rgba(255,255,255,.18)', textAlign: 'center' }}>
                      {chartPeriod} 기간 시장 데이터가 아직 충분히 쌓이지 않았습니다
                    </div>}
                  </div>
                )
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
        <div className="aleph-col-right" style={compactMode ? { display: 'none' } : {}}>

          {/* Portfolio header + live holdings */}
          <div className="glass" style={{ padding: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: '#00e5ff' }}>PORTFOLIO ALPHA</span>
              {portfolioHealth != null && (
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: portfolioHealth > 60 ? '#00ff88' : '#ff4d6d', textShadow: portfolioHealth > 60 ? '0 0 6px rgba(0,255,136,.4)' : '0 0 6px rgba(255,77,109,.4)' }}>
                  HEALTH {Math.round(portfolioHealth)}
                </span>
              )}
              <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.28)' }}>
                USER: {user ? user.email?.split('@')[0].toUpperCase() : 'KIM MIN-SEONG'}
              </span>
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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: '#00e5ff' }}>PERFORMANCE</div>
              <button onClick={handlePortfolioReset} title="초기 잔고로 리셋" style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7, letterSpacing: '1px', padding: '2px 7px', borderRadius: 4, border: '1px solid rgba(255,77,109,.35)', background: 'transparent', color: 'rgba(255,77,109,.6)', cursor: 'pointer' }}>RESET</button>
            </div>
            {/* Total NAV summary — aggregated across all accounts */}
            {vpData?.accounts && (() => {
              const accs = Object.values(vpData.accounts)
              const totalInitial = accs.reduce((s, a) => s + a.initial_balance, 0)
              const totalValue   = accs.reduce((s, a) => s + a.total_value, 0)
              const totalPl      = accs.reduce((s, a) => s + a.total_pl, 0)
              const totalPlPct   = totalInitial > 0 ? (totalPl / totalInitial) * 100 : 0
              const plCol        = totalPl >= 0 ? '#00ff88' : '#ff4d6d'
              return (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 10px', marginBottom: 10, background: `${plCol}08`, border: `1px solid ${plCol}22`, borderRadius: 8 }}>
                  <div>
                    <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7, color: 'rgba(255,255,255,.28)', marginBottom: 2 }}>TOTAL NAV</div>
                    <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 12, fontWeight: 900, color: '#00e5ff', letterSpacing: '0.5px' }}>
                      ₩{Math.round(totalValue).toLocaleString('ko-KR')}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 11, fontWeight: 700, color: plCol }}>
                      {totalPl >= 0 ? '+' : ''}{totalPlPct.toFixed(2)}%
                    </div>
                    <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: plCol }}>
                      {totalPl >= 0 ? '+' : ''}₩{Math.round(totalPl).toLocaleString('ko-KR')}
                    </div>
                  </div>
                </div>
              )
            })()}
            {/* NAV history sparkline */}
            {(() => {
              const snaps = (navHistoryData?.snapshots ?? [])
                .filter(s => s.currency === 'KRW')
                .slice()
                .reverse()  // oldest → newest
              if (snaps.length < 2) return null
              const vals = snaps.map(s => s.total_nav)
              const min  = Math.min(...vals)
              const max  = Math.max(...vals)
              const W = 180, H = 32
              const range = max - min || 1
              const pts = vals.map((v, i) => {
                const x = (i / (vals.length - 1)) * W
                const y = H - ((v - min) / range) * (H - 4) - 2
                return `${x.toFixed(1)},${y.toFixed(1)}`
              }).join(' ')
              const lastNav  = vals[vals.length - 1]
              const firstNav = vals[0]
              const navColor = lastNav >= firstNav ? '#00ff88' : '#ff4d6d'
              return (
                <div style={{ marginBottom: 8, padding: '6px 8px', background: 'rgba(0,229,255,.03)', border: '1px solid rgba(0,229,255,.08)', borderRadius: 6 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7, color: 'rgba(255,255,255,.3)', letterSpacing: '1.5px' }}>NAV 30D</span>
                    <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, color: navColor }}>
                      {lastNav >= firstNav ? '▲' : '▼'} {Math.abs(((lastNav - firstNav) / firstNav) * 100).toFixed(2)}%
                    </span>
                  </div>
                  <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', height: H }}>
                    <polyline points={pts} fill="none" stroke={navColor} strokeWidth="1.5" strokeLinejoin="round" opacity="0.8" />
                    <polyline points={`0,${H} ${pts} ${W},${H}`} fill={`${navColor}18`} stroke="none" />
                  </svg>
                </div>
              )
            })()}
            {/* Virtual Portfolio accounts */}
            {vpData?.accounts && Object.entries(vpData.accounts).map(([currency, acc]) => {
              const plColor = acc.total_pl >= 0 ? '#00ff88' : '#ff4d6d'
              const fmt = (n: number) => currency === 'KRW' ? `₩${Math.round(n).toLocaleString('ko-KR')}` : `$${n.toFixed(0)}`
              return (
                <div key={currency} style={{ marginBottom: 8, padding: '7px 9px', background: 'rgba(0,229,255,.04)', border: '1px solid rgba(0,229,255,.1)', borderRadius: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, color: 'rgba(255,255,255,.5)', letterSpacing: '1px' }}>{currency} 계좌</span>
                    <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: plColor }}>{acc.total_pl >= 0 ? '+' : ''}{acc.total_pl_pct.toFixed(1)}%</span>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7, color: 'rgba(255,255,255,.3)', marginBottom: 1 }}>현금</div>
                      <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, color: '#a855f7' }}>{fmt(acc.cash_balance)}</div>
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7, color: 'rgba(255,255,255,.3)', marginBottom: 1 }}>평가금액</div>
                      <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, color: '#00e5ff' }}>{fmt(acc.total_value)}</div>
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7, color: 'rgba(255,255,255,.3)', marginBottom: 1 }}>손익</div>
                      <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, color: plColor }}>{fmt(acc.total_pl)}</div>
                    </div>
                  </div>
                </div>
              )
            })}
            {/* Holdings holdings P&L mini-list */}
            {vpData?.holdings && vpData.holdings.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                {vpData.holdings.slice(0, 3).map(h => (
                  <div key={h.ticker} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', borderBottom: '1px solid rgba(255,255,255,.04)' }}>
                    <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(255,255,255,.5)' }}>{h.display_name}</span>
                    <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: h.unrealized_pl >= 0 ? '#00ff88' : '#ff4d6d' }}>{h.unrealized_pl >= 0 ? '+' : ''}{h.unrealized_pl.toFixed(0)}</span>
                  </div>
                ))}
              </div>
            )}
            {!vpData?.accounts && (
              <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
                {([
                  [vpHoldingPct != null ? `${vpHoldingPct.toFixed(1)}%` : '—', '#00e5ff', 'HOLDING'],
                  [vpCashPct    != null ? `${vpCashPct.toFixed(1)}%`    : '—', '#a855f7', 'CASH'],
                ] as [string, string, string][]).map(([v, c, l]) => (
                  <div key={l} style={{ flex: 1, textAlign: 'center', padding: '8px 4px', background: `${c}08`, borderRadius: 8, border: `1px solid ${c}20` }}>
                    <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 20, fontWeight: 900, color: c, textShadow: `0 0 14px ${c}88` }}>{v}</div>
                    <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.3)', letterSpacing: '1px' }}>{l}</div>
                  </div>
                ))}
              </div>
            )}
            {riskDist ? (
              <>
                <PBar lbl="HIGH Risk" pct={riskDist.high} col="#ff4d6d" />
                <PBar lbl="MED Risk"  pct={riskDist.med}  col="#fbbf24" />
                <PBar lbl="LOW Risk"  pct={riskDist.low}  col="#00ff88" />
              </>
            ) : (
              <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(0,229,255,.28)', letterSpacing: '2px', textAlign: 'center', padding: '8px 0' }}>SIGNAL DIST: LOADING…</div>
            )}
          </div>

          {/* Engine Synthesis */}
          <QuantSynthesisPanel quantScore={quantScoreData} regime={regimeData} />

          {/* AI Advice */}
          <div className="glass" style={{ padding: 12, flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
              <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#a855f7', boxShadow: '0 0 7px #a855f7', animation: 'glow-pulse 2.2s ease-in-out infinite' }} />
              <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '2px', color: '#a855f7' }}>AI ADVICE</span>
            </div>
            <div style={{ padding: '10px 12px', marginBottom: 10, background: 'rgba(168,85,247,.09)', border: '1px solid rgba(168,85,247,.28)', borderRadius: 9 }}>
              {allocationData?.concentration_warning ? (
                <>
                  <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 10, fontWeight: 700, color: '#a855f7', letterSpacing: '1px', lineHeight: 1.4, textShadow: '0 0 10px rgba(168,85,247,.4)' }}>AI REBALANCE<br />RECOMMENDED:</div>
                  <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 13, fontWeight: 900, color: '#fff', marginTop: 4, letterSpacing: '1px' }}>DIVERSIFY {(allocationData.top_sector ?? '').toUpperCase()}</div>
                  <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: 'rgba(255,255,255,.42)', marginTop: 6, lineHeight: 1.5 }}>{allocationData.concentration_warning}</div>
                </>
              ) : allocationData ? (
                <>
                  <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 10, fontWeight: 700, color: '#00ff88', letterSpacing: '1px', lineHeight: 1.4 }}>PORTFOLIO<br />DIVERSIFIED</div>
                  <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: 'rgba(255,255,255,.42)', marginTop: 6, lineHeight: 1.5 }}>HHI {allocationData.hhi.toFixed(3)} — 섹터 집중 위험 없음. 현재 배분 유지 권장.</div>
                </>
              ) : (
                <>
                  <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 10, fontWeight: 700, color: '#a855f7', letterSpacing: '1px', lineHeight: 1.4, textShadow: '0 0 10px rgba(168,85,247,.4)' }}>AI REBALANCE<br />RECOMMENDED:</div>
                  <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 13, fontWeight: 900, color: '#fff', marginTop: 4, letterSpacing: '1px' }}>ANALYZING…</div>
                  <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: 'rgba(255,255,255,.28)', marginTop: 6, lineHeight: 1.5 }}>포트폴리오 데이터를 불러오는 중입니다.</div>
                </>
              )}
            </div>
            <div style={{ display: 'flex', gap: 5, marginBottom: 10 }}>
              {([['SHARPE', sharpeDisplay, '#00ff88'], ['BETA', betaDisplay, '#fbbf24'], ['α', alphaDisplay, '#00e5ff']] as const).map(([l, v, c]) => (
                <div key={l} style={{ flex: 1, padding: '7px 6px', background: 'rgba(0,229,255,.04)', border: '1px solid rgba(0,229,255,.1)', borderRadius: 7, textAlign: 'center' }}>
                  <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.3)', letterSpacing: '1px' }}>{l}</div>
                  <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 11, fontWeight: 700, color: c }}>{v}</div>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                onClick={handleApply}
                disabled={omni.busy}
                title="AI가 포트폴리오 최적화를 분석하고 가상 매매를 실행합니다"
                style={{ flex: 1, padding: '7px 0', borderRadius: 7, cursor: omni.busy ? 'default' : 'pointer', opacity: omni.busy ? 0.5 : 1, background: 'rgba(168,85,247,.18)', border: '1px solid rgba(168,85,247,.55)', fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px', color: '#a855f7', transition: 'all .2s', boxShadow: omni.busy ? 'none' : '0 0 8px rgba(168,85,247,.25)' }}>APPLY</button>
              <button
                onClick={() => { setWhatifOpen(o => !o); setWhatifResult(null); setWhatifError(null) }}
                style={{ flex: 1, padding: '7px 0', borderRadius: 7, cursor: 'pointer', background: whatifOpen ? 'rgba(251,191,36,.18)' : 'rgba(251,191,36,.07)', border: `1px solid rgba(251,191,36,${whatifOpen ? '.55' : '.25'})`, fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px', color: '#fbbf24', transition: 'all .2s', boxShadow: whatifOpen ? '0 0 8px rgba(251,191,36,.25)' : 'none' }}>WHAT-IF</button>
              <button
                onClick={() => handleExec('현재 포트폴리오 리스크를 분석하고 최적 리밸런싱 전략을 제시해줘. 섹터 집중도, 변동성, 리스크 대비 수익률을 고려해서 구체적인 조언을 해줘.')}
                disabled={omni.busy}
                style={{ flex: 1, padding: '7px 0', borderRadius: 7, cursor: omni.busy ? 'default' : 'pointer', opacity: omni.busy ? 0.5 : 1, background: 'rgba(0,229,255,.07)', border: '1px solid rgba(0,229,255,.18)', fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px', color: '#00e5ff', transition: 'all .2s' }}>ANALYZE</button>
              <button
                onClick={() => setCorrelOpen(o => !o)}
                style={{ flex: 1, padding: '7px 0', borderRadius: 7, cursor: 'pointer', background: correlOpen ? 'rgba(0,229,255,.14)' : 'rgba(0,229,255,.04)', border: `1px solid rgba(0,229,255,${correlOpen ? '.45' : '.15'})`, fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px', color: '#00e5ff', transition: 'all .2s', boxShadow: correlOpen ? '0 0 8px rgba(0,229,255,.2)' : 'none' }}>CORREL</button>
              <button
                onClick={() => setBriefOpen(o => !o)}
                style={{ flex: 1, padding: '7px 0', borderRadius: 7, cursor: 'pointer', background: briefOpen ? 'rgba(168,85,247,.18)' : 'rgba(168,85,247,.06)', border: `1px solid rgba(168,85,247,${briefOpen ? '.55' : '.2'})`, fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px', color: '#a855f7', transition: 'all .2s', boxShadow: briefOpen ? '0 0 8px rgba(168,85,247,.25)' : 'none' }}>BRIEF</button>
              <button
                onClick={() => setOrdersOpen(o => !o)}
                style={{ flex: 1, padding: '7px 0', borderRadius: 7, cursor: 'pointer', background: ordersOpen ? 'rgba(0,255,136,.14)' : 'rgba(0,255,136,.04)', border: `1px solid rgba(0,255,136,${ordersOpen ? '.45' : '.15'})`, fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px', color: '#00ff88', transition: 'all .2s', boxShadow: ordersOpen ? '0 0 8px rgba(0,255,136,.2)' : 'none' }}>ORDERS</button>
            </div>
          </div>
        </div>
      </div>

      {/* ══ OMNI-COMMAND ═══════════════════════════════════════════════════════ */}
      <div style={{ zIndex: 20, flexShrink: 0, borderTop: '1px solid rgba(0,229,255,.09)', background: 'rgba(2,6,18,.97)', backdropFilter: 'blur(24px)' }}>

        {/* AI response widgets */}
        {omni.resp && (
          <div style={{ padding: '10px 16px 0', display: 'flex', gap: 8, flexWrap: 'wrap', animation: 'slide-up .35s ease-out' }}>
            <div className="ai-w glass" style={{ padding: '10px 14px', minWidth: 220, flex: 2 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 4 }}>
                <div style={{ width: 4, height: 4, borderRadius: '50%', background: '#a855f7', boxShadow: '0 0 5px #a855f7' }} />
                <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7, color: '#a855f7', letterSpacing: '2px' }}>AI NEURAL ANALYSIS</span>
              </div>
              <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 12, color: 'rgba(255,255,255,.8)', lineHeight: 1.5 }}>
                {typedInsight}<span style={{ animation: 'blink 0.8s step-end infinite', color: '#a855f7' }}>▌</span>
              </div>
              {omni.resp.action && <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 11, color: '#00ff88', marginTop: 5, fontWeight: 600 }}>→ {omni.resp.action}</div>}
            </div>
            {omni.resp.widgets.map((w, i) => <AIWidget key={i} w={w} idx={i + 1} />)}
            {omni.resp.confidence > 0 && (
              <div className="ai-w glass" style={{ padding: '10px 14px', minWidth: 90, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', animationDelay: '.32s' }}>
                <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8, color: 'rgba(255,255,255,.28)', letterSpacing: '1px', marginBottom: 4 }}>CONFIDENCE</div>
                <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 18, fontWeight: 900, color: '#00e5ff', textShadow: '0 0 14px rgba(0,229,255,.5)' }}>{omni.resp.confidence}%</div>
              </div>
            )}
          </div>
        )}

        {/* Long-form report — typewriter streaming effect */}
        {omni.resp?.report && omni.resp.report.trim().length > 0 && (
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
              onKeyDown={e => e.key === 'Enter' && handleExec()}
              placeholder="포트폴리오 최적화, 시장 리스크 분석, 섹터 로테이션 추천... (Enter)"
              disabled={omni.busy}
            />
            {omni.busy && (
              <div style={{ display: 'flex', gap: 3, flexShrink: 0 }}>
                {[0, 1, 2, 3].map(i => (
                  <div key={i} style={{ width: 4, height: 4, borderRadius: '50%', background: '#a855f7', boxShadow: '0 0 5px #a855f7', animation: `glow-pulse .7s ${i * 0.15}s ease-in-out infinite` }} />
                ))}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexShrink: 0 }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', transition: 'all .3s', background: omni.busy ? '#a855f7' : 'rgba(255,255,255,.12)', boxShadow: omni.busy ? '0 0 7px #a855f7' : 'none', animation: omni.busy ? 'glow-pulse .7s ease-in-out infinite' : 'none' }} />
            <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8.5, letterSpacing: '1px', color: omni.busy ? 'rgba(168,85,247,.7)' : 'rgba(255,255,255,.18)' }}>
              {omni.busy ? 'AI THOUGHT PROCESS' : 'AI STANDBY'}
            </span>
          </div>
          <button onClick={() => handleExec()} disabled={omni.busy || !query.trim()} style={{ padding: '7px 14px', borderRadius: 7, cursor: omni.busy || !query.trim() ? 'default' : 'pointer', background: omni.busy || !query.trim() ? 'rgba(0,229,255,.04)' : 'rgba(0,229,255,.13)', border: `1px solid rgba(0,229,255,${omni.busy || !query.trim() ? '.09' : '.36'})`, fontFamily: "'Orbitron',sans-serif", fontSize: 8, letterSpacing: '1px', color: omni.busy || !query.trim() ? 'rgba(0,229,255,.22)' : '#00e5ff', transition: 'all .2s', flexShrink: 0 }}>EXECUTE</button>
        </div>

        {/* Status bar */}
        <div style={{ padding: '2px 16px 6px', display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(255,255,255,.13)' }}>
            ALEPH-ONE CORE {APP_VERSION} · {omni.busy ? 'AI PROCESSING' : 'NEURAL ENGINE ACTIVE'} · MARKET DATA {connected ? 'CONNECTED' : 'RECONNECTING'} · DATA{' '}
            <span style={{ color: trustDegraded ? '#FF9800' : trustFreshness === 'fresh' ? '#00ff88' : 'rgba(255,255,255,.13)' }}>
              {trustFreshness.toUpperCase()}
            </span>
            {' '}· {trustAvailability.toUpperCase()}
            {lastUpdate && (
              <span style={{ color: 'rgba(0,229,255,.28)' }}> · 마지막 수집: {lastUpdate}</span>
            )}
          </span>
          <span style={{ marginLeft: 'auto', fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(0,229,255,.28)' }}>{ts} KST</span>
        </div>
      </div>
    </div>
  )
}
