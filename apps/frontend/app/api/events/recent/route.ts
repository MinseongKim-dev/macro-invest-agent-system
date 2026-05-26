/**
 * Recent events proxy — forwards GET to the Aleph-One events endpoint.
 *
 * Used by useNewsStream hook for 30-second SWR polling.
 * Target: ALEPH_API_URL (default http://aleph-api:8001)
 */
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request): Promise<Response> {
  const base       = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'
  const { search } = new URL(request.url)
  const upstreamUrl = `${base}/api/events/recent${search}`

  let upstream: Response
  try {
    upstream = await fetch(upstreamUrl, {
      headers: { Accept: 'application/json' },
    })
  } catch {
    return new Response(JSON.stringify({ events: [] }), {
      status:  200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  if (!upstream.ok) {
    return new Response(JSON.stringify({ events: [] }), {
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
