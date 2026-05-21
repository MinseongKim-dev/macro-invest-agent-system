import type { Metadata } from 'next'
import dynamic from 'next/dynamic'
import './globals.css'

// StatusBar uses clock (browser-only) — must be client-only
const StatusBar = dynamic(() => import('@/components/layout/StatusBar'), { ssr: false })

export const metadata: Metadata = {
  title: 'Aleph-One | Macro Intelligence',
  description: 'Hyper-futuristic macro investment intelligence command center',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <StatusBar />
        {children}
      </body>
    </html>
  )
}
