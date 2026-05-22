'use client'
/**
 * useMarketStream — consumes the SSE market stream from /api/stream/market.
 *
 * Maintains a rolling price history buffer (up to HISTORY_LEN points) per
 * ticker so that chart components can render sparklines without their own
 * accumulation logic.
 *
 * Falls back gracefully: if EventSource fails (e.g. server not ready),
 * `connected` is false and `data` stays null.  The LiveChart renders a
 * "DISCONNECTED" indicator and retries after 3 s.
 */

import { useEffect, useRef, useState } from 'react'

export interface MarketTick {
  type: 'market'
  prices: Record<string, number>
  portfolio_value: number
  ts: string
}

export interface MarketStreamState {
  data: MarketTick | null
  connected: boolean
  priceHistory: Record<string, number[]>
}

const HISTORY_LEN = 120  // 2 minutes at 1 s/tick
const RETRY_MS    = 3_000

export function useMarketStream(): MarketStreamState {
  const [data,      setData]      = useState<MarketTick | null>(null)
  const [connected, setConnected] = useState(false)
  const [history,   setHistory]   = useState<Record<string, number[]>>({})
  const histRef = useRef<Record<string, number[]>>({})
  const esRef   = useRef<EventSource | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    function connect() {
      const es = new EventSource('/api/stream/market')
      esRef.current = es

      es.onopen = () => setConnected(true)

      es.onmessage = (event: MessageEvent<string>) => {
        try {
          const tick = JSON.parse(event.data) as MarketTick
          // Accumulate history per ticker
          for (const [ticker, price] of Object.entries(tick.prices)) {
            if (!histRef.current[ticker]) histRef.current[ticker] = []
            histRef.current[ticker].push(price)
            if (histRef.current[ticker].length > HISTORY_LEN) {
              histRef.current[ticker].shift()
            }
          }
          setData(tick)
          setHistory({ ...histRef.current })
        } catch {
          // Ignore malformed events
        }
      }

      es.onerror = () => {
        setConnected(false)
        es.close()
        retryRef.current = setTimeout(connect, RETRY_MS)
      }
    }

    connect()

    return () => {
      esRef.current?.close()
      if (retryRef.current) clearTimeout(retryRef.current)
    }
  }, [])

  return { data, connected, priceHistory: history }
}
