'use client'
import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import type { User } from '@supabase/supabase-js'

export function useAuth() {
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    let supabase
    try { supabase = createClient() } catch { return } // no-op when auth not configured

    supabase.auth.getUser().then(({ data }) => setUser(data.user))

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_, session) => setUser(session?.user ?? null),
    )
    return () => subscription.unsubscribe()
  }, [])

  async function signOut() {
    try {
      const supabase = createClient()
      await supabase.auth.signOut()
    } catch { /* Supabase not configured */ }
    window.location.href = '/login'
  }

  return { user, signOut }
}
