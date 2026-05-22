'use client'
import dynamic from 'next/dynamic'
import { useAlephStream } from '@/hooks/useAlephStream'
import AlphaPanel      from '@/components/layout/AlphaPanel'
import CommandTerminal from '@/components/panels/CommandTerminal'
import RiskMatrix      from '@/components/panels/RiskMatrix'
import WorldMap        from '@/components/panels/WorldMap'

// THREE.js and EventSource use browser APIs — skip SSR
const NetworkCanvas = dynamic(
  () => import('@/components/panels/NetworkCanvas'),
  {
    ssr: false,
    loading: () => (
      <div className="w-full h-full flex items-center justify-center
        text-[9px] text-[rgba(0,229,255,0.3)] tracking-widest uppercase">
        INITIALIZING NETWORK…
      </div>
    ),
  },
)

const LiveChart = dynamic(
  () => import('@/components/panels/LiveChart'),
  {
    ssr: false,
    loading: () => (
      <div className="glass-card p-3 flex items-center justify-center h-full
        text-[9px] text-[rgba(0,229,255,0.3)] tracking-widest uppercase">
        CONNECTING TO STREAM…
      </div>
    ),
  },
)

export default function Home() {
  const { data: streamData } = useAlephStream()

  return (
    /*
     * Fixed top:   StatusBar  (40 px)
     * Fixed bottom: WorldMap  (176 px)
     * Everything in between scrolls as a flex column.
     */
    <div
      className="flex flex-col"
      style={{ height: '100vh', paddingTop: '40px', paddingBottom: '176px' }}
    >
      {/* ── Main content ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Personal Alpha panel */}
        <AlphaPanel streamData={streamData} />

        {/* Center column */}
        <main className="flex-1 flex flex-col gap-3 p-3 overflow-y-auto min-h-0">

          {/* OMNI Command Terminal */}
          <CommandTerminal />

          {/* Response grid: 3D network map + Risk/Opportunity matrix */}
          <div className="grid grid-cols-2 gap-3" style={{ minHeight: '260px' }}>
            <div className="glass-card relative overflow-hidden">
              <span className="absolute top-2 left-3 z-10 label-dim text-[rgba(0,229,255,0.5)]">
                Portfolio Network Map
              </span>
              <NetworkCanvas className="w-full h-full" />
            </div>

            <div className="glass-card p-3 flex flex-col">
              <span className="label-dim text-[rgba(0,229,255,0.5)] mb-2">
                Risk · Opportunity Matrix
              </span>
              <div className="flex-1 min-h-0">
                <RiskMatrix
                  className="w-full h-full"
                  riskMatrix={streamData?.intelligence_synthesis.risk_matrix ?? null}
                />
              </div>
            </div>
          </div>

          {/* Phase 2: Live price chart (SSE stream) */}
          <LiveChart />

        </main>
      </div>

      {/* ── Global Intel Stream — fixed bottom strip ── */}
      <div
        className="fixed bottom-0 left-0 right-0 z-20
          border-t border-[rgba(0,229,255,0.13)]
          bg-[rgba(8,8,26,0.90)] backdrop-blur-[24px]"
        style={{ height: '176px' }}
      >
        <p className="label-dim px-3 pt-2 pb-0.5 text-[rgba(0,229,255,0.45)]">
          Global Intel Stream
        </p>
        <div style={{ height: 'calc(100% - 22px)' }}>
          <WorldMap className="w-full h-full" />
        </div>
      </div>
    </div>
  )
}
