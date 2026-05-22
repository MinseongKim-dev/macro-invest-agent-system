'use client'
import dynamic from 'next/dynamic'

// Wrapper so `ssr: false` lives in a Client Component (required by Next.js 16+)
const StatusBar = dynamic(() => import('./StatusBar'), { ssr: false })

export default function StatusBarLazy() {
  return <StatusBar />
}
