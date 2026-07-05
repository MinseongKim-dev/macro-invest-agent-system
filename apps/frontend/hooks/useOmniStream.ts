'use client'
import { useState, useCallback } from 'react'

// ── Shared types ──────────────────────────────────────────────────────────────

export interface OmniMeta {
  regime?:     string
  phase?:      string
  confidence?: number
  signal?:     string
  health?:     number
}

export interface OmniWidget {
  type:   'metric' | 'alert'
  title:  string
  value?: string
  sub?:   string
  trend?: 'up' | 'down' | 'neutral'
  level?: 'HIGH' | 'MED' | 'LOW'
  text?:  string
}

export interface OmniResp {
  insight:    string
  action:     string
  confidence: number
  report?:    string
  widgets:    OmniWidget[]
}

export interface UseOmniStreamResult {
  busy:         boolean
  streaming:    boolean
  panelContent: string
  panelMeta:    OmniMeta | undefined
  panelQuery:   string
  resp:         OmniResp | null
  exec:         (query: string, onOpen?: () => void) => Promise<void>
  clearResp:    () => void
}

/**
 * Encapsulates the OMNI-COMMAND SSE streaming fetch.
 * Components call exec() with a query string; the hook manages all HTTP and
 * parse state.  Panel open/close remains the caller's responsibility.
 */
export function useOmniStream(): UseOmniStreamResult {
  const [busy,         setBusy]         = useState(false)
  const [streaming,    setStreaming]    = useState(false)
  const [panelContent, setPanelContent] = useState('')
  const [panelMeta,    setPanelMeta]    = useState<OmniMeta | undefined>()
  const [panelQuery,   setPanelQuery]   = useState('')
  const [resp,         setResp]         = useState<OmniResp | null>(null)

  const clearResp = useCallback(() => {
    setResp(null)
    setPanelContent('')
    setPanelMeta(undefined)
  }, [])

  const exec = useCallback(async (query: string, onOpen?: () => void) => {
    const q = query.trim()
    if (!q || busy) return

    setBusy(true)
    setResp(null)
    setPanelContent('')
    setPanelMeta(undefined)
    setPanelQuery(q)
    setStreaming(true)
    onOpen?.()

    try {
      const r = await fetch('/api/v1/intelligence/command/stream', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ query: q, persona: 'AGGRESSIVE' }),
      })
      if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`)

      const reader  = r.body.getReader()
      const decoder = new TextDecoder()
      let   buffer  = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === 'meta') {
              const regime = evt.macro_regime    ?? {}
              const health = evt.portfolio_health ?? {}
              const sig    = (evt.active_signals ?? [])[0]
              setPanelMeta({
                regime:     regime.regime_name,
                phase:      regime.market_phase,
                confidence: regime.confidence_score,
                signal:     sig?.action,
                health:     health.score,
              })
              const widgets: OmniWidget[] = []
              if (regime.regime_name)   widgets.push({ type: 'metric', title: 'MACRO REGIME',     value: regime.regime_name,                    sub:  regime.market_phase ?? '',  trend: (regime.confidence_score ?? 0.5) > 0.7 ? 'up' : 'down' })
              if (health.score != null) widgets.push({ type: 'metric', title: 'PORTFOLIO HEALTH', value: `${Math.round(health.score)}`,          sub:  health.source ?? '',        trend: health.score > 60 ? 'up' : 'down' })
              setResp({ insight: regime.regime_name ?? 'Analysis complete.', action: sig?.action ?? '', confidence: Math.round((sig?.probability ?? 0.5) * 100), report: '', widgets })
            } else if (evt.type === 'token') {
              setPanelContent(prev => prev + (evt.content ?? ''))
            } else if (evt.type === 'done') {
              setStreaming(false)
            }
          } catch { /* skip malformed SSE line */ }
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'NETWORK ERROR'
      setPanelContent(`NEURAL LINK ERROR — ${msg}`)
      setResp({ insight: `NEURAL LINK ERROR — ${msg}`, action: '', confidence: 0, report: '', widgets: [] })
      console.error('[useOmniStream] exec failed:', e)
    } finally {
      setBusy(false)
      setStreaming(false)
    }
  }, [busy])

  return { busy, streaming, panelContent, panelMeta, panelQuery, resp, exec, clearResp }
}
