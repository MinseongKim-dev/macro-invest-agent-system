import { NextRequest, NextResponse } from 'next/server'

const ALEPH_API_URL = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'

export async function GET(req: NextRequest) {
  const qs = req.nextUrl.searchParams.toString()
  try {
    const res = await fetch(
      `${ALEPH_API_URL}/api/quant/latest${qs ? `?${qs}` : ''}`,
      { cache: 'no-store' },
    )
    if (!res.ok) return NextResponse.json({ status: 'error' }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ status: 'error' }, { status: 503 })
  }
}
