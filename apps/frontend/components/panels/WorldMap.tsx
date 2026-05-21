'use client'
import { useEvents, useAlerts } from '@/hooks/useAlephData'
import type { ExternalEventDTO } from '@/lib/types'
import { seededRand } from '@/lib/utils'

// Simplified continent polygon paths in a 1000×470 viewBox
const CONTINENTS = [
  { id: 'NA', d: 'M 78 72 L 195 65 L 340 78 L 355 168 L 300 255 L 220 258 L 140 210 L 76 150 Z' },
  { id: 'SA', d: 'M 155 272 L 295 268 L 318 380 L 290 455 L 195 460 L 138 390 Z' },
  { id: 'EU', d: 'M 415 52 L 560 48 L 575 78 L 565 192 L 445 205 L 408 140 Z' },
  { id: 'AF', d: 'M 422 218 L 600 212 L 618 368 L 580 450 L 460 460 L 415 388 Z' },
  { id: 'AS', d: 'M 572 42 L 925 42 L 948 180 L 938 355 L 710 375 L 564 295 L 558 110 Z' },
  { id: 'OC', d: 'M 758 368 L 952 362 L 962 465 L 800 472 Z' },
]

// Region name → approx SVG coordinate
const REGION_POS: Record<string, [number, number]> = {
  'US': [185, 162], 'United States': [185, 162], 'North America': [210, 150],
  'EU': [492, 128], 'Europe': [492, 128], 'Euro Area': [492, 128],
  'CN': [782, 148], 'China': [782, 148],
  'JP': [875, 158], 'Japan': [875, 158],
  'UK': [452, 98],  'United Kingdom': [452, 98],
  'IN': [720, 210], 'India': [720, 210],
  'BR': [230, 355], 'Brazil': [230, 355],
  'AU': [850, 420], 'Australia': [850, 420],
  'RU': [680, 80],  'Russia': [680, 80],
  'KR': [855, 148], 'South Korea': [855, 148],
  'Global': [500, 240],
}

const EVENT_TYPE_COLOR: Record<string, string> = {
  central_bank_decision:   '#00E5FF',
  macro_release:           '#00FF88',
  geopolitical_development:'#FF5722',
  policy_announcement:     '#FF9800',
  market_catalyst:         '#BF00FF',
  earnings_event:          '#FFEA00',
  other:                   '#8899AA',
}

function eventPos(event: ExternalEventDTO): [number, number] {
  if (event.region && REGION_POS[event.region])      return REGION_POS[event.region]
  if (event.entity && REGION_POS[event.entity])       return REGION_POS[event.entity]
  // Deterministic hash fallback
  let h = 0
  for (const c of event.event_id) h = ((h << 5) - h + c.charCodeAt(0)) | 0
  return [90 + Math.abs(h % 810), 52 + Math.abs((h >> 6) % 360)]
}

export default function WorldMap({ className = '' }: { className?: string }) {
  const { data: eventsData } = useEvents(30)
  const { data: alertsData } = useAlerts()

  const events = eventsData?.events ?? []
  const alerts = alertsData?.alerts ?? []

  // Build seamless ticker content (doubled for infinite scroll)
  const tickerParts = [
    ...events.map((e) => `[${e.event_type.replace(/_/g, ' ').toUpperCase()}]  ${e.title}`),
    ...alerts.map((a) => `[ALERT · ${a.severity.toUpperCase()}]  ${a.message}`),
  ]
  if (tickerParts.length === 0) tickerParts.push('ALEPH-ONE  ·  GLOBAL INTELLIGENCE STREAM  ·  AWAITING LIVE DATA')
  const tickerText = tickerParts.join('     ·     ')
  const doubled    = tickerText + '          ·          ' + tickerText

  return (
    <div className={`relative w-full h-full overflow-hidden ${className}`}>

      {/* World SVG */}
      <svg viewBox="0 0 1000 470" className="absolute inset-0 w-full h-[calc(100%-28px)]">
        {/* Graticule */}
        {[200, 400, 600, 800].map((x) => (
          <line key={`v${x}`} x1={x} y1={0} x2={x} y2={470}
            stroke="rgba(255,255,255,0.035)" strokeWidth={0.5} />
        ))}
        {[120, 235, 350].map((y) => (
          <line key={`h${y}`} x1={0} y1={y} x2={1000} y2={y}
            stroke="rgba(255,255,255,0.035)" strokeWidth={0.5} />
        ))}

        {/* Continents */}
        {CONTINENTS.map((c) => (
          <path
            key={c.id}
            d={c.d}
            fill="rgba(26,26,46,0.75)"
            stroke="rgba(255,255,255,0.10)"
            strokeWidth={0.8}
          />
        ))}

        {/* Event heatmap dots */}
        {events.map((event, i) => {
          const [cx, cy] = eventPos(event)
          const color    = EVENT_TYPE_COLOR[event.event_type] ?? '#8899AA'
          const r        = 4 + seededRand(i * 17) * 3
          return (
            <g key={event.event_id}>
              <circle cx={cx} cy={cy} r={r}
                fill={color} opacity={0.75}
                style={{ filter: `drop-shadow(0 0 5px ${color})` }}
              />
              <circle cx={cx} cy={cy} r={r + 5}
                fill="none" stroke={color} strokeWidth={0.7} opacity={0.3}
              />
            </g>
          )
        })}
      </svg>

      {/* News ticker strip */}
      <div className="absolute bottom-0 left-0 right-0 h-7 overflow-hidden
        border-t border-[rgba(0,229,255,0.18)]
        bg-[rgba(8,8,26,0.82)] flex items-center gap-0">
        <span className="label-dim px-2 shrink-0 text-[rgba(0,229,255,0.6)]">INTEL ▶</span>
        <div className="flex-1 overflow-hidden">
          <span className="ticker-track text-[9px] text-[rgba(232,240,254,0.65)]">
            {doubled}
          </span>
        </div>
      </div>
    </div>
  )
}
