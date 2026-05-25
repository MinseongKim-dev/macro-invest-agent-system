import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Aleph-One | Macro Intelligence',
  description: 'Hyper-futuristic macro investment intelligence command center',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, padding: 0, overflow: 'hidden' }}>
        {children}
      </body>
    </html>
  )
}
