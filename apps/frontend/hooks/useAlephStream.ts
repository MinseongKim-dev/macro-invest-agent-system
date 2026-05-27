'use client'
/**
 * useAlephStream — singleton SSE subscription with exponential-backoff reconnection.
 *
 * Design:
 * - One EventSource per page lifetime; all hook callers share the same connection.
 * - On error: closes the connection and schedules a retry with full jitter backoff
 *   (3 s → 6 s → 12 s → 30 s max).
 * - Reconnects immediately when the browser tab becomes visible after a disconnect.
 * - Retry counter resets every time the stream enters LIVE state.
 */

import { useEffect, useState } from 'react'
import type { AlephStreamData, StreamStatus } from '@/lib/types'

export interface AlephStreamState {
  data:   AlephStreamData | null
  status: StreamStatus
}

// ── Module-level singleton ────────────────────────────────────────────────────

type Listener = (data: AlephStreamData | null, status: StreamStatus) => void

let _es:         EventSource | null                  = null
let _retryTimer: ReturnType<typeof setTimeout> | null = null
let _retryCount  = 0
let _lastData:   AlephStreamData | null              = null
let _lastStatus: StreamStatus                        = 'CONNECTING'
const _listeners = new Set<Listener>()

const STREAM_URL   = '/api/v1/intelligence/stream?persona=AGGRESSIVE'
const BASE_RETRY   = 3_000   // 3 s
const MAX_RETRY    = 30_000  // 30 s cap

function _jitter(ms: number): number {
  return ms * (0.75 + Math.random() * 0.5)  // ±25% jitter
}

function _nextRetryMs(): number {
  return Math.min(BASE_RETRY * 2 ** _retryCount, MAX_RETRY)
}

function _notify(data: AlephStreamData | null, status: StreamStatus): void {
  _lastData   = data
  _lastStatus = status
  _listeners.forEach((fn) => fn(data, status))
}

function _scheduleRetry(): void {
  if (_retryTimer) return
  const delay = _jitter(_nextRetryMs())
  _retryCount = Math.min(_retryCount + 1, 5)  // cap exponent at 2^5 = 32×
  _notify(_lastData, 'ERROR')
  _retryTimer = setTimeout(() => {
    _retryTimer = null
    _connect()
  }, delay)
}

function _connect(): void {
  if (_es) return  // already connected

  _notify(_lastData, 'CONNECTING')
  const es = new EventSource(STREAM_URL)
  _es = es

  const handleFrame = (e: MessageEvent<string>): void => {
    try {
      const parsed = JSON.parse(e.data) as AlephStreamData
      if (parsed.status !== 'ERROR') {
        _retryCount = 0  // reset backoff on successful data
        _notify(parsed, 'LIVE')
      }
    } catch {
      // silently drop malformed SSE frames
    }
  }

  // sse-starlette emits named 'intelligence' events; fall back to onmessage
  es.addEventListener('intelligence', handleFrame)
  es.onmessage = handleFrame

  es.onerror = (): void => {
    es.close()
    _es = null
    _scheduleRetry()
  }
}

function _disconnect(): void {
  _es?.close()
  _es = null
  if (_retryTimer) {
    clearTimeout(_retryTimer)
    _retryTimer = null
  }
}

// Reconnect when the tab regains visibility (handles sleep/resume and tab-switch)
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && _listeners.size > 0 && !_es && !_retryTimer) {
      _retryCount = 0  // fresh reconnect, no penalty
      _connect()
    }
  })
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
    _connect()  // no-op if already connected
    return () => {
      _listeners.delete(listener)
      // Disconnect only when the last listener unmounts (full page teardown)
      if (_listeners.size === 0) _disconnect()
    }
  }, [])

  return state
}
