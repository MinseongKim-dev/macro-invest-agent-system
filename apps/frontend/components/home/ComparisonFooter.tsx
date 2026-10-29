'use client'
import { DataStatus } from '@/components/ui/DataStatus'
import type { VirtualPortfolioSummary } from '@/lib/types'

interface ComparisonFooterProps {
  portfolio: VirtualPortfolioSummary | undefined
  isLoading: boolean
  error:     unknown
}

function formatKRW(v: number): string {
  if (Math.abs(v) >= 100_000_000) return `${(v / 100_000_000).toFixed(2)}억`
  if (Math.abs(v) >= 10_000)      return `${(v / 10_000).toFixed(1)}만`
  return v.toLocaleString('ko-KR')
}

function formatUSD(v: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
}

function PLChip({ pct, label }: { pct: number; label: string }) {
  const sign = pct >= 0 ? '+' : ''
  const color = pct >= 0 ? 'var(--a1-gain)' : pct < 0 ? 'var(--a1-loss)' : 'var(--a1-neutral-fin)'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 10, color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-label)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
        {label}
      </span>
      <span className="a1-num" style={{ fontSize: 15, fontWeight: 500, color, letterSpacing: '-0.02em' }}>
        {sign}{pct.toFixed(2)}%
      </span>
    </div>
  )
}

function AccountSummary({
  currency, account,
}: {
  currency: string
  account: { cash_balance: number; market_value: number; total_value: number; initial_balance: number; total_pl: number; total_pl_pct: number }
}) {
  const fmt = currency === 'KRW' ? formatKRW : formatUSD
  const currencyLabel = currency === 'KRW' ? '₩' : '$'

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 'var(--a1-space-5)',
      padding: '0 var(--a1-space-5)',
      flexWrap: 'wrap',
    }}>
      <div>
        <span style={{
          fontSize: 10, color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-label)',
          letterSpacing: '0.04em', textTransform: 'uppercase', display: 'block', marginBottom: 2,
        }}>
          {currency} 계좌
        </span>
        <span className="a1-num" style={{ fontSize: 17, fontWeight: 500, color: 'var(--a1-text)', letterSpacing: '-0.02em' }}>
          {currencyLabel}{fmt(account.total_value)}
        </span>
      </div>
      <div
        style={{
          width: 1, height: 28, background: 'var(--a1-border)', flexShrink: 0,
        }}
        aria-hidden="true"
      />
      <PLChip pct={account.total_pl_pct} label="총 손익" />
      <div style={{
        width: 1, height: 28, background: 'var(--a1-border)', flexShrink: 0,
      }} aria-hidden="true" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ fontSize: 10, color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-label)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          현금
        </span>
        <span className="a1-num" style={{ fontSize: 13, color: 'var(--a1-text-secondary)' }}>
          {currencyLabel}{fmt(account.cash_balance)}
        </span>
      </div>
    </div>
  )
}

export function ComparisonFooter({ portfolio, isLoading, error }: ComparisonFooterProps) {
  const footerStyle: React.CSSProperties = {
    minHeight: 'var(--a1-footer-h)',
    background: 'var(--a1-surface)',
    borderTop: '1px solid var(--a1-border)',
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--a1-space-3)',
    flexShrink: 0,
    padding: 'var(--a1-space-3) 0',
    overflowX: 'auto',
  }

  if (isLoading) {
    return (
      <footer style={footerStyle} aria-busy="true" aria-label="계좌 요약 로딩 중">
        <div style={{ display: 'flex', gap: 16, padding: '0 var(--a1-space-5)', alignItems: 'center' }}>
          {[120, 80, 60, 80].map((w, i) => (
            <div key={i} style={{
              width: w, height: 14, background: 'var(--a1-border)', borderRadius: 3,
              animation: 'a1-pulse 1.4s ease-in-out infinite', animationDelay: `${i * 0.1}s`,
            }} aria-hidden="true" />
          ))}
        </div>
      </footer>
    )
  }

  if (error) {
    return (
      <footer style={footerStyle} role="contentinfo">
        <div style={{ padding: '0 var(--a1-space-5)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <DataStatus availability="unavailable" freshness="unknown" compact />
          <span style={{ fontSize: 12, color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-body)' }}>
            계좌 데이터를 불러올 수 없습니다
          </span>
        </div>
      </footer>
    )
  }

  if (!portfolio || Object.keys(portfolio.accounts).length === 0) {
    return (
      <footer style={footerStyle} role="contentinfo">
        <div style={{ padding: '0 var(--a1-space-5)', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 12, color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-body)' }}>
            모의 투자를 시작하면 성과를 여기서 확인할 수 있습니다
          </span>
          <span style={{
            padding: '4px 10px', borderRadius: 'var(--a1-radius-sm)',
            background: 'var(--a1-accent-light)', color: 'var(--a1-accent)',
            fontSize: 12, fontFamily: 'var(--a1-font-body)', fontWeight: 500,
            cursor: 'pointer',
          }}>
            OMNI로 가설 작성하기
          </span>
        </div>
      </footer>
    )
  }

  const hasDemoFills = portfolio.holdings.some(h => h.live_price === 0)
  const accountEntries = Object.entries(portfolio.accounts)

  return (
    <footer style={footerStyle} role="contentinfo" aria-label="모의 계좌 요약">
      <div style={{
        display: 'flex', alignItems: 'center', gap: 'var(--a1-space-4)',
        padding: '0 var(--a1-space-5)',
        width: '100%', flexWrap: 'wrap',
      }}>
        <span style={{
          fontSize: 11, color: 'var(--a1-text-muted)', fontFamily: 'var(--a1-font-label)',
          letterSpacing: '0.06em', textTransform: 'uppercase', flexShrink: 0,
        }}>
          모의 계좌
        </span>

        {accountEntries.map(([currency, account]) => (
          <AccountSummary key={currency} currency={currency} account={account} />
        ))}

        <div style={{ flex: 1 }} />

        {hasDemoFills && (
          <DataStatus
            availability="partial"
            freshness="unknown"
            is_demo
            compact
            detail="과거 합성 시세 기반 체결이 포함되어 있습니다. 실제 성과와 다를 수 있습니다."
          />
        )}

        <DataStatus
          availability="full"
          freshness="fresh"
          source="가상 브로커"
          compact
        />

        <a
          href="#"
          style={{
            padding: '4px 10px',
            borderRadius: 'var(--a1-radius-sm)',
            background: 'transparent',
            border: '1px solid var(--a1-border)',
            color: 'var(--a1-text-secondary)',
            fontSize: 11, fontFamily: 'var(--a1-font-body)',
            textDecoration: 'none', flexShrink: 0,
          }}
        >
          계좌 상세 →
        </a>
      </div>
    </footer>
  )
}
