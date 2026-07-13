import { NextRequest, NextResponse } from 'next/server'

const ALEPH_API_URL = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'

export async function GET(req: NextRequest) {
  const limit = req.nextUrl.searchParams.get('limit') ?? '20'
  try {
    const res = await fetch(
      `${ALEPH_API_URL}/api/v1/portfolio/orders?limit=${limit}`,
      { cache: 'no-store' },
    )
    if (!res.ok) return NextResponse.json({ orders: [], total: 0, status: 'error' }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ orders: [], total: 0, status: 'error' }, { status: 503 })
  }
}
