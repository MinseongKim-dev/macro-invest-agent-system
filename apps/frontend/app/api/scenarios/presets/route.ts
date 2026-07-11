export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(): Promise<Response> {
  const base = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'
  try {
    const upstream = await fetch(`${base}/api/scenarios/presets`, {
      headers: { Accept: 'application/json' },
    })
    const data = await upstream.text()
    return new Response(data, {
      status: upstream.status,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch {
    return new Response(JSON.stringify({ presets: [] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}
