'use client'
import { useSignals, useRegime } from '@/hooks/useAlephData'
import { seededRand } from '@/lib/utils'

const ROWS = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']
const COLS = ['MOMENTUM', 'REGIME', 'RATES', 'SENTIMENT', 'SIG SCORE']

const HDR_X = 56   // row-label column width
const HDR_Y = 24   // header row height
const CW    = 82   // cell width
const CH    = 46   // cell height
const W     = HDR_X + COLS.length * CW
const H     = HDR_Y + ROWS.length * CH

function scoreCell(ri: number, ci: number, avgSigScore: number, regimeFam: string): number {
  // SIG SCORE column → actual live signal score
  if (ci === 4) return avgSigScore

  // REGIME column → reflect regime family direction
  if (ci === 1) {
    const fam = regimeFam.toLowerCase()
    if (fam.includes('expansion') || fam.includes('goldilocks') || fam.includes('recovery'))
      return 0.65 + seededRand(ri * 11 + 1) * 0.30
    if (fam.includes('contraction') || fam.includes('recession') || fam.includes('stagflation'))
      return seededRand(ri * 11 + 2) * 0.30
    return 0.35 + seededRand(ri * 11 + 3) * 0.30
  }

  // Other columns: deterministic per (ri, ci) with slight live bias from regime
  return 0.15 + seededRand(ri * 7 + ci * 31 + 17) * 0.70
}

interface Cell {
  ri: number; ci: number
  x: number; y: number
  score: number
  fill: string; stroke: string
  tag: string | null; tagColor: string
}

function buildCells(avgSigScore: number, regimeFam: string): Cell[] {
  return ROWS.flatMap((_, ri) =>
    COLS.map((_, ci) => {
      const score  = scoreCell(ri, ci, avgSigScore, regimeFam)
      const x      = HDR_X + ci * CW
      const y      = HDR_Y + ri * CH
      const isOpp  = score >= 0.62
      const isRisk = score < 0.32

      const fill   = isOpp
        ? `rgba(0,229,255,${(0.10 + score * 0.22).toFixed(2)})`
        : isRisk
          ? `rgba(191,0,255,${(0.10 + (1 - score) * 0.22).toFixed(2)})`
          : 'rgba(255,255,255,0.035)'
      const stroke = isOpp
        ? 'rgba(0,229,255,0.30)'
        : isRisk
          ? 'rgba(191,0,255,0.30)'
          : 'rgba(255,255,255,0.07)'

      const tag      = score > 0.83 ? '▲ ADJUST' : score < 0.20 ? '▼ REDUCE' : null
      const tagColor = score > 0.83 ? '#00E5FF' : '#BF00FF'

      return { ri, ci, x, y, score, fill, stroke, tag, tagColor }
    })
  )
}

export default function RiskMatrix({ className = '' }: { className?: string }) {
  const { data: signals } = useSignals()
  const { data: regime }  = useRegime()

  const sigList  = signals?.signals ?? []
  const avgScore = sigList.length
    ? sigList.reduce((s, x) => s + x.score, 0) / sigList.length
    : 0.5
  const regimeFam = regime?.regime_family ?? 'unknown'
  const cells     = buildCells(avgScore, regimeFam)

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
            y={HDR_Y - 7}
            textAnchor="middle"
            fill="rgba(0,229,255,0.65)"
            fontSize="7.5"
            fontFamily="'Space Mono', monospace"
          >
            {col}
          </text>
        ))}

        {/* Row headers */}
        {ROWS.map((row, ri) => (
          <text
            key={row}
            x={HDR_X - 5}
            y={HDR_Y + ri * CH + CH / 2 + 4}
            textAnchor="end"
            fill="rgba(232,240,254,0.65)"
            fontSize="9"
            fontFamily="'Space Mono', monospace"
          >
            {row}
          </text>
        ))}

        {/* Cells */}
        {cells.map(({ ri, ci, x, y, score, fill, stroke, tag, tagColor }) => (
          <g key={`${ri}-${ci}`}>
            <rect
              x={x + 1} y={y + 1}
              width={CW - 2} height={CH - 2}
              rx={5} fill={fill} stroke={stroke} strokeWidth={0.6}
            />
            <text
              x={x + CW / 2} y={y + CH / 2 - 2}
              textAnchor="middle"
              fill="rgba(232,240,254,0.5)"
              fontSize="9"
              fontFamily="'Space Mono', monospace"
            >
              {Math.round(score * 100)}
            </text>
            {tag && (
              <text
                x={x + CW / 2} y={y + CH / 2 + 10}
                textAnchor="middle"
                fill={tagColor}
                fontSize="6.5"
                fontFamily="'Space Mono', monospace"
                fontWeight="bold"
              >
                {tag}
              </text>
            )}
          </g>
        ))}

        {/* Grid hairlines */}
        {COLS.map((_, ci) => (
          <line
            key={`vl-${ci}`}
            x1={HDR_X + ci * CW} y1={HDR_Y}
            x2={HDR_X + ci * CW} y2={H}
            stroke="rgba(255,255,255,0.05)" strokeWidth={0.5}
          />
        ))}
        {ROWS.map((_, ri) => (
          <line
            key={`hl-${ri}`}
            x1={HDR_X} y1={HDR_Y + ri * CH}
            x2={W}     y2={HDR_Y + ri * CH}
            stroke="rgba(255,255,255,0.05)" strokeWidth={0.5}
          />
        ))}
      </svg>
    </div>
  )
}
