/**
 * OMNI streaming proxy — forwards POST requests to the Aleph-One SSE stream endpoint.
 * Pipes the SSE response body directly to the client. Falls back to an offline
 * token stream when the backend is unreachable.
 */
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const OFFLINE_REPORT =
  '▌ ALEPH-ONE NEURAL LINK OFFLINE\n\n' +
  'Backend API is currently unreachable.\n\n' +
  '**To connect:**\n' +
  '- Set `ALEPH_API_URL` in Vercel environment variables\n' +
  '- Point it to your VPS: `https://api.your-domain.com`\n' +
  '- Ensure the VPS Docker stack is running'

function offlineStream(): ReadableStream<Uint8Array> {
  const enc = new TextEncoder()
  const meta = {
    type:             'meta',
    macro_regime:     { regime_name: 'OFFLINE', market_phase: 'UNKNOWN', confidence_score: 0 },
    portfolio_health: { score: 0, source: 'OFFLINE' },
    active_signals:   [],
  }
  const words = OFFLINE_REPORT.split(' ')
  let idx = 0

  return new ReadableStream({
    start(ctrl) {
      ctrl.enqueue(enc.encode(`data: ${JSON.stringify(meta)}\n\n`))
      const timer = setInterval(() => {
        if (idx < words.length) {
          const content = words[idx] + (idx < words.length - 1 ? ' ' : '')
          ctrl.enqueue(enc.encode(`data: ${JSON.stringify({ type: 'token', content })}\n\n`))
          idx++
        } else {
          ctrl.enqueue(enc.encode(`data: ${JSON.stringify({ type: 'done' })}\n\n`))
          clearInterval(timer)
          ctrl.close()
        }
      }, 50)
    },
  })
}

export async function POST(request: Request): Promise<Response> {
  const base        = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'
  const upstreamUrl = `${base}/api/v1/intelligence/command/stream`

  let body: unknown
  try {
    body = await request.json()
  } catch {
    return new Response('Invalid JSON body', { status: 400 })
  }

  try {
    const upstream = await fetch(upstreamUrl, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    })
    return new Response(upstream.body, {
      headers: {
        'Content-Type':  'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection':    'keep-alive',
      },
    })
  } catch {
    return new Response(offlineStream(), {
      headers: {
        'Content-Type':  'text/event-stream',
        'Cache-Control': 'no-cache',
      },
    })
  }
}
