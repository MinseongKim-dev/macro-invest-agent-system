/**
 * Sector summary proxy — forwards GET to backend.
 * Returns live sector % changes derived from in-memory price state.
 */
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(): Promise<Response> {
  const base        = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'
  const upstreamUrl = `${base}/api/tickers/sector/summary`

  try {
    const upstream = await fetch(upstreamUrl, { headers: { Accept: 'application/json' } })
    const data     = await upstream.text()
    return new Response(data, { status: upstream.status, headers: { 'Content-Type': 'application/json' } })
  } catch {
    return new Response(JSON.stringify({ sectors: [] }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }
}
