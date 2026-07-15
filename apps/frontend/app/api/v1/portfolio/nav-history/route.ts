import { NextRequest, NextResponse } from 'next/server'

const ALEPH_API_URL = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'

export async function GET(req: NextRequest) {
  const days = req.nextUrl.searchParams.get('days') ?? '30'
  try {
    const res = await fetch(
      `${ALEPH_API_URL}/api/v1/portfolio/nav-history?days=${days}`,
      { cache: 'no-store' },
    )
    if (!res.ok) return NextResponse.json({ snapshots: [], status: 'error' }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ snapshots: [], status: 'error' }, { status: 503 })
  }
}
