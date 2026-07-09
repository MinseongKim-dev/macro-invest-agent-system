// Aleph-One Service Worker — v2
// Caches app shell; network-first for API/SSE; cache-first for static assets.
// Handles push notifications for regime-transition alerts.

const CACHE_NAME = 'aleph-one-v2'

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

// ── Push notifications ────────────────────────────────────────────────────────
self.addEventListener('push', (event) => {
  let title = 'Aleph-One Alert'
  let body  = 'Regime conditions have changed.'
  try {
    const data = event.data?.json()
    if (data?.title) title = data.title
    if (data?.body)  body  = data.body
  } catch (_) { /* raw text or empty — use defaults */ }

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon:  '/icon-192x192.png',
      badge: '/icon-192x192.png',
      tag:   'regime-alert',
      renotify: true,
      data: { url: '/' },
    })
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url ?? '/'
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      const existing = wins.find((w) => w.url === url && 'focus' in w)
      if (existing) return existing.focus()
      return clients.openWindow(url)
    })
  )
})
