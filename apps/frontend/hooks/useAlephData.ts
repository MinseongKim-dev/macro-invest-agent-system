'use client'
import useSWR from 'swr'
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
