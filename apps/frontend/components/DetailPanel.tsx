'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'
import type { ExternalEventDTO } from '@/lib/types'
import { useNewsSummary } from '@/hooks/useNewsSummary'
import { useFundamentals } from '@/hooks/useAlephData'

export interface TickerDetail {
  ticker:  string
  n:       string
  t:       string
  col:     string
  group:   'STOCK' | 'ETF'
  chg:     string
  dir:     number
  prices:  number[]
  current: number | null
}

interface DetailPanelProps {
  open:    boolean
  onClose: () => void
  ticker?: TickerDetail | null
  news?:   ExternalEventDTO | null
}

function formatPrice(t: TickerDetail): string {
  if (t.current == null) return '···'
  return t.ticker.startsWith('0')
    ? `₩${Math.round(t.current).toLocaleString('ko-KR')}`
    : `$${t.current.toFixed(2)}`
}

function fmtNum(v: number | null | undefined, decimals = 2): string {
  if (v == null) return '···'
  return v.toLocaleString('en-US', { maximumFractionDigits: decimals })
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '···'
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
}

function fmtCap(v: number | null | undefined): string {
  if (v == null) return '···'
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(2)}M`
  return `$${v.toFixed(0)}`
}

function FundamentalsTab({ t }: { t: TickerDetail }) {
  const { data: f, isLoading } = useFundamentals(t.ticker)
  const isKR = t.ticker.startsWith('0')

  const fmtRange = (v: number | null | undefined) => {
    if (v == null) return '···'
    return isKR ? `₩${Math.round(v).toLocaleString('ko-KR')}` : `$${v.toFixed(2)}`
  }

  if (isLoading) {
    return (
      <div style={{ padding: '20px 0', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} style={{ height: 32, borderRadius: 6, background: 'rgba(255,255,255,.04)', animation: 'glow-pulse 1.2s ease-in-out infinite' }} />
        ))}
      </div>
    )
  }

  const rows: [string, string][] = [
    ['52W HIGH',        fmtRange(f?.week52_high)],
    ['52W LOW',         fmtRange(f?.week52_low)],
    ['MARKET CAP',      fmtCap(f?.market_cap)],
    ['P/E (TTM)',        fmtNum(f?.pe_trailing)],
    ['P/E (FWD)',        fmtNum(f?.pe_forward)],
    ['EPS (TTM)',        fmtNum(f?.eps_trailing)],
    ['DIV YIELD',       f?.dividend_yield_pct != null ? `${f.dividend_yield_pct.toFixed(2)}%` : '···'],
    ['BETA',            fmtNum(f?.beta)],
    ['REV GROWTH',      fmtPct(f?.revenue_growth_yoy != null ? f.revenue_growth_yoy * 100 : null)],
    ['GROSS MARGIN',    f?.gross_margin_pct != null ? `${f.gross_margin_pct.toFixed(1)}%` : '···'],
    ['DEBT / EQUITY',   fmtNum(f?.debt_to_equity)],
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {f?.sector && (
        <div style={{ marginBottom: 8, padding: '6px 10px', background: `${t.col}0e`, border: `1px solid ${t.col}28`, borderRadius: 7 }}>
          <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 9, color: 'rgba(255,255,255,.3)', letterSpacing: '1px' }}>SECTOR · </span>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: t.col }}>{f.sector}</span>
          {f.industry && (
            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(255,255,255,.28)', marginLeft: 6 }}>/ {f.industry}</span>
          )}
        </div>
      )}
      {rows.map(([lbl, val]) => (
        <div key={lbl} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 8px', background: 'rgba(255,255,255,.025)', borderRadius: 6 }}>
          <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 8.5, color: 'rgba(255,255,255,.35)', letterSpacing: '1px' }}>{lbl}</span>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9.5, color: val === '···' ? 'rgba(255,255,255,.2)' : '#00e5ff', fontWeight: 600 }}>{val}</span>
        </div>
      ))}
    </div>
  )
}

function TickerBody({ t }: { t: TickerDetail }) {
  const [tab, setTab] = useState<'PRICE' | 'FUNDAMENTALS'>('PRICE')
  const chartData = t.prices.map((v, i) => ({ i, v }))
  const up = t.dir > 0

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
        <div style={{
          width: 44, height: 44, borderRadius: 9, flexShrink: 0,
          background: `${t.col}18`, border: `1px solid ${t.col}44`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: "'Orbitron',sans-serif", fontSize: 11, color: t.col,
        }}>{t.n.slice(0, 2)}</div>
        <div>
          <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 15, color: '#fff', letterSpacing: '1px' }}>{t.n}</div>
          <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 10, color: 'rgba(255,255,255,.35)', marginTop: 2 }}>{t.t} · {t.group}</div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12 }}>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 26, fontWeight: 700, color: '#fff' }}>{formatPrice(t)}</span>
        <span style={{
          fontFamily: "'JetBrains Mono',monospace", fontSize: 13, fontWeight: 600,
          color: up ? '#00ff88' : '#ff4d6d',
          textShadow: up ? '0 0 8px rgba(0,255,136,.4)' : '0 0 8px rgba(255,77,109,.4)',
        }}>{t.chg}</span>
      </div>

      {/* Tab toggle */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 14, padding: '3px', background: 'rgba(255,255,255,.04)', borderRadius: 8, border: '1px solid rgba(255,255,255,.08)' }}>
        {(['PRICE', 'FUNDAMENTALS'] as const).map(tb => (
          <button
            key={tb}
            onClick={() => setTab(tb)}
            style={{
              flex: 1, padding: '5px 0', borderRadius: 6, cursor: 'pointer',
              background: tab === tb ? `${t.col}22` : 'transparent',
              border: `1px solid ${tab === tb ? `${t.col}55` : 'transparent'}`,
              fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px',
              color: tab === tb ? t.col : 'rgba(255,255,255,.28)',
              transition: 'all .15s',
            }}
          >{tb}</button>
        ))}
      </div>

      {tab === 'PRICE' ? (
        <>
          <div style={{ height: 160, marginBottom: 14 }}>
            {chartData.length >= 2 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="dp-grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={t.col} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={t.col} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="i" hide />
                  <YAxis tick={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, fill: 'rgba(255,255,255,.18)' }} axisLine={false} tickLine={false} domain={['auto', 'auto']} width={48} />
                  <Tooltip
                    contentStyle={{ background: 'rgba(2,12,30,.96)', border: `1px solid ${t.col}44`, borderRadius: 8, fontFamily: "'JetBrains Mono',monospace", fontSize: 10, color: t.col }}
                    labelFormatter={() => ''}
                    formatter={(v) => [Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 }), t.n]} />
                  <Area type="monotone" dataKey="v" stroke={t.col} strokeWidth={1.8} fill="url(#dp-grad)" dot={false} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'rgba(255,255,255,.2)', letterSpacing: '2px' }}>
                AWAITING PRICE HISTORY…
              </div>
            )}
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            {(['TICKER', 'SESSION CHG', 'ASSET CLASS'] as const).map((lbl, i) => (
              <div key={lbl} style={{ flex: 1, padding: '8px 6px', background: 'rgba(255,255,255,.03)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 7, textAlign: 'center' }}>
                <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 7.5, color: 'rgba(255,255,255,.3)', letterSpacing: '1px', marginBottom: 3 }}>{lbl}</div>
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 10, fontWeight: 600, color: i === 1 ? (up ? '#00ff88' : '#ff4d6d') : '#00e5ff' }}>
                  {i === 0 ? t.ticker : i === 1 ? t.chg : t.group}
                </div>
              </div>
            ))}
          </div>
        </>
      ) : (
        <FundamentalsTab t={t} />
      )}
    </>
  )
}

function NewsBody({ n }: { n: ExternalEventDTO }) {
  const sentiment = n.metadata?.sentiment
  const sCol = sentiment === 'positive' ? '#00ff88' : sentiment === 'negative' ? '#ff4d6d' : '#fbbf24'
  const occurred = n.published_at ?? n.occurred_at
  const ts = occurred ? new Date(occurred).toLocaleString('ko-KR') : '—'

  const { text: aiText, streaming: aiStreaming, done: aiDone, error: aiError } = useNewsSummary({
    title:  n.title,
    source: n.source,
    entity: n.entity,
  })

  return (
    <>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        {sentiment && (
          <span style={{
            fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px',
            color: sCol, background: `${sCol}18`, border: `1px solid ${sCol}44`,
            padding: '2px 7px', borderRadius: 4, textTransform: 'uppercase',
          }}>{sentiment}</span>
        )}
        {n.source && (
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(0,229,255,.55)', border: '1px solid rgba(0,229,255,.22)', padding: '2px 7px', borderRadius: 4 }}>{n.source}</span>
        )}
        {n.entity && (
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(255,255,255,.4)', border: '1px solid rgba(255,255,255,.12)', padding: '2px 7px', borderRadius: 4 }}>{n.entity}</span>
        )}
      </div>

      <div style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 14, color: '#fff', lineHeight: 1.5, marginBottom: 10 }}>{n.title}</div>

      <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'rgba(255,255,255,.28)', marginBottom: 16 }}>{ts}</div>

      {/* AI market analysis — auto-streamed on open */}
      <div style={{ marginBottom: 16, padding: '10px 12px', background: 'rgba(168,85,247,.06)', border: '1px solid rgba(168,85,247,.22)', borderRadius: 9 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 7 }}>
          <div style={{ width: 4, height: 4, borderRadius: '50%', background: '#a855f7', boxShadow: '0 0 5px #a855f7', animation: aiStreaming ? 'glow-pulse 0.7s ease-in-out infinite' : 'none' }} />
          <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '2px', color: '#a855f7' }}>AI MARKET ANALYSIS</span>
          {!aiStreaming && aiDone && (
            <span style={{ marginLeft: 'auto', fontFamily: "'JetBrains Mono',monospace", fontSize: 7, color: 'rgba(168,85,247,.45)' }}>GROQ · {aiError ? 'ERROR' : 'DONE'}</span>
          )}
        </div>
        {!aiText && aiStreaming && (
          <div style={{ display: 'flex', gap: 5, padding: '6px 0' }}>
            {[0, 1, 2].map(i => (
              <div key={i} style={{ height: 8, borderRadius: 4, background: 'rgba(168,85,247,.18)', animation: `glow-pulse .8s ${i * 0.18}s ease-in-out infinite` }} className={i === 0 ? 'skel-long' : i === 1 ? 'skel-mid' : 'skel-short'} />
            ))}
            <style>{`.skel-long{width:60%}.skel-mid{width:30%}.skel-short{width:10%}`}</style>
          </div>
        )}
        {aiError && !aiText && (
          <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 11, color: 'rgba(255,77,109,.6)', lineHeight: 1.5 }}>분석을 불러올 수 없습니다. 백엔드 연결을 확인해주세요.</div>
        )}
        {aiText && (
          <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 11.5, color: 'rgba(255,255,255,.78)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
            {aiText}{aiStreaming && <span style={{ animation: 'blink 0.8s step-end infinite', color: '#a855f7' }}>▌</span>}
          </div>
        )}
      </div>

      {n.summary && (
        <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 12, color: 'rgba(255,255,255,.72)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{n.summary}</div>
      )}

      {n.source_url && (
        <a href={n.source_url} target="_blank" rel="noopener noreferrer" style={{
          display: 'inline-block', marginTop: 16,
          fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: '#00e5ff',
          border: '1px solid rgba(0,229,255,.3)', borderRadius: 6, padding: '6px 12px',
          textDecoration: 'none',
        }}>VIEW SOURCE ↗</a>
      )}
    </>
  )
}

export function DetailPanel({ open, onClose, ticker, news }: DetailPanelProps) {
  const accent = ticker ? ticker.col : '#00e5ff'
  const heading = ticker ? 'ASSET DETAIL' : 'NEWS DETAIL'

  return (
    <AnimatePresence>
      {open && (ticker || news) && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            style={{
              position: 'fixed', inset: 0, zIndex: 90,
              background: 'rgba(2,6,18,.55)',
              backdropFilter: 'blur(2px)',
            }}
          />
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 320, damping: 34 }}
            style={{
              position:       'fixed', top: 0, right: 0, bottom: 0,
              width:          420, zIndex: 100,
              background:     'rgba(2, 9, 22, 0.98)',
              backdropFilter: 'blur(28px)',
              borderLeft:     `1px solid ${accent}48`,
              display:        'flex', flexDirection: 'column',
            }}
          >
            <div style={{
              padding:      '14px 16px 12px',
              borderBottom: `1px solid ${accent}30`,
              display:      'flex', alignItems: 'center', gap: 10, flexShrink: 0,
            }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: accent, boxShadow: `0 0 8px ${accent}` }} />
              <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, letterSpacing: '3px', color: accent, flex: 1 }}>
                ◈ {heading}
              </span>
              <button
                onClick={onClose}
                style={{
                  background: 'none', border: '1px solid rgba(255,255,255,.12)', borderRadius: 5,
                  color: 'rgba(255,255,255,.38)', fontSize: 11, cursor: 'pointer',
                  width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  lineHeight: 1, flexShrink: 0,
                }}
              >✕</button>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: '18px 16px', scrollbarWidth: 'thin' }}>
              {ticker ? <TickerBody t={ticker} /> : news ? <NewsBody n={news} /> : null}
            </div>

            <div style={{
              padding:    '8px 16px', flexShrink: 0,
              borderTop:  `1px solid ${accent}20`,
              display:    'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7.5, color: 'rgba(255,255,255,.18)' }}>
                ALEPH-ONE LIVE DATA · INFORMATIONAL ONLY
              </span>
              <button
                onClick={onClose}
                style={{
                  padding:    '4px 12px', borderRadius: 5, cursor: 'pointer',
                  background: `${accent}18`, border: `1px solid ${accent}48`,
                  fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px', color: accent,
                }}
              >CLOSE</button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
