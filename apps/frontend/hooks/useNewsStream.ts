'use client'
import useSWR from 'swr'
import type { ExternalEventDTO } from '@/lib/types'

const fetcher = (url: string) => fetch(url).then(r => r.json())

export function useNewsStream(limit = 15): ExternalEventDTO[] {
  const { data } = useSWR(
    `/api/events/recent?limit=${limit}`,
    fetcher,
    { refreshInterval: 30_000, revalidateOnFocus: false },
  )
  return (data?.events as ExternalEventDTO[]) ?? []
}
