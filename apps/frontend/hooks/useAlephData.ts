'use client'
import useSWR from 'swr'
import { useAlephStream } from '@/hooks/useAlephStream'
import { fetchJson, endpoints } from '@/lib/api'
import type {
  RegimeLatestResponse,
  SignalsLatestResponse,
  EventsRecentResponse,
  AlertsRecentResponse,
} from '@/lib/types'

const POLL_FAST = 30_000   // 30s — regime + signals
const POLL_SLOW = 60_000   // 60s — events + alerts

const SWR_OPT = {
  revalidateOnFocus: false,
  shouldRetryOnError: true,
  errorRetryCount: 3,
}

export function useRegime() {
  return useSWR<RegimeLatestResponse>(
    endpoints.regime,
    fetchJson,
    { ...SWR_OPT, refreshInterval: POLL_FAST },
  )
}

export const useRegimeStatus = useRegime

export function useMacroSnapshot() {
  const { data } = useAlephStream()
  return data?.macro_indicators ?? null
}

export function useSignals(country = 'US') {
  return useSWR<SignalsLatestResponse>(
    endpoints.signals(country),
    fetchJson,
    { ...SWR_OPT, refreshInterval: POLL_FAST },
  )
}

export function useEvents(limit = 20) {
  return useSWR<EventsRecentResponse>(
    endpoints.events(limit),
    fetchJson,
    { ...SWR_OPT, refreshInterval: POLL_SLOW },
  )
}

export function useAlerts(limit = 10) {
  return useSWR<AlertsRecentResponse>(
    endpoints.alerts(limit),
    fetchJson,
    { ...SWR_OPT, refreshInterval: POLL_SLOW },
  )
}

export function useSectorSummary() {
  return useSWR<{ sectors: Array<{ name: string; change_pct: number }> }>(
    endpoints.sectorSummary,
    fetchJson,
    { ...SWR_OPT, refreshInterval: 30_000 },
  )
}

export function usePortfolio(period: '1D' | '1W' | '1M' | '3M' = '1D') {
  const { data: history, isLoading: histLoading } = useSWR<{
    points: Array<{ ts: string; value: number }>
    empty:  boolean
  }>(
    period !== '1D' ? endpoints.portfolioHistory(period) : null,
    fetchJson,
    { refreshInterval: 60_000 },
  )
  const { data: metrics } = useSWR<{
    sharpe: number | null
    beta:   number | null
    alpha:  number | null
  }>(
    endpoints.portfolioMetrics,
    fetchJson,
    { refreshInterval: 300_000 },
  )
  return { history, histLoading, metrics }
}
