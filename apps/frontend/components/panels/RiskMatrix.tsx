'use client'
import { useEffect, useRef, useState } from 'react'
import { useSignals, useRegime } from '@/hooks/useAlephData'
import { seededRand } from '@/lib/utils'
import type { AlephRiskRow, SignalSummaryDTO } from '@/lib/types'

// ── Layout constants ──────────────────────────────────────────────────────────
const COLS     = ['MOMENTUM', 'REGIME', 'RATES', 'SENTIMENT', 'SIG SCORE']
const HDR_X    = 70   // row-label column width (wider for Korean names)
const HDR_Y    = 24   // header row height
const CW       = 84   // cell width
const CH       = 52   // cell height (taller to fit sparkline in SIG SCORE col)
const HIST_LEN = 60   // sparkline history points (60 s rolling)

// Fallback rows match backend DISPLAY_NAMES exactly
const FALLBACK_ROWS = ['AAPL', 'MSFT', 'TSLA', '삼성전자', 'SK하이닉스']

// ── Score mapping ─────────────────────────────────────────────────────────────

/** WATCH/STABLE → continuous 0–1 (used as fallback when numeric score absent) */
function statusScore(ws: string): number {
  return ws === 'WATCH' ? 0.22 : 0.72
}

/** BUY/HOLD/SELL → 0–1 */
function sigScore(sig: string): number {
  if (sig === 'BUY')  return 0.90
  if (sig === 'SELL') return 0.10
  return 0.50
}

/** Derive per-column score from a stream row, using numeric fields when available */
function colScore(row: AlephRiskRow, ci: number): number {
  switch (ci) {
    case 0: {
      // momentum: prefer quant_score (0–1), else binary
      const q = row.quant_score
      return q != null ? q : statusScore(row.momentum)
    }
    case 1: {
      // regime: no dedicated continuous score — use status binary
      return statusScore(row.regime)
    }
    case 2: {
      // rates: mirror regime
      return statusScore(row.rates)
    }
    case 3: {
      // sentiment: normalize sentiment_score (−1..+1) → 0..1
      const s = row.sentiment_score
      return s != null ? Math.max(0, Math.min(1, (s + 1) / 2)) : statusScore(row.sentiment)
    }
    case 4: {
      // sig_score: prefer sig_confidence (0–1), else BUY/HOLD/SELL mapping
      const c = row.sig_confidence
      return c != null ? c : sigScore(row.sig_score)
    }
    default: return 0.5
  }
}

// ── Synthetic fallback (SWR data path, no SSE) ────────────────────────────────

function scoreCell(ri: number, ci: number, avgSig: number, regimeFam: string): number {
  if (ci === 4) return avgSig
  if (ci === 1) {
    const fam = regimeFam.toLowerCase()
    if (fam.includes('expansion') || fam.includes('goldilocks') || fam.includes('recovery'))
      return 0.65 + seededRand(ri * 11 + 1) * 0.30
    if (fam.includes('contraction') || fam.includes('recession') || fam.includes('stagflation'))
      return seededRand(ri * 11 + 2) * 0.30
    return 0.35 + seededRand(ri * 11 + 3) * 0.30
  }
  return 0.15 + seededRand(ri * 7 + ci * 31 + 17) * 0.70
}

// ── Cell builder ──────────────────────────────────────────────────────────────

interface Cell {
  ri: number; ci: number
  x: number;  y: number
  score: number
  fill: string; stroke: string
  tag: string | null; tagColor: string
  statusLabel: string
}

function buildCell(ri: number, ci: number, score: number, row?: AlephRiskRow): Cell {
  const x      = HDR_X + ci * CW
  const y      = HDR_Y + ri * CH
  const isOpp  = score >= 0.62
  const isRisk = score < 0.32

  const fill   = isOpp
    ? `rgba(0,229,255,${(0.08 + score * 0.20).toFixed(2)})`
    : isRisk
      ? `rgba(191,0,255,${(0.08 + (1 - score) * 0.20).toFixed(2)})`
      : 'rgba(255,255,255,0.03)'
  const stroke = isOpp ? 'rgba(0,229,255,0.28)' : isRisk ? 'rgba(191,0,255,0.28)' : 'rgba(255,255,255,0.06)'
  const tag      = score > 0.84 ? '▲ ADJ' : score < 0.18 ? '▼ RDC' : null
  const tagColor = score > 0.84 ? '#00E5FF' : '#BF00FF'

  // Status label: WATCH/STABLE or BUY/HOLD/SELL for SIG SCORE col
  let statusLabel = ''
  if (row) {
    if (ci === 4) statusLabel = row.sig_score
    else if (ci === 0) statusLabel = row.momentum
    else if (ci === 1) statusLabel = row.regime
    else if (ci === 2) statusLabel = row.rates
    else if (ci === 3) statusLabel = row.sentiment
  }

  return { ri, ci, x, y, score, fill, stroke, tag, tagColor, statusLabel }
}

// ── Inline sparkline SVG path ─────────────────────────────────────────────────

function sparklinePath(hist: number[], x0: number, y0: number, w: number, h: number): string {
  if (hist.length < 2) return ''
  const n   = hist.length
  const min = 0   // fixed Y-axis 0–1 so scale is stable
  const max = 1
  const pts = hist.map((v, i) => {
    const px = x0 + (i / (n - 1)) * w
    const py = y0 + h - ((v - min) / (max - min)) * h
    return `${px.toFixed(1)},${py.toFixed(1)}`
  })
  return `M ${pts.join(' L ')}`
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  className?:  string
  riskMatrix?: AlephRiskRow[] | null
}

export default function RiskMatrix({ className = '', riskMatrix }: Props) {
  const { data: signals } = useSignals()
  const { data: regime }  = useRegime()

  // Rolling history of sig_confidence per ticker for the sparkline
  const [sigHistory, setSigHistory] = useState<Record<string, number[]>>({})

  useEffect(() => {
    if (!riskMatrix || riskMatrix.length === 0) return
    setSigHistory(prev => {
      const next = { ...prev }
      riskMatrix.forEach(row => {
        const hist = next[row.ticker] ? [...next[row.ticker]] : []
        const val  = row.sig_confidence ?? sigScore(row.sig_score)
        hist.push(val)
        if (hist.length > HIST_LEN) hist.shift()
        next[row.ticker] = hist
      })
      return next
    })
  }, [riskMatrix])

  const hasStream = !!riskMatrix && riskMatrix.length > 0

  const rows: string[] = hasStream
    ? riskMatrix!.map(r => r.ticker)
    : FALLBACK_ROWS

  // Build cell grid
  const cells: Cell[] = hasStream
    ? riskMatrix!.flatMap((row, ri) =>
        COLS.map((_, ci) => buildCell(ri, ci, colScore(row, ci), row))
      )
    : (() => {
        const sigList  = signals?.signals ?? []
        const avgScore = sigList.length
          ? sigList.reduce((s: number, x: SignalSummaryDTO) => s + x.score, 0) / sigList.length
          : 0.5
        return FALLBACK_ROWS.flatMap((_, ri) =>
          COLS.map((_, ci) => buildCell(ri, ci, scoreCell(ri, ci, avgScore, regime?.regime_family ?? 'unknown')))
        )
      })()

  const W = HDR_X + COLS.length * CW
  const H = HDR_Y + rows.length * CH

  return (
    <div className={`w-full h-full flex items-start justify-center ${className}`}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ maxHeight: '100%', overflow: 'visible' }}
      >
        {/* Column headers */}
        {COLS.map((col, ci) => (
          <text
            key={col}
            x={HDR_X + ci * CW + CW / 2}
            y={HDR_Y - 8}
            textAnchor="middle"
            fill="rgba(0,229,255,0.60)"
            fontSize="7"
            fontFamily="'Space Mono', monospace"
            letterSpacing="0.5"
          >
            {col}
          </text>
        ))}

        {/* Row headers */}
        {rows.map((row, ri) => (
          <text
            key={row}
            x={HDR_X - 5}
            y={HDR_Y + ri * CH + CH / 2 + 4}
            textAnchor="end"
            fill="rgba(232,240,254,0.60)"
            fontSize="8.5"
            fontFamily="'Space Mono', monospace"
          >
            {row}
          </text>
        ))}

        {/* Cells */}
        {cells.map(({ ri, ci, x, y, score, fill, stroke, tag, tagColor, statusLabel }) => {
          const isSig = ci === 4
          const hist  = isSig ? (sigHistory[rows[ri]] ?? []) : []

          return (
            <g key={`${ri}-${ci}`}>
              {/* Cell background */}
              <rect
                x={x + 1} y={y + 1}
                width={CW - 2} height={CH - 2}
                rx={4} fill={fill} stroke={stroke} strokeWidth={0.5}
                style={{ transition: 'fill 0.6s ease, stroke 0.6s ease' }}
              />

              {isSig ? (
                /* ── SIG SCORE cell: number top-left + BUY/HOLD/SELL top-right + sparkline bottom ── */
                <>
                  {/* Score number — top-left */}
                  <text
                    x={x + 7} y={y + 15}
                    textAnchor="start"
                    fill="rgba(232,240,254,0.85)"
                    fontSize="10"
                    fontFamily="'Space Mono', monospace"
                    fontWeight="bold"
                  >
                    {Math.round(score * 100)}
                  </text>

                  {/* BUY/HOLD/SELL label — top-right */}
                  {statusLabel && (
                    <text
                      x={x + CW - 6} y={y + 15}
                      textAnchor="end"
                      fill={statusLabel === 'BUY' ? '#00E5FF' : statusLabel === 'SELL' ? '#BF00FF' : 'rgba(232,240,254,0.45)'}
                      fontSize="7.5"
                      fontFamily="'Space Mono', monospace"
                      fontWeight="bold"
                      style={{ filter: statusLabel !== 'HOLD' ? `drop-shadow(0 0 3px currentColor)` : undefined }}
                    >
                      {statusLabel}
                    </text>
                  )}

                  {/* Divider line between score area and sparkline */}
                  <line
                    x1={x + 4} y1={y + 19}
                    x2={x + CW - 4} y2={y + 19}
                    stroke="rgba(255,255,255,0.06)" strokeWidth={0.5}
                  />

                  {/* Sparkline — bottom portion of cell (y+21 to y+CH-4) */}
                  {hist.length >= 2 ? (
                    <>
                      {/* Area fill under sparkline */}
                      <path
                        d={`${sparklinePath(hist, x + 4, y + 21, CW - 10, CH - 27)} L ${(x + CW - 6).toFixed(1)},${(y + CH - 6).toFixed(1)} L ${(x + 4).toFixed(1)},${(y + CH - 6).toFixed(1)} Z`}
                        fill={score >= 0.62 ? 'rgba(0,229,255,0.06)' : score < 0.32 ? 'rgba(191,0,255,0.06)' : 'rgba(255,255,255,0.03)'}
                      />
                      {/* Sparkline line */}
                      <path
                        d={sparklinePath(hist, x + 4, y + 21, CW - 10, CH - 27)}
                        fill="none"
                        stroke={score >= 0.62 ? '#00E5FF' : score < 0.32 ? '#BF00FF' : 'rgba(232,240,254,0.4)'}
                        strokeWidth={1}
                        strokeLinejoin="round"
                        strokeLinecap="round"
                        style={{ transition: 'stroke 0.5s ease' }}
                      />
                    </>
                  ) : (
                    /* Placeholder dashed line when no history yet */
                    <line
                      x1={x + 4} y1={y + CH / 2 + 8}
                      x2={x + CW - 4} y2={y + CH / 2 + 8}
                      stroke="rgba(255,255,255,0.08)" strokeWidth={0.7} strokeDasharray="3 2"
                    />
                  )}
                </>
              ) : (
                /* ── Status cells (MOMENTUM/REGIME/RATES/SENTIMENT): number + sublabel ── */
                <>
                  {/* Numeric score — centered vertically */}
                  <text
                    x={x + CW / 2} y={y + CH / 2 - 1}
                    textAnchor="middle"
                    fill="rgba(232,240,254,0.75)"
                    fontSize="10"
                    fontFamily="'Space Mono', monospace"
                    style={{ transition: 'all 0.5s ease' }}
                  >
                    {Math.round(score * 100)}
                  </text>

                  {/* WATCH/STABLE sublabel — below number */}
                  {statusLabel && (
                    <text
                      x={x + CW / 2} y={y + CH / 2 + 10}
                      textAnchor="middle"
                      fill={statusLabel === 'WATCH' ? 'rgba(191,0,255,0.65)' : 'rgba(0,229,255,0.55)'}
                      fontSize="6"
                      fontFamily="'Space Mono', monospace"
                      letterSpacing="0.3"
                    >
                      {statusLabel}
                    </text>
                  )}

                  {/* Adjust/Reduce tag */}
                  {tag && (
                    <text
                      x={x + CW / 2} y={y + CH - 7}
                      textAnchor="middle"
                      fill={tagColor}
                      fontSize="6"
                      fontFamily="'Space Mono', monospace"
                      fontWeight="bold"
                    >
                      {tag}
                    </text>
                  )}
                </>
              )}
            </g>
          )
        })}

        {/* Grid hairlines */}
        {COLS.map((_, ci) => (
          <line
            key={`vl-${ci}`}
            x1={HDR_X + ci * CW} y1={HDR_Y}
            x2={HDR_X + ci * CW} y2={H}
            stroke="rgba(255,255,255,0.04)" strokeWidth={0.5}
          />
        ))}
        {rows.map((_, ri) => (
          <line
            key={`hl-${ri}`}
            x1={HDR_X} y1={HDR_Y + ri * CH}
            x2={W}     y2={HDR_Y + ri * CH}
            stroke="rgba(255,255,255,0.04)" strokeWidth={0.5}
          />
        ))}
      </svg>
    </div>
  )
}
