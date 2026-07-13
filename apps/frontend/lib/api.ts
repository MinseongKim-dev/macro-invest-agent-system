/**
 * SWR-compatible fetch helper. Throws on non-2xx so SWR surfaces errors correctly.
 * All endpoints proxy through Next.js rewrites → FastAPI at /api/*
 */
export async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: 'no-store' })
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`)
  }
  return res.json() as Promise<T>
}

export const endpoints = {
  regime:           '/api/regimes/latest',
  regimeCompare:    '/api/regimes/compare',
  signals:          (country = 'US')   => `/api/signals/latest?country=${country}`,
  events:           (limit = 20)       => `/api/events/recent?limit=${limit}`,
  alerts:           (limit = 10)       => `/api/alerts/recent?limit=${limit}`,
  tickerDetail:     (ticker: string)   => `/api/tickers/${ticker}/detail`,
  portfolioHistory: (period: string)   => `/api/tickers/portfolio/history?period=${period}`,
  portfolioMetrics: '/api/tickers/portfolio/metrics',
  portfolioSummary: '/api/v1/portfolio/summary',
  portfolioReset:   '/api/v1/portfolio/reset',
  sectorSummary:    '/api/tickers/sector/summary',
  newsSummarize:    '/api/news/summarize',
  scenarioPresets:  '/api/scenarios/presets',
  scenarioRun:      '/api/scenarios/run',
  fundamentals:     (ticker: string) => `/api/fundamentals/${ticker}`,
  portfolioAllocation: '/api/portfolio/allocation',
  portfolioCorrelation: (days = 30) => `/api/portfolio/correlation?period_days=${days}`,
  narrativeBrief: '/api/narrative/brief',
  liveAlerts:      (limit = 20) => `/api/v1/alerts/live?limit=${limit}`,
  portfolioOrders: (limit = 20) => `/api/v1/portfolio/orders?limit=${limit}`,
} as const
