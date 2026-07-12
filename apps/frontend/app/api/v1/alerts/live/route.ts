import { NextRequest, NextResponse } from 'next/server'

const ALEPH_API_URL = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'

export async function GET(req: NextRequest) {
  const limit = req.nextUrl.searchParams.get('limit') ?? '20'
  try {
    const res = await fetch(`${ALEPH_API_URL}/api/v1/alerts/live?limit=${limit}`, { cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ alerts: [], total: 0 }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ alerts: [], total: 0 }, { status: 503 })
  }
}
