'use client'
import dynamic from 'next/dynamic'

// AlephHome uses browser APIs (EventSource, SWR, localStorage) — skip SSR
const AlephHome = dynamic(
  () => import('@/components/AlephHome').then(m => ({ default: m.AlephHome })),
  {
    ssr: false,
    loading: () => (
      <div
        style={{
          width: '100vw',
          height: '100vh',
          background: '#F6F4EF',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: "'Inter', system-ui, sans-serif",
          fontSize: 13,
          color: '#8A9399',
          letterSpacing: '0.04em',
        }}
      >
        Aleph One
      </div>
    ),
  },
)

export default function Home() {
  return <AlephHome />
}
