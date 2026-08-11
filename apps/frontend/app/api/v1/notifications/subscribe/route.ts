import { NextRequest, NextResponse } from 'next/server'

const ALEPH_API_URL = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const res = await fetch(`${ALEPH_API_URL}/api/v1/notifications/subscribe`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
      cache:   'no-store',
    })
    if (!res.ok) return NextResponse.json({ error: 'upstream error' }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ error: 'service unavailable' }, { status: 503 })
  }
}
