'use client'
import { useState } from 'react'

type Availability = 'full' | 'partial' | 'degraded' | 'unavailable'
type Freshness    = 'fresh' | 'stale' | 'unknown'

export interface DataStatusProps {
  availability: Availability
  freshness:    Freshness
  source?:      string
  as_of?:       string | null
  is_demo?:     boolean
  compact?:     boolean
  detail?:      string          // expanded explanation when clicked
}

interface StatusConfig {
  dot:   string
  label: string
  bg:    string
  fg:    string
}

const STATUS: Record<string, StatusConfig> = {
  full_fresh:          { dot: 'var(--a1-success)', label: '실시간',         bg: 'var(--a1-success-bg)', fg: 'var(--a1-success)' },
  full_stale:          { dot: 'var(--a1-warn)',    label: '지연 시세',       bg: 'var(--a1-warn-bg)',    fg: 'var(--a1-warn)' },
  full_unknown:        { dot: 'var(--a1-demo)',    label: '확인 중',         bg: 'var(--a1-demo-bg)',    fg: 'var(--a1-demo)' },
  partial_fresh:       { dot: 'var(--a1-warn)',    label: '일부 데이터',     bg: 'var(--a1-warn-bg)',    fg: 'var(--a1-warn)' },
  partial_stale:       { dot: 'var(--a1-warn)',    label: '일부·지연',       bg: 'var(--a1-warn-bg)',    fg: 'var(--a1-warn)' },
  partial_unknown:     { dot: 'var(--a1-demo)',    label: '부분 데이터',     bg: 'var(--a1-demo-bg)',    fg: 'var(--a1-demo)' },
  degraded_fresh:      { dot: 'var(--a1-warn)',    label: '분석 제한',       bg: 'var(--a1-warn-bg)',    fg: 'var(--a1-warn)' },
  degraded_stale:      { dot: 'var(--a1-warn)',    label: '지연·분석 제한',  bg: 'var(--a1-warn-bg)',    fg: 'var(--a1-warn)' },
  degraded_unknown:    { dot: 'var(--a1-warn)',    label: '품질 저하',       bg: 'var(--a1-warn-bg)',    fg: 'var(--a1-warn)' },
  unavailable_fresh:   { dot: 'var(--a1-error)',   label: '데이터 없음',     bg: 'var(--a1-error-bg)',   fg: 'var(--a1-error)' },
  unavailable_stale:   { dot: 'var(--a1-error)',   label: '데이터 없음',     bg: 'var(--a1-error-bg)',   fg: 'var(--a1-error)' },
  unavailable_unknown: { dot: 'var(--a1-error)',   label: '데이터 없음',     bg: 'var(--a1-error-bg)',   fg: 'var(--a1-error)' },
}

function formatRelativeTime(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1)  return '방금'
  if (mins < 60) return `${mins}분 전`
  const h = Math.floor(mins / 60)
  if (h < 24)    return `${h}시간 전`
  return `${Math.floor(h / 24)}일 전`
}

/** Compact dot+label variant — for inline use inside text */
function DataStatusCompact({ availability, freshness, is_demo }: DataStatusProps) {
  const key = `${availability}_${freshness}`
  const cfg = STATUS[key] ?? STATUS.unavailable_unknown
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <span
        style={{
          width: 6, height: 6, borderRadius: '50%',
          background: is_demo ? 'var(--a1-demo)' : cfg.dot,
          display: 'inline-block', flexShrink: 0,
        }}
        aria-hidden="true"
      />
      <span style={{
        fontSize: 11, fontFamily: 'var(--a1-font-label)',
        color: is_demo ? 'var(--a1-demo)' : cfg.fg,
        letterSpacing: '0.02em',
      }}>
        {is_demo ? 'DEMO' : cfg.label}
      </span>
    </span>
  )
}

/** Full badge variant — standalone status display */
export function DataStatus(props: DataStatusProps) {
  const { availability, freshness, source, as_of, is_demo, compact, detail } = props
  const [expanded, setExpanded] = useState(false)

  if (compact) return <DataStatusCompact {...props} />

  const key = `${availability}_${freshness}`
  const cfg = STATUS[key] ?? STATUS.unavailable_unknown

  const dotColor  = is_demo ? 'var(--a1-demo)' : cfg.dot
  const bgColor   = is_demo ? 'var(--a1-demo-bg)' : cfg.bg
  const fgColor   = is_demo ? 'var(--a1-demo)' : cfg.fg
  const labelText = is_demo ? 'DEMO · 실거래 아님' : cfg.label

  return (
    <div style={{ display: 'inline-block' }}>
      <button
        type="button"
        onClick={() => detail && setExpanded(v => !v)}
        aria-expanded={detail ? expanded : undefined}
        aria-label={`데이터 상태: ${labelText}`}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '3px 8px', borderRadius: 'var(--a1-radius-sm)',
          background: bgColor,
          border: `1px solid ${dotColor}33`,
          cursor: detail ? 'pointer' : 'default',
          fontFamily: 'inherit',
        }}
      >
        <span
          style={{ width: 6, height: 6, borderRadius: '50%', background: dotColor, flexShrink: 0 }}
          aria-hidden="true"
        />
        <span style={{ fontSize: 11, fontFamily: 'var(--a1-font-label)', color: fgColor, letterSpacing: '0.02em' }}>
          {labelText}
          {source && !is_demo ? ` · ${source}` : ''}
        </span>
        {as_of && !is_demo && (
          <span style={{ fontSize: 10, color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-data)' }}>
            {formatRelativeTime(as_of)}
          </span>
        )}
        {detail && (
          <span style={{ fontSize: 10, color: fgColor, marginLeft: 2 }} aria-hidden="true">
            {expanded ? '▲' : '▼'}
          </span>
        )}
      </button>
      {expanded && detail && (
        <div style={{
          marginTop: 4, padding: '6px 10px',
          background: bgColor, border: `1px solid ${dotColor}33`,
          borderRadius: 'var(--a1-radius-sm)',
          fontSize: 12, color: 'var(--a1-text-secondary)',
          fontFamily: 'var(--a1-font-body)', lineHeight: 1.5,
          maxWidth: 260,
        }}>
          {detail}
        </div>
      )}
    </div>
  )
}
