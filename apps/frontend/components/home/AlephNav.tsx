'use client'
import { useAuth } from '@/hooks/useAuth'
import { DataStatus } from '@/components/ui/DataStatus'
import type { StreamStatus } from '@/lib/types'

type NavTab = '관찰' | '실험' | '계좌' | '회고'

interface AlephNavProps {
  activeTab:    NavTab
  onTabChange:  (tab: NavTab) => void
  streamStatus: StreamStatus
}

const TABS: NavTab[] = ['관찰', '실험', '계좌', '회고']

export function AlephNav({ activeTab, onTabChange, streamStatus }: AlephNavProps) {
  const { user, signOut } = useAuth()

  const streamAvailability =
    streamStatus === 'LIVE'       ? 'full' as const :
    streamStatus === 'CONNECTING' ? 'full' as const : 'unavailable' as const

  const streamFreshness =
    streamStatus === 'LIVE'       ? 'fresh' as const :
    streamStatus === 'CONNECTING' ? 'unknown' as const : 'unknown' as const

  return (
    <header
      role="banner"
      style={{
        height: 'var(--a1-nav-h)',
        background: 'var(--a1-surface)',
        borderBottom: '1px solid var(--a1-border)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 var(--a1-space-5)',
        gap: 'var(--a1-space-5)',
        flexShrink: 0,
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      {/* Logo */}
      <a
        href="/"
        aria-label="Aleph One 홈"
        style={{
          display: 'flex', alignItems: 'baseline', gap: 4,
          textDecoration: 'none', flexShrink: 0,
        }}
      >
        <span style={{
          fontFamily: 'var(--a1-font-label)',
          fontWeight: 600, fontSize: 15,
          color: 'var(--a1-text)',
          letterSpacing: '-0.01em',
        }}>
          ALEPH
        </span>
        <span style={{
          fontFamily: 'var(--a1-font-label)',
          fontWeight: 300, fontSize: 15,
          color: 'var(--a1-accent)',
          letterSpacing: '-0.01em',
        }}>
          ONE
        </span>
      </a>

      {/* Navigation tabs */}
      <nav role="navigation" aria-label="주 메뉴">
        <ul
          role="tablist"
          aria-label="화면 탭"
          style={{ display: 'flex', gap: 2, listStyle: 'none', margin: 0, padding: 0 }}
        >
          {TABS.map(tab => (
            <li key={tab} role="presentation">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === tab}
                onClick={() => onTabChange(tab)}
                style={{
                  padding: '6px 14px',
                  borderRadius: 'var(--a1-radius-sm)',
                  border: 'none',
                  background: activeTab === tab ? 'var(--a1-accent-light)' : 'transparent',
                  color: activeTab === tab ? 'var(--a1-accent)' : 'var(--a1-text-secondary)',
                  fontFamily: 'var(--a1-font-body)',
                  fontSize: 13,
                  fontWeight: activeTab === tab ? 600 : 400,
                  cursor: 'pointer',
                  transition: 'background 0.15s, color 0.15s',
                  letterSpacing: '-0.01em',
                }}
              >
                {tab}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Stream status */}
      <DataStatus
        availability={streamAvailability}
        freshness={streamFreshness}
        source="스트림"
        compact
        detail={
          streamStatus === 'ERROR'
            ? '데이터 스트림에 연결할 수 없습니다. 잠시 후 자동으로 재연결을 시도합니다.'
            : streamStatus === 'CONNECTING'
            ? '서버에 연결 중입니다.'
            : undefined
        }
      />

      {/* User */}
      {user ? (
        <button
          type="button"
          onClick={signOut}
          aria-label="로그아웃"
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 10px',
            background: 'transparent',
            border: '1px solid var(--a1-border)',
            borderRadius: 'var(--a1-radius-sm)',
            cursor: 'pointer',
            fontFamily: 'var(--a1-font-body)',
            fontSize: 12,
            color: 'var(--a1-text-secondary)',
          }}
        >
          <span
            style={{
              width: 20, height: 20, borderRadius: '50%',
              background: 'var(--a1-accent-light)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 10, color: 'var(--a1-accent)', fontWeight: 600,
            }}
            aria-hidden="true"
          >
            {(user.email?.[0] ?? '?').toUpperCase()}
          </span>
          <span className="a1-sr-only" style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0,0,0,0)' }}>
            {user.email}
          </span>
        </button>
      ) : (
        <a
          href="/login"
          style={{
            padding: '4px 12px',
            background: 'var(--a1-accent)',
            color: '#fff',
            borderRadius: 'var(--a1-radius-sm)',
            textDecoration: 'none',
            fontSize: 12,
            fontFamily: 'var(--a1-font-body)',
            fontWeight: 500,
          }}
        >
          로그인
        </a>
      )}
    </header>
  )
}
