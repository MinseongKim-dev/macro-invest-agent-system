import dynamic from 'next/dynamic'
import AlphaPanel       from '@/components/layout/AlphaPanel'
import CommandTerminal  from '@/components/panels/CommandTerminal'
import RiskMatrix       from '@/components/panels/RiskMatrix'
import WorldMap         from '@/components/panels/WorldMap'

// THREE.js uses browser APIs — must skip SSR
const NetworkCanvas = dynamic(
  () => import('@/components/panels/NetworkCanvas'),
  {
    ssr: false,
    loading: () => (
      <div className="w-full h-full flex items-center justify-center
        text-[9px] text-[rgba(0,229,255,0.35)] tracking-widest uppercase">
        INITIALIZING NETWORK…
      </div>
    ),
  },
)

export default function Home() {
  return (
    /*
     * Layout: fixed StatusBar (40px top) + fixed WorldMap (176px bottom).
     * Main area fills the space between in a flex row.
     */
    <div
      className="flex flex-col"
      style={{ height: '100vh', paddingTop: '40px', paddingBottom: '176px' }}
    >
      {/* ── Scrollable content area ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left: Personal Alpha Panel */}
        <AlphaPanel />

        {/* Center: Terminal + Response Grid */}
        <main className="flex-1 flex flex-col gap-3 p-3 overflow-y-auto min-h-0">

          {/* OMNI Command Terminal */}
          <CommandTerminal />

          {/* Response Grid — 3D Network ╳ Risk Matrix */}
          <div className="grid grid-cols-2 gap-3 flex-1 min-h-0" style={{ minHeight: '300px' }}>

            {/* 3D Portfolio Network Map */}
            <div className="glass-card relative overflow-hidden">
              <span className="absolute top-2 left-3 z-10 label-dim text-[rgba(0,229,255,0.55)]">
                Portfolio Network Map
              </span>
              <NetworkCanvas className="w-full h-full" />
            </div>

            {/* Risk / Opportunity Matrix */}
            <div className="glass-card p-3 flex flex-col">
              <span className="label-dim text-[rgba(0,229,255,0.55)] mb-2">
                Risk · Opportunity Matrix
              </span>
              <div className="flex-1 min-h-0">
                <RiskMatrix className="w-full h-full" />
              </div>
            </div>

          </div>
        </main>
      </div>

      {/* ── Global Intel Stream (fixed bottom strip) ── */}
      <div
        className="fixed bottom-0 left-0 right-0 z-20
          border-t border-[rgba(0,229,255,0.14)]
          bg-[rgba(8,8,26,0.88)] backdrop-blur-[24px]"
        style={{ height: '176px' }}
      >
        <p className="label-dim px-3 pt-2 pb-1 text-[rgba(0,229,255,0.5)]">
          Global Intel Stream
        </p>
        <WorldMap className="w-full" style={{ height: 'calc(100% - 24px)' } as React.CSSProperties} />
      </div>
    </div>
  )
}
