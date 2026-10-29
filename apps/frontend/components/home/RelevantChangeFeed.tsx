'use client'
import { useState } from 'react'
import { DataStatus } from '@/components/ui/DataStatus'
import type { ExternalEventDTO, AlertEventDTO } from '@/lib/types'

export interface FeedItem {
  id:        string
  type:      'event' | 'alert' | 'regime'
  title:     string
  summary:   string | null
  relevance: string          // why it matters
  source:    string
  sourceUrl: string | null
  entity:    string | null
  time:      string
  provenance: string         // 'observed' | 'synthetic' | 'mixed'
  freshness: string          // 'fresh' | 'stale' | 'unknown'
  severity?: 'info' | 'warning' | 'critical'
}

interface RelevantChangeFeedProps {
  events:       ExternalEventDTO[]
  alerts:       AlertEventDTO[]
  regimeChange: string | null    // e.g. "EXPANSION → CONTRACTION"
  isLoading:    boolean
  error:        unknown
  selectedId:   string | null
  onSelect:     (item: FeedItem) => void
}

function toFeedItem(ev: ExternalEventDTO): FeedItem {
  return {
    id:        ev.event_id,
    type:      'event',
    title:     ev.title,
    summary:   ev.summary,
    relevance: ev.affected_domains.length > 0
      ? `영향 도메인: ${ev.affected_domains.slice(0, 2).join(', ')}`
      : ev.region ? `지역: ${ev.region}` : '글로벌 이슈',
    source:    ev.source,
    sourceUrl: ev.source_url,
    entity:    ev.entity,
    time:      ev.published_at ?? ev.occurred_at,
    provenance: ev.provenance,
    freshness: ev.freshness,
  }
}

function alertToFeedItem(al: AlertEventDTO): FeedItem {
  return {
    id:        al.alert_id,
    type:      'alert',
    title:     al.rule_name,
    summary:   al.message,
    relevance: al.source_regime && al.target_regime
      ? `체제 변화: ${al.source_regime} → ${al.target_regime}`
      : al.indicator_type ?? '시장 알림',
    source:    'ALEPH ONE 알림',
    sourceUrl: null,
    entity:    al.country,
    time:      al.triggered_at,
    provenance: 'observed',
    freshness: 'fresh',
    severity:  al.severity,
  }
}

function formatTime(isoString: string): string {
  const d = new Date(isoString)
  if (isNaN(d.getTime())) return ''
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 60)  return `${mins}분 전`
  if (mins < 1440) return `${Math.floor(mins / 60)}시간 전`
  return d.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })
}

function SeverityBar({ severity }: { severity?: 'info' | 'warning' | 'critical' }) {
  if (!severity) return null
  const color =
    severity === 'critical' ? 'var(--a1-error)' :
    severity === 'warning'  ? 'var(--a1-warn)' :
    'var(--a1-accent)'
  return (
    <span
      aria-hidden="true"
      style={{
        position: 'absolute', left: 0, top: 0, bottom: 0,
        width: 3, background: color, borderRadius: '4px 0 0 4px',
      }}
    />
  )
}

function FeedCard({ item, selected, onSelect }: { item: FeedItem; selected: boolean; onSelect: () => void }) {
  return (
    <article
      aria-selected={selected}
      style={{
        position: 'relative',
        padding: '14px 16px',
        background: selected ? 'var(--a1-accent-light)' : 'var(--a1-surface)',
        border: `1px solid ${selected ? 'var(--a1-accent)' : 'var(--a1-border)'}`,
        borderRadius: 'var(--a1-radius-md)',
        cursor: 'pointer',
        transition: 'border-color 0.15s, background 0.15s',
      }}
      onClick={onSelect}
      onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && onSelect()}
      tabIndex={0}
      role="button"
    >
      <SeverityBar severity={item.severity} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
        <h3 style={{
          margin: 0, fontSize: 13, fontWeight: 500,
          color: selected ? 'var(--a1-accent)' : 'var(--a1-text)',
          fontFamily: 'var(--a1-font-body)',
          lineHeight: 1.4,
        }}>
          {item.title}
        </h3>
        <time
          dateTime={item.time}
          style={{ fontSize: 11, color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-data)', flexShrink: 0 }}
        >
          {formatTime(item.time)}
        </time>
      </div>
      {item.summary && (
        <p style={{
          margin: '0 0 6px', fontSize: 12,
          color: 'var(--a1-text-secondary)', fontFamily: 'var(--a1-font-body)',
          lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>
          {item.summary}
        </p>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, color: 'var(--a1-accent)', fontFamily: 'var(--a1-font-body)' }}>
          {item.relevance}
        </span>
        {item.entity && (
          <span style={{
            fontSize: 10, padding: '1px 6px', borderRadius: 3,
            background: 'var(--a1-border-subtle)', color: 'var(--a1-text-muted)',
            fontFamily: 'var(--a1-font-label)',
          }}>
            {item.entity}
          </span>
        )}
        <DataStatus
          availability={item.provenance === 'observed' ? 'full' : item.provenance === 'synthetic' ? 'partial' : 'partial'}
          freshness={item.freshness === 'fresh' ? 'fresh' : item.freshness === 'stale' ? 'stale' : 'unknown'}
          source={item.source}
          compact
        />
      </div>
    </article>
  )
}

export function RelevantChangeFeed({
  events, alerts, regimeChange, isLoading, error, selectedId, onSelect,
}: RelevantChangeFeedProps) {
  const [filterType, setFilterType] = useState<'all' | 'event' | 'alert'>('all')

  const allAlertItems = alerts.map(alertToFeedItem)
  const allEventItems = events.map(toFeedItem)

  const combined: FeedItem[] = [
    ...allAlertItems,
    ...allEventItems,
  ].sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())

  const filtered = combined.filter(item =>
    filterType === 'all' ? true : item.type === filterType
  )

  return (
    <section
      aria-label="나에게 중요한 변화"
      style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}
    >
      {/* Header */}
      <div style={{
        padding: 'var(--a1-space-4) var(--a1-space-4) var(--a1-space-2)',
        display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
        gap: 8, flexShrink: 0,
      }}>
        <div>
          <h2 style={{
            margin: 0, fontSize: 15, fontWeight: 600,
            color: 'var(--a1-text)', fontFamily: 'var(--a1-font-body)',
            letterSpacing: '-0.01em',
          }}>
            지금, 나에게 중요한 변화
          </h2>
          {regimeChange && (
            <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--a1-warn)', fontFamily: 'var(--a1-font-body)' }}>
              체제 변화 감지: {regimeChange}
            </p>
          )}
        </div>
        {/* Filter buttons */}
        <div style={{ display: 'flex', gap: 2 }}>
          {(['all', 'alert', 'event'] as const).map(f => (
            <button
              key={f}
              type="button"
              aria-pressed={filterType === f}
              onClick={() => setFilterType(f)}
              style={{
                padding: '3px 8px', borderRadius: 'var(--a1-radius-sm)',
                border: '1px solid var(--a1-border)',
                background: filterType === f ? 'var(--a1-text)' : 'transparent',
                color: filterType === f ? 'var(--a1-surface)' : 'var(--a1-text-secondary)',
                fontSize: 11, fontFamily: 'var(--a1-font-label)',
                cursor: 'pointer',
              }}
            >
              {f === 'all' ? '전체' : f === 'alert' ? '알림' : '뉴스'}
            </button>
          ))}
        </div>
      </div>

      {/* Feed content */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '0 var(--a1-space-4) var(--a1-space-4)',
        display: 'flex', flexDirection: 'column', gap: var_space(2),
      }}>
        {isLoading ? (
          <FeedSkeleton />
        ) : error ? (
          <FeedError />
        ) : filtered.length === 0 ? (
          <FeedEmpty hasAnyData={combined.length > 0} />
        ) : (
          filtered.map(item => (
            <FeedCard
              key={item.id}
              item={item}
              selected={selectedId === item.id}
              onSelect={() => onSelect(item)}
            />
          ))
        )}
      </div>
    </section>
  )
}

// ─── Sub-components ────────────────────────────────────────────────────────

function var_space(n: 1 | 2 | 3 | 4 | 5 | 6 | 7): string {
  return `var(--a1-space-${n})`
}

function FeedSkeleton() {
  return (
    <>
      {[1, 2, 3].map(i => (
        <div
          key={i}
          style={{
            height: 88, borderRadius: 'var(--a1-radius-md)',
            background: 'var(--a1-border-subtle)',
            animation: 'a1-pulse 1.4s ease-in-out infinite',
            animationDelay: `${i * 0.1}s`,
          }}
          aria-hidden="true"
        />
      ))}
    </>
  )
}

function FeedError() {
  return (
    <div
      role="alert"
      style={{
        padding: 'var(--a1-space-5)',
        border: '1px solid var(--a1-error-bg)',
        borderRadius: 'var(--a1-radius-md)',
        background: 'var(--a1-error-bg)',
        display: 'flex', flexDirection: 'column', gap: 6,
      }}
    >
      <DataStatus availability="unavailable" freshness="unknown" />
      <p style={{ margin: 0, fontSize: 13, color: 'var(--a1-error)', fontFamily: 'var(--a1-font-body)' }}>
        뉴스 데이터를 불러올 수 없습니다
      </p>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--a1-text-secondary)', fontFamily: 'var(--a1-font-body)' }}>
        데이터 서버에 연결 중입니다. 잠시 후 자동으로 재시도합니다.
      </p>
    </div>
  )
}

function FeedEmpty({ hasAnyData }: { hasAnyData: boolean }) {
  return (
    <div style={{
      padding: 'var(--a1-space-7) var(--a1-space-5)',
      display: 'flex', flexDirection: 'column', gap: 12,
      alignItems: 'flex-start',
    }}>
      <p style={{
        margin: 0, fontSize: 14, color: 'var(--a1-text-secondary)',
        fontFamily: 'var(--a1-font-body)', lineHeight: 1.6,
      }}>
        {hasAnyData
          ? '선택한 필터에 해당하는 변화가 없습니다.'
          : '아직 수집된 변화 정보가 없습니다.'}
      </p>
      {!hasAnyData && (
        <p style={{
          margin: 0, fontSize: 12, color: 'var(--a1-text-muted)',
          fontFamily: 'var(--a1-font-body)', lineHeight: 1.6,
        }}>
          관심 종목을 추가하면 해당 종목과 관련된 시장 변화를 이곳에서 확인할 수 있습니다.
          가설이 없어도 관심 종목 탐색과 모의 투자를 바로 시작할 수 있습니다.
        </p>
      )}
    </div>
  )
}
