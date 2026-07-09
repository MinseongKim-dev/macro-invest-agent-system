'use client'

import { useCallback, useEffect, useState } from 'react'

type PermissionState = 'default' | 'granted' | 'denied'

interface UsePushNotificationsReturn {
  permission: PermissionState
  isSubscribed: boolean
  subscribe: () => Promise<void>
  unsubscribe: () => Promise<void>
  isSupported: boolean
}

function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64   = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw      = atob(base64)
  const buf      = new ArrayBuffer(raw.length)
  const view     = new Uint8Array(buf)
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i)
  return view
}

export function usePushNotifications(): UsePushNotificationsReturn {
  const [permission, setPermission] = useState<PermissionState>('default')
  const [isSubscribed, setIsSubscribed] = useState(false)
  const [registration, setRegistration] = useState<ServiceWorkerRegistration | null>(null)

  const isSupported =
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window

  useEffect(() => {
    if (!isSupported) return
    setPermission(Notification.permission as PermissionState)
    navigator.serviceWorker.ready.then((reg) => {
      setRegistration(reg)
      reg.pushManager.getSubscription().then((sub) => setIsSubscribed(!!sub))
    })
  }, [isSupported])

  const subscribe = useCallback(async () => {
    if (!registration) return
    const perm = await Notification.requestPermission()
    setPermission(perm as PermissionState)
    if (perm !== 'granted') return

    const keyResp = await fetch('/api/v1/notifications/vapid-public-key')
    const { public_key } = (await keyResp.json()) as { public_key: string }

    const sub = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(public_key),
    })

    await fetch('/api/v1/notifications/subscribe', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(sub.toJSON()),
    })
    setIsSubscribed(true)
  }, [registration])

  const unsubscribe = useCallback(async () => {
    if (!registration) return
    const sub = await registration.pushManager.getSubscription()
    if (!sub) return
    const endpoint = encodeURIComponent(sub.endpoint)
    await fetch(`/api/v1/notifications/unsubscribe?endpoint=${endpoint}`, { method: 'DELETE' })
    await sub.unsubscribe()
    setIsSubscribed(false)
  }, [registration])

  return { permission, isSubscribed, subscribe, unsubscribe, isSupported }
}
