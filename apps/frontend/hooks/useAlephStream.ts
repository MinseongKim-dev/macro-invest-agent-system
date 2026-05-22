'use client'
/**
 * useAlephStream — subscribes to the Aleph-One SSE intelligence stream.
 *
 * Singleton pattern: multiple components may call this hook, but only ONE
 * EventSource connection is created per page lifetime.  All callers receive
 * the same data via their own React state slice.
 *
 * Stream URL: /api/v1/intelligence/stream (Next.js Route Handler → aleph-api)
 */

import { useEffect, useState } from 'react'
import type { AlephStreamData, StreamStatus } from '@/lib/types'

export interface AlephStreamState {
  data:   AlephStreamData | null
  status: StreamStatus
}

// ── Module-level singleton ────────────────────────────────────────────────────

type Listener = (data: AlephStreamData | null, status: StreamStatus) => void

let _es:         EventSource | null               = null
let _retryTimer: ReturnType<typeof setTimeout> | null = null
let _lastData:   AlephStreamData | null           = null
let _lastStatus: StreamStatus                     = 'CONNECTING'
const _listeners = new Set<Listener>()

const STREAM_URL = '/api/v1/intelligence/stream?persona=AGGRESSIVE'
const RETRY_MS   = 3_000

function _notify(data: AlephStreamData | null, status: StreamStatus): void {
  _lastData   = data
  _lastStatus = status
  _listeners.forEach((fn) => fn(data, status))
}

function _connect(): void {
  if (_es) return  // already connected

  const es = new EventSource(STREAM_URL)
  _es = es

  const handleFrame = (e: MessageEvent<string>): void => {
    try {
      const parsed = JSON.parse(e.data) as AlephStreamData
      if (parsed.status !== 'ERROR') _notify(parsed, 'LIVE')
    } catch {
      // ignore malformed SSE frames
    }
  }

  // sse-starlette emits named 'intelligence' events; fall back to onmessage
  es.addEventListener('intelligence', handleFrame)
  es.onmessage = handleFrame

  es.onerror = (): void => {
    _es?.close()
    _es = null
    _notify(_lastData, 'ERROR')
    _retryTimer = setTimeout(_connect, RETRY_MS)
  }
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useAlephStream(): AlephStreamState {
  const [state, setState] = useState<AlephStreamState>({
    data:   _lastData,
    status: _lastStatus,
  })

  useEffect(() => {
    const listener: Listener = (data, status) => setState({ data, status })
    _listeners.add(listener)
    _connect()                          // no-op if already connected
    return () => { _listeners.delete(listener) }
  }, [])

  return state
}
