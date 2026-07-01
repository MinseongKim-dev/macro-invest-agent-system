/**
 * News summarize proxy — POST SSE stream from backend Groq analysis.
 * Pipes the SSE response directly; falls back to an error token on failure.
 */
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

function errorStream(msg: string): ReadableStream<Uint8Array> {
  const enc = new TextEncoder()
  return new ReadableStream({
    start(ctrl) {
      ctrl.enqueue(enc.encode(`data: ${JSON.stringify({ type: 'token', text: msg + ' ' })}\n\n`))
      ctrl.enqueue(enc.encode(`data: ${JSON.stringify({ type: 'done' })}\n\n`))
      ctrl.close()
    },
  })
}

export async function POST(request: Request): Promise<Response> {
  const base        = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'
  const upstreamUrl = `${base}/api/news/summarize`

  let body: unknown
  try { body = await request.json() } catch { return new Response('Invalid JSON body', { status: 400 }) }

  try {
    const upstream = await fetch(upstreamUrl, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    })
    return new Response(upstream.body, {
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive' },
    })
  } catch {
    return new Response(errorStream('분석 서버에 연결할 수 없습니다.'), {
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
    })
  }
}
