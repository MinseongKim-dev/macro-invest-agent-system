'use client'
import { DataStatus } from '@/components/ui/DataStatus'
import type { QuantScoreLatestResponse, RegimeLatestResponse, DimensionScoreDTO } from '@/lib/types'
import type { FeedItem } from './RelevantChangeFeed'

interface EvidencePanelProps {
  selectedItem: FeedItem | null
  regime:       RegimeLatestResponse | undefined
  quantScore:   QuantScoreLatestResponse | undefined
  isLoading:    boolean
}

const DIMENSION_KO: Record<string, string> = {
  growth:               '성장',
  inflation:            '인플레이션',
  labor:                '고용',
  policy:               '정책',
  financial_conditions: '금융 여건',
}

const DIMENSION_DESC: Record<string, string> = {
  growth:               'PMI, 소매판매 등 경기 확장 지표',
  inflation:            'CPI, FRED 인플레이션 시리즈',
  labor:                '실업률, 고용 변화',
  policy:               '기준금리, 연준 정책 방향',
  financial_conditions: '국채 금리 스프레드, 신용 환경',
}

function scoreBar(score: number) {
  const pct = Math.round(score * 100)
  const color =
    score >= 0.6 ? 'var(--a1-accent)' :
    score >= 0.4 ? 'var(--a1-warn)' :
    'var(--a1-error)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`점수 ${pct}%`}
        style={{
          flex: 1, height: 4, background: 'var(--a1-border)',
          borderRadius: 2, overflow: 'hidden',
        }}
      >
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 0.3s' }} />
      </div>
      <span className="a1-num" style={{ fontSize: 11, color: 'var(--a1-text-secondary)', minWidth: 32, textAlign: 'right' }}>
        {pct}
      </span>
    </div>
  )
}

function DimensionRow({ dim }: { dim: DimensionScoreDTO }) {
  const nameKo = DIMENSION_KO[dim.dimension] ?? dim.dimension
  const desc   = DIMENSION_DESC[dim.dimension] ?? ''
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingBottom: 10, borderBottom: '1px solid var(--a1-border-subtle)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{
          fontSize: 12, fontWeight: 500, color: 'var(--a1-text)',
          fontFamily: 'var(--a1-font-body)',
        }}>
          {nameKo}
        </span>
        <span style={{
          fontSize: 11, color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-body)',
        }}>
          {dim.level}
        </span>
      </div>
      {scoreBar(dim.score)}
      <p style={{ margin: 0, fontSize: 11, color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-body)' }}>
        {desc}
      </p>
    </div>
  )
}

function RegimeDetail({ regime }: { regime: RegimeLatestResponse }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <p style={{
          margin: '0 0 8px', fontSize: 12, color: 'var(--a1-text-secondary)',
          fontFamily: 'var(--a1-font-body)', lineHeight: 1.6,
        }}>
          {regime.rationale_summary || '분석 요약 없음'}
        </p>
        {regime.warnings.map((w, i) => (
          <p key={i} style={{
            margin: '4px 0 0', fontSize: 11, color: 'var(--a1-warn)',
            fontFamily: 'var(--a1-font-body)', lineHeight: 1.5,
          }}>
            ⚠ {w}
          </p>
        ))}
      </div>
    </div>
  )
}

function ItemDetail({ item }: { item: FeedItem }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <p style={{
          margin: '0 0 8px', fontSize: 13, fontWeight: 500,
          color: 'var(--a1-text)', fontFamily: 'var(--a1-font-body)',
          lineHeight: 1.4,
        }}>
          {item.title}
        </p>
        {item.summary && (
          <p style={{
            margin: '0 0 8px', fontSize: 12, color: 'var(--a1-text-secondary)',
            fontFamily: 'var(--a1-font-body)', lineHeight: 1.6,
          }}>
            {item.summary}
          </p>
        )}
      </div>
      <div style={{
        padding: '10px 12px',
        background: 'var(--a1-accent-light)',
        borderRadius: 'var(--a1-radius-sm)',
        border: '1px solid var(--a1-accent)22',
      }}>
        <p style={{
          margin: 0, fontSize: 12, fontWeight: 500,
          color: 'var(--a1-accent)', fontFamily: 'var(--a1-font-body)',
          marginBottom: 4,
        }}>
          왜 나와 관련 있는가
        </p>
        <p style={{ margin: 0, fontSize: 12, color: 'var(--a1-text-secondary)', fontFamily: 'var(--a1-font-body)', lineHeight: 1.5 }}>
          {item.relevance}
        </p>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style={{ fontSize: 11, color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-label)' }}>
          출처
        </span>
        {item.sourceUrl ? (
          <a
            href={item.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: 12, color: 'var(--a1-accent)',
              fontFamily: 'var(--a1-font-body)',
              textDecoration: 'none',
              borderBottom: '1px solid var(--a1-accent)44',
              width: 'fit-content',
            }}
          >
            {item.source} ↗
          </a>
        ) : (
          <span style={{ fontSize: 12, color: 'var(--a1-text-secondary)', fontFamily: 'var(--a1-font-body)' }}>
            {item.source}
          </span>
        )}
      </div>
      <DataStatus
        availability={item.provenance === 'observed' ? 'full' : 'partial'}
        freshness={item.freshness === 'fresh' ? 'fresh' : item.freshness === 'stale' ? 'stale' : 'unknown'}
        source={item.source}
        as_of={item.time}
      />
    </div>
  )
}

export function EvidencePanel({ selectedItem, regime, quantScore, isLoading }: EvidencePanelProps) {
  const panelStyle: React.CSSProperties = {
    width: 'var(--a1-panel-w)',
    flexShrink: 0,
    background: 'var(--a1-surface)',
    borderLeft: '1px solid var(--a1-border)',
    display: 'flex', flexDirection: 'column',
    overflowY: 'auto',
  }

  const headerStyle: React.CSSProperties = {
    padding: 'var(--a1-space-4)',
    borderBottom: '1px solid var(--a1-border-subtle)',
    flexShrink: 0,
  }

  return (
    <aside style={panelStyle} aria-label="근거 패널">
      <div style={headerStyle}>
        <h2 style={{
          margin: 0, fontSize: 12, fontWeight: 600,
          color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-label)',
          letterSpacing: '0.06em', textTransform: 'uppercase',
        }}>
          {selectedItem ? '선택된 항목 근거' : '현재 시장 분석'}
        </h2>
      </div>

      <div style={{ flex: 1, padding: 'var(--a1-space-4)', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 'var(--a1-space-4)' }}>
        {isLoading ? (
          <PanelSkeleton />
        ) : selectedItem ? (
          <ItemDetail item={selectedItem} />
        ) : regime ? (
          <RegimeDetail regime={regime} />
        ) : (
          <PanelEmpty />
        )}

        {/* Quant Score dimensions — always show when available */}
        {quantScore && !isLoading && (
          <section aria-label="퀀트 점수 상세">
            <h3 style={{
              margin: '0 0 10px', fontSize: 11, fontWeight: 600,
              color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-label)',
              letterSpacing: '0.06em', textTransform: 'uppercase',
            }}>
              퀀트 분석 ({quantScore.regime_label})
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {(['growth', 'inflation', 'labor', 'policy', 'financial_conditions'] as const).map(dim => (
                <DimensionRow key={dim} dim={quantScore[dim]} />
              ))}
            </div>
            <DataStatus
              availability="full"
              freshness="fresh"
              as_of={quantScore.as_of_date}
              source="퀀트 엔진"
              compact
            />
          </section>
        )}

        {/* Limitations notice */}
        <div style={{
          padding: '10px 12px',
          background: 'var(--a1-border-subtle)',
          borderRadius: 'var(--a1-radius-sm)',
          marginTop: 'auto',
        }}>
          <p style={{
            margin: 0, fontSize: 11, color: 'var(--a1-text-muted)',
            fontFamily: 'var(--a1-font-body)', lineHeight: 1.5,
          }}>
            이 분석은 투자 추천이 아닙니다. 관측된 지표에서 도출한 참고 정보입니다.
          </p>
        </div>
      </div>
    </aside>
  )
}

function PanelSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }} aria-hidden="true">
      {[100, 60, 80, 40].map((w, i) => (
        <div
          key={i}
          style={{
            height: 14, width: `${w}%`,
            background: 'var(--a1-border)',
            borderRadius: 3,
            animation: 'a1-pulse 1.4s ease-in-out infinite',
            animationDelay: `${i * 0.1}s`,
          }}
        />
      ))}
    </div>
  )
}

function PanelEmpty() {
  return (
    <p style={{
      margin: 0, fontSize: 12, color: 'var(--a1-text-muted)',
      fontFamily: 'var(--a1-font-body)', lineHeight: 1.6,
    }}>
      변화 목록에서 항목을 선택하면 관련 근거와 출처를 확인할 수 있습니다.
    </p>
  )
}
