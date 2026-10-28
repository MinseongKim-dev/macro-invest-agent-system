'use client'
import { useState, useCallback } from 'react'
import { AlephNav } from '@/components/home/AlephNav'
import { MarketContextStrip } from '@/components/home/MarketContextStrip'
import { RelevantChangeFeed, type FeedItem } from '@/components/home/RelevantChangeFeed'
import { EvidencePanel } from '@/components/home/EvidencePanel'
import { ComparisonFooter } from '@/components/home/ComparisonFooter'
import { useAlephStream } from '@/hooks/useAlephStream'
import { useRegime, useEvents, useAlerts, useVirtualPortfolio, useQuantScore } from '@/hooks/useAlephData'
import type { StreamStatus } from '@/lib/types'

// ─── Tab content ──────────────────────────────────────────────────────────────

function TabPlaceholder({ title, description }: { title: string; description: string }) {
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: 'var(--a1-space-7)',
      gap: 'var(--a1-space-3)',
    }}>
      <h2 style={{
        margin: 0, fontSize: 18, fontWeight: 500,
        color: 'var(--a1-text)', fontFamily: 'var(--a1-font-body)',
        letterSpacing: '-0.01em',
      }}>
        {title}
      </h2>
      <p style={{
        margin: 0, fontSize: 14, color: 'var(--a1-text-muted)',
        fontFamily: 'var(--a1-font-body)', lineHeight: 1.6,
        maxWidth: 400, textAlign: 'center',
      }}>
        {description}
      </p>
    </div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────────

export function AlephHome() {
  const [activeTab, setActiveTab] = useState<'관찰' | '실험' | '계좌' | '회고'>('관찰')
  const [selectedItem, setSelectedItem] = useState<FeedItem | null>(null)

  const { status: streamStatus } = useAlephStream()
  const { data: regime, isLoading: regimeLoading, error: regimeError } = useRegime()
  const { data: eventsData, isLoading: eventsLoading, error: eventsError } = useEvents(20)
  const { data: alertsData } = useAlerts(10)
  const { data: portfolio, isLoading: portfolioLoading, error: portfolioError } = useVirtualPortfolio()
  const { data: quantScore, isLoading: quantLoading } = useQuantScore()

  const handleSelect = useCallback((item: FeedItem) => {
    setSelectedItem(prev => prev?.id === item.id ? null : item)
  }, [])

  const regimeChange = (() => {
    if (!regime?.transition?.changed || !regime.transition.transition_from_prior) return null
    return `${regime.transition.transition_from_prior} → ${regime.regime_label}`
  })()

  return (
    <div
      className="a1-root"
      data-theme="a1"
      style={{ height: '100vh', overflow: 'hidden' }}
    >
      {/* Keyframe for loading skeletons */}
      <style>{`
        @keyframes a1-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.45; }
        }
      `}</style>

      {/* A: Navigation */}
      <AlephNav
        activeTab={activeTab}
        onTabChange={setActiveTab}
        streamStatus={streamStatus}
      />

      {/* B: Market context strip — only on 관찰 tab */}
      {activeTab === '관찰' && (
        <MarketContextStrip
          regime={regime}
          isLoading={regimeLoading}
          error={regimeError}
        />
      )}

      {/* Main body */}
      <main
        style={{
          flex: 1, display: 'flex',
          overflow: 'hidden', minHeight: 0,
        }}
        role="main"
        aria-label={`${activeTab} 화면`}
      >
        {activeTab === '관찰' ? (
          <>
            {/* C: Central main area */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
              <RelevantChangeFeed
                events={eventsData?.events ?? []}
                alerts={alertsData?.alerts ?? []}
                regimeChange={regimeChange}
                isLoading={eventsLoading}
                error={eventsError}
                selectedId={selectedItem?.id ?? null}
                onSelect={handleSelect}
              />
            </div>

            {/* D: Right evidence panel — hidden on mobile via CSS */}
            <div className="a1-evidence-panel-wrapper">
              <EvidencePanel
                selectedItem={selectedItem}
                regime={regime}
                quantScore={quantScore}
                isLoading={regimeLoading || quantLoading}
              />
            </div>
          </>
        ) : activeTab === '실험' ? (
          <TabPlaceholder
            title="실험 공간"
            description="가설을 작성하고, 백테스트와 모의 투자로 검증하는 공간입니다. 준비 중입니다."
          />
        ) : activeTab === '계좌' ? (
          <TabPlaceholder
            title="모의 계좌"
            description="OMNI 명령어로 가상 주문을 실행하고 성과를 추적할 수 있습니다."
          />
        ) : (
          <TabPlaceholder
            title="회고"
            description="과거 판단과 실제 결과를 비교하고 투자 논리를 개선하는 공간입니다. 준비 중입니다."
          />
        )}
      </main>

      {/* E: Comparison footer */}
      <ComparisonFooter
        portfolio={portfolio}
        isLoading={portfolioLoading}
        error={portfolioError}
      />

      {/* Mobile responsive styles */}
      <style>{`
        @media (max-width: 768px) {
          .a1-evidence-panel-wrapper {
            display: none;
          }
        }
        @media (min-width: 769px) {
          .a1-evidence-panel-wrapper {
            display: flex;
          }
        }
      `}</style>
    </div>
  )
}
