export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(request: Request): Promise<Response> {
  const base = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'
  let body: string
  try {
    body = await request.text()
  } catch {
    body = '{}'
  }
  try {
    const upstream = await fetch(`${base}/api/scenarios/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body,
    })
    const data = await upstream.text()
    return new Response(data, {
      status: upstream.status,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch {
    return new Response(JSON.stringify({ detail: 'Scenario engine unavailable' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}
