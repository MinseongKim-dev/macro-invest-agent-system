// Aleph-One Service Worker — v1
// Caches app shell; network-first for API/SSE; cache-first for static assets.

const CACHE_NAME = 'aleph-one-v1'

const APP_SHELL = [
  '/',
  '/manifest.json',
  '/icon-192x192.png',
  '/icon-512x512.png',
]

// ── Install: pre-cache app shell ──────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  )
  self.skipWaiting()
})

// ── Activate: clean old caches ────────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  )
  self.clients.claim()
})

// ── Fetch strategy ────────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // Skip non-GET, cross-origin, and streaming endpoints (SSE / EventSource)
  if (request.method !== 'GET') return
  if (url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/')) return  // always network for API

  // Cache-first for static assets; network-first with cache fallback otherwise
  const isStatic =
    url.pathname.startsWith('/_next/static/') ||
    url.pathname.match(/\.(png|jpg|svg|ico|woff2?)$/)

  if (isStatic) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ??
          fetch(request).then((res) => {
            if (res.ok) {
              const clone = res.clone()
              caches.open(CACHE_NAME).then((c) => c.put(request, clone))
            }
            return res
          })
      )
    )
  } else {
    event.respondWith(
      fetch(request)
        .then((res) => {
          if (res.ok) {
            const clone = res.clone()
            caches.open(CACHE_NAME).then((c) => c.put(request, clone))
          }
          return res
        })
        .catch(() => caches.match(request))
    )
  }
})
