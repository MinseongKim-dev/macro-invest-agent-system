/**
 * OMNI command proxy — forwards POST requests to the Aleph-One intelligence API.
 *
 * Target: ALEPH_API_URL (default http://aleph-api:8001)
 */
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

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
    })
  } catch {
    return new Response('Aleph-One API unavailable', { status: 502 })
  }

  const data = await upstream.text()
  return new Response(data, {
    status:  upstream.status,
    headers: { 'Content-Type': 'application/json' },
  })
}
