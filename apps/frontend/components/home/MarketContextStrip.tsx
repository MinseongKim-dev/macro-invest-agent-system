'use client'
import { DataStatus } from '@/components/ui/DataStatus'
import type { RegimeLatestResponse } from '@/lib/types'

interface MarketContextStripProps {
  regime:      RegimeLatestResponse | undefined
  isLoading:   boolean
  error:       unknown
}

const REGIME_FAMILY_KO: Record<string, string> = {
  EXPANSION:         '확장',
  CONTRACTION:       '수축',
  RECOVERY:          '회복',
  STAGFLATION:       '스태그플레이션',
  DISINFLATION:      '디스인플레이션',
  POLICY_TIGHTENING: '긴축',
  UNCLEAR:           '불명확',
  MIXED:             '혼재',
  GOLDILOCKS:        '골디락스',
}

const CONFIDENCE_KO: Record<string, string> = {
  HIGH:         '높음',
  MEDIUM:       '보통',
  LOW:          '낮음',
  VERY_HIGH:    '매우 높음',
  VERY_LOW:     '매우 낮음',
  INSUFFICIENT: '데이터 부족',
}

function RegimeChip({ label }: { label: string }) {
  const isUnclear = label === 'UNCLEAR' || label === 'MIXED'
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 10px',
      borderRadius: 'var(--a1-radius-sm)',
      background: isUnclear ? 'var(--a1-warn-bg)' : 'var(--a1-accent-light)',
      border: `1px solid ${isUnclear ? 'var(--a1-warn)' : 'var(--a1-accent)'}22`,
      fontFamily: 'var(--a1-font-label)',
      fontSize: 12, fontWeight: 500,
      color: isUnclear ? 'var(--a1-warn)' : 'var(--a1-accent)',
      letterSpacing: '0.02em',
    }}>
      {REGIME_FAMILY_KO[label] ?? label}
    </span>
  )
}

export function MarketContextStrip({ regime, isLoading, error }: MarketContextStripProps) {
  const stripStyle: React.CSSProperties = {
    height: 'var(--a1-strip-h)',
    background: 'var(--a1-surface)',
    borderBottom: '1px solid var(--a1-border-subtle)',
    display: 'flex',
    alignItems: 'center',
    padding: '0 var(--a1-space-5)',
    gap: 'var(--a1-space-4)',
    flexShrink: 0,
    overflowX: 'auto',
  }

  if (isLoading) {
    return (
      <div style={stripStyle} aria-busy="true" aria-label="시장 컨텍스트 로딩 중">
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {[80, 120, 60].map((w, i) => (
            <div
              key={i}
              style={{
                width: w, height: 16,
                background: 'var(--a1-border)',
                borderRadius: 3,
                animation: 'a1-pulse 1.4s ease-in-out infinite',
                animationDelay: `${i * 0.15}s`,
              }}
            />
          ))}
        </div>
      </div>
    )
  }

  if (error || !regime) {
    return (
      <div style={stripStyle} role="alert">
        <DataStatus availability="unavailable" freshness="unknown" />
        <span style={{ fontSize: 12, color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-body)' }}>
          시장 체제 데이터를 불러올 수 없습니다
        </span>
      </div>
    )
  }

  const availability =
    regime.status === 'success'  ? 'full' as const :
    regime.status === 'degraded' ? 'degraded' as const :
    regime.status === 'stale'    ? 'partial' as const :
    regime.is_seeded             ? 'partial' as const : 'full' as const

  const freshness =
    regime.freshness_status === 'fresh' ? 'fresh' as const :
    regime.freshness_status === 'stale' ? 'stale' as const : 'unknown' as const

  const transitionText = regime.transition?.changed && regime.transition.transition_from_prior
    ? `${regime.transition.transition_from_prior} → ${REGIME_FAMILY_KO[regime.regime_label] ?? regime.regime_label}`
    : null

  return (
    <div style={stripStyle} role="region" aria-label="현재 시장 체제">
      {/* Regime family */}
      <RegimeChip label={regime.regime_label} />

      {/* Confidence */}
      <Divider />
      <span style={{ fontSize: 12, color: 'var(--a1-text-secondary)', fontFamily: 'var(--a1-font-body)' }}>
        신뢰도 {CONFIDENCE_KO[regime.confidence] ?? regime.confidence}
      </span>

      {/* Transition */}
      {transitionText && (
        <>
          <Divider />
          <span style={{ fontSize: 12, color: 'var(--a1-text-secondary)', fontFamily: 'var(--a1-font-body)' }}>
            체제 변화: {transitionText}
          </span>
        </>
      )}

      {/* Missing inputs warning */}
      {regime.missing_inputs.length > 0 && (
        <>
          <Divider />
          <span
            style={{
              fontSize: 11, color: 'var(--a1-warn)',
              fontFamily: 'var(--a1-font-body)',
            }}
            title={`누락된 지표: ${regime.missing_inputs.join(', ')}`}
          >
            지표 누락 {regime.missing_inputs.length}건
          </span>
        </>
      )}

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Data status + timestamp */}
      <DataStatus
        availability={availability}
        freshness={freshness}
        source={regime.is_seeded ? '합성 초기값' : '분석 엔진'}
        as_of={regime.regime_timestamp}
        detail={
          regime.is_seeded
            ? `실제 DB 데이터가 수집되기 전 합성 초기값으로 분석한 결과입니다. 지표: ${regime.missing_inputs.join(', ') || '없음'}`
            : regime.status === 'degraded'
            ? `일부 지표가 누락된 상태에서 분석했습니다. 신뢰도가 낮을 수 있습니다.`
            : undefined
        }
        compact
      />
    </div>
  )
}

function Divider() {
  return (
    <span
      aria-hidden="true"
      style={{
        width: 1, height: 14,
        background: 'var(--a1-border)',
        flexShrink: 0,
      }}
    />
  )
}
