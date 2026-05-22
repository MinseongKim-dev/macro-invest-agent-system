import type { Metadata } from 'next'
import StatusBarLazy from '@/components/layout/StatusBarLazy'
import './globals.css'

export const metadata: Metadata = {
  title: 'Aleph-One | Macro Intelligence',
  description: 'Hyper-futuristic macro investment intelligence command center',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <StatusBarLazy />
        {children}
      </body>
    </html>
  )
}
