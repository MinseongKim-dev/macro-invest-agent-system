/**
 * SSE proxy — pipes the Aleph-One intelligence stream to the browser.
 *
 * The browser EventSource can only connect same-origin.  This Route Handler
 * takes precedence over next.config.ts rewrites and pipes the response body
 * from the aleph-api service without buffering.
 *
 * Target: ALEPH_API_URL (default http://aleph-api:8001)
 */
export const dynamic    = 'force-dynamic'
export const runtime    = 'nodejs'
// Vercel Pro/Enterprise: extend the Function execution window so the SSE proxy
// can stay alive longer than the default 10 s (Hobby) / 25 s (Pro) limit.
// On Hobby this is a no-op; on Pro it raises the ceiling to 300 s.
// The browser also connects directly to the VPS when NEXT_PUBLIC_API_URL is set
// (see useAlephStream.ts), so this proxy is only used as a same-origin fallback.
export const maxDuration = 300

export async function GET(request: Request): Promise<Response> {
  const base        = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'
  const { search }  = new URL(request.url)
  const upstreamUrl = `${base}/api/v1/intelligence/stream${search}`

  let upstream: Response
  try {
    upstream = await fetch(upstreamUrl, {
      headers: { Accept: 'text/event-stream' },
      // @ts-expect-error — Node fetch supports this for streaming
      duplex: 'half',
    })
  } catch {
    return new Response('Aleph-One API unavailable', { status: 502 })
  }

  if (!upstream.ok || !upstream.body) {
    return new Response('Aleph-One upstream error', { status: upstream.status })
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
