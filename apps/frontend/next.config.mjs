/** @type {import('next').NextConfig} */
const config = {
  output: 'standalone',
  async rewrites() {
    const apiBase = process.env.API_BASE_URL ?? 'http://api:8000'
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
      {
        source: '/health',
        destination: `${apiBase}/health`,
      },
    ]
  },
}

export default config
