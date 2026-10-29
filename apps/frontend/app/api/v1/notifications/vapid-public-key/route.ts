import { NextResponse } from 'next/server'

const ALEPH_API_URL = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'

export async function GET() {
  try {
    const res = await fetch(`${ALEPH_API_URL}/api/v1/notifications/vapid-public-key`, {
      cache: 'no-store',
    })
    if (!res.ok) return NextResponse.json({ error: 'upstream error' }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ error: 'service unavailable' }, { status: 503 })
  }
}
