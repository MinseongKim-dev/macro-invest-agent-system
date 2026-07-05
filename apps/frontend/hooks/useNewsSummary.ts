'use client'
import { useState, useEffect } from 'react'

interface NewsSummaryInput {
  title:   string
  source?: string | null
  entity?: string | null
}

export interface UseNewsSummaryResult {
  text:      string
  streaming: boolean
  done:      boolean
  error:     boolean
}

/**
 * Streams an AI market analysis for a news headline via POST /api/news/summarize.
 * Auto-triggers whenever `item` changes.  Pass null to reset / skip.
 */
export function useNewsSummary(item: NewsSummaryInput | null): UseNewsSummaryResult {
  const [text,      setText]      = useState('')
  const [streaming, setStreaming] = useState(false)
  const [done,      setDone]      = useState(false)
  const [error,     setError]     = useState(false)

  useEffect(() => {
    if (!item?.title) {
      setText(''); setDone(false); setError(false); setStreaming(false)
      return
    }
    setText('')
    setDone(false)
    setError(false)
    setStreaming(true)

    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/news/summarize', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({
            title:  item.title,
            source: item.source ?? '',
            entity: item.entity ?? '',
          }),
        })
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

        const reader  = res.body.getReader()
        const decoder = new TextDecoder()
        let   buffer  = ''

        while (true) {
          const { done: rd, value } = await reader.read()
          if (rd || cancelled) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            try {
              const evt = JSON.parse(line.slice(6))
              if (evt.type === 'token') setText(prev => prev + (evt.text ?? ''))
              if (evt.type === 'done')  setDone(true)
              if (evt.type === 'error') { setError(true); setDone(true) }
            } catch { /* skip malformed */ }
          }
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setError(true)
          console.error('[useNewsSummary] stream failed:', e)
        }
      } finally {
        if (!cancelled) setStreaming(false)
      }
    })()

    return () => { cancelled = true }
  }, [item?.title, item?.source, item?.entity])

  return { text, streaming, done, error }
}
