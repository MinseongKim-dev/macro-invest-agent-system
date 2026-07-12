import { NextResponse } from 'next/server'

const ALEPH_API_URL = process.env.ALEPH_API_URL ?? 'http://aleph-api:8001'

export async function GET() {
  try {
    const res = await fetch(`${ALEPH_API_URL}/api/narrative/brief`, { cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ detail: 'upstream error' }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ detail: '서버 연결 실패' }, { status: 503 })
  }
}
