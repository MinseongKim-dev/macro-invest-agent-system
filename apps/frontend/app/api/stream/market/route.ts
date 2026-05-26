/**
 * SSE proxy Route Handler.
 *
 * The browser's EventSource API can only connect to same-origin endpoints.
 * This Route Handler pipes the FastAPI SSE stream (/api/mock/stream/market)
 * to the client without buffering, preserving the text/event-stream format.
 *
 * Next.js Route Handlers take precedence over rewrites, so this file handles
 * GET /api/stream/market while all other /api/* calls fall through to the
 * rewrite → FastAPI.
 */
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(): Promise<Response> {
  const base = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'
  const upstreamUrl = `${base}/api/mock/stream/market`

  let upstream: Response
  try {
    upstream = await fetch(upstreamUrl, {
      headers: { Accept: 'text/event-stream' },
    })
  } catch {
    return new Response('SSE upstream unavailable', { status: 502 })
  }

  if (!upstream.ok || !upstream.body) {
    return new Response('SSE upstream error', { status: 502 })
  }

  return new Response(upstream.body, {
    headers: {
      'Content-Type':      'text/event-stream',
      'Cache-Control':     'no-cache, no-transform',
      'X-Accel-Buffering': 'no',
      'Connection':        'keep-alive',
    },
  })
}
