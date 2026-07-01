/**
 * Portfolio history proxy — forwards GET to backend with query params.
 * Uses ALEPH_API_URL (default http://aleph-api:8001).
 */
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request): Promise<Response> {
  const base        = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'
  const { search }  = new URL(request.url)
  const upstreamUrl = `${base}/api/tickers/portfolio/history${search}`

  try {
    const upstream = await fetch(upstreamUrl, { headers: { Accept: 'application/json' } })
    const data     = await upstream.text()
    return new Response(data, { status: upstream.status, headers: { 'Content-Type': 'application/json' } })
  } catch {
    return new Response(JSON.stringify({ points: [], empty: true }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }
}
