/**
 * OMNI command proxy — forwards POST requests to the Aleph-One intelligence API.
 * Returns a graceful offline response instead of 502 when the backend is unreachable.
 *
 * Target: ALEPH_API_URL (default http://aleph-api:8001)
 */
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const OFFLINE_RESPONSE = {
  timestamp: '',
  status: 'SYNCING',
  portfolio_health: { score: 0, source: 'OFFLINE' },
  macro_regime: { regime_name: 'STANDBY', market_phase: 'UNKNOWN', confidence_score: 0 },
  active_signals: [],
  intelligence_synthesis: { assets_count: 0, vector_mode: 'OFFLINE', network_nodes: [], risk_matrix: [] },
  omni_report: '▌ ALEPH-ONE NEURAL LINK OFFLINE\n══════════════════════════════════\n\nBackend API is currently unreachable.\n\nTo connect:\n→ Set ALEPH_API_URL in Vercel environment variables\n→ Point it to your VPS: https://api.your-domain.com\n→ Ensure the VPS Docker stack is running',
}

export async function POST(request: Request): Promise<Response> {
  const base        = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'
  const upstreamUrl = `${base}/api/v1/intelligence/command`

  let body: unknown
  try {
    body = await request.json()
  } catch {
    return new Response('Invalid JSON body', { status: 400 })
  }

  let upstream: Response
  try {
    upstream = await fetch(upstreamUrl, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
      signal:  AbortSignal.timeout(30_000),
    })
  } catch {
    const fallback = { ...OFFLINE_RESPONSE, timestamp: new Date().toISOString() }
    return new Response(JSON.stringify(fallback), {
      status:  200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const data = await upstream.text()
  return new Response(data, {
    status:  upstream.status,
    headers: { 'Content-Type': 'application/json' },
  })
}
