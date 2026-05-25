import dynamic from 'next/dynamic'

// AlephDashboard uses browser APIs (EventSource, canvas) — skip SSR
const AlephDashboard = dynamic(
  () => import('@/components/AlephDashboard'),
  {
    ssr: false,
    loading: () => (
      <div style={{
        width: '100vw', height: '100vh',
        background: '#020b18',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11, color: 'rgba(0,229,255,0.4)',
        letterSpacing: '3px',
      }}>
        ALEPH-ONE INITIALIZING…
      </div>
    ),
  },
)

export default function Home() {
  return <AlephDashboard />
}
