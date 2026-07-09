'use client'
import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'

type Mode = 'signin' | 'signup' | 'magic'

export default function LoginPage() {
  const [mode, setMode]       = useState<Mode>('signin')
  const [email, setEmail]     = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg]         = useState<{ text: string; ok: boolean } | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setMsg(null)

    // createClient() is deferred to the event handler so it only runs in the
    // browser (never at build-time during Next.js static analysis).
    const supabase = createClient()

    try {
      if (mode === 'magic') {
        const { error } = await supabase.auth.signInWithOtp({
          email,
          options: { emailRedirectTo: `${location.origin}/auth/callback` },
        })
        if (error) throw error
        setMsg({ text: '매직 링크를 이메일로 전송했습니다. 확인해주세요.', ok: true })
      } else if (mode === 'signup') {
        const { error } = await supabase.auth.signUp({
          email,
          password,
          options: { emailRedirectTo: `${location.origin}/auth/callback` },
        })
        if (error) throw error
        setMsg({ text: '확인 이메일을 발송했습니다. 이메일을 확인해주세요.', ok: true })
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
        window.location.href = '/'
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '인증 오류가 발생했습니다'
      setMsg({ text: message, ok: false })
    } finally {
      setLoading(false)
    }
  }

  const labels: Record<Mode, string> = {
    signin: '로그인',
    signup: '회원가입',
    magic:  '매직 링크',
  }

  return (
    <div style={styles.root}>
      <div style={styles.grid} />

      <div style={styles.panel}>
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.logo}>ALEPH-ONE</div>
          <div style={styles.sub}>MACRO INTELLIGENCE COMMAND CENTER</div>
          <div style={styles.divider} />
        </div>

        {/* Mode tabs */}
        <div style={styles.tabs}>
          {(['signin', 'signup', 'magic'] as Mode[]).map(m => (
            <button
              key={m}
              onClick={() => { setMode(m); setMsg(null) }}
              style={{ ...styles.tab, ...(mode === m ? styles.tabActive : {}) }}
            >
              {labels[m]}
            </button>
          ))}
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.field}>
            <label style={styles.label}>EMAIL</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              placeholder="user@domain.com"
              style={styles.input}
            />
          </div>

          {mode !== 'magic' && (
            <div style={styles.field}>
              <label style={styles.label}>PASSWORD</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                minLength={6}
                placeholder="••••••••"
                style={styles.input}
              />
            </div>
          )}

          {msg && (
            <div style={{ ...styles.msg, borderColor: msg.ok ? '#00e5ff' : '#ff4d6d' }}>
              {msg.text}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{ ...styles.submit, opacity: loading ? 0.6 : 1 }}
          >
            {loading ? 'PROCESSING...' : labels[mode].toUpperCase()}
          </button>
        </form>

        <div style={styles.footer}>
          INVESTMENT SUPPORT TOOL — NOT FINANCIAL ADVICE
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    minHeight: '100vh',
    background: '#050a0f',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    position: 'relative',
    overflow: 'hidden',
  },
  grid: {
    position: 'absolute',
    inset: 0,
    backgroundImage:
      'linear-gradient(rgba(0,229,255,0.04) 1px, transparent 1px), ' +
      'linear-gradient(90deg, rgba(0,229,255,0.04) 1px, transparent 1px)',
    backgroundSize: '40px 40px',
    pointerEvents: 'none',
  },
  panel: {
    width: '100%',
    maxWidth: 440,
    background: 'rgba(10,20,30,0.92)',
    border: '1px solid rgba(0,229,255,0.25)',
    borderRadius: 4,
    padding: '40px 36px 32px',
    boxShadow: '0 0 60px rgba(0,229,255,0.08)',
    position: 'relative',
    zIndex: 1,
  },
  header: {
    textAlign: 'center',
    marginBottom: 28,
  },
  logo: {
    fontSize: 24,
    fontWeight: 700,
    color: '#00e5ff',
    letterSpacing: '0.3em',
    textShadow: '0 0 20px rgba(0,229,255,0.6)',
  },
  sub: {
    fontSize: 9,
    color: 'rgba(0,229,255,0.5)',
    letterSpacing: '0.15em',
    marginTop: 6,
  },
  divider: {
    height: 1,
    background: 'linear-gradient(90deg, transparent, rgba(0,229,255,0.4), transparent)',
    marginTop: 20,
  },
  tabs: {
    display: 'flex',
    gap: 4,
    marginBottom: 24,
  },
  tab: {
    flex: 1,
    padding: '8px 0',
    background: 'transparent',
    border: '1px solid rgba(0,229,255,0.2)',
    color: 'rgba(0,229,255,0.5)',
    fontSize: 11,
    letterSpacing: '0.1em',
    cursor: 'pointer',
    borderRadius: 2,
    transition: 'all 0.15s',
  },
  tabActive: {
    background: 'rgba(0,229,255,0.1)',
    borderColor: 'rgba(0,229,255,0.6)',
    color: '#00e5ff',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },
  field: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  label: {
    fontSize: 10,
    color: 'rgba(0,229,255,0.6)',
    letterSpacing: '0.12em',
  },
  input: {
    background: 'rgba(0,229,255,0.04)',
    border: '1px solid rgba(0,229,255,0.2)',
    borderRadius: 2,
    padding: '10px 12px',
    color: '#e0f7fa',
    fontSize: 13,
    outline: 'none',
    fontFamily: 'inherit',
    transition: 'border-color 0.15s',
  },
  msg: {
    fontSize: 12,
    padding: '10px 12px',
    border: '1px solid',
    borderRadius: 2,
    color: '#cfd8dc',
    background: 'rgba(0,0,0,0.3)',
    lineHeight: 1.5,
  },
  submit: {
    marginTop: 4,
    padding: '12px',
    background: 'rgba(0,229,255,0.12)',
    border: '1px solid rgba(0,229,255,0.5)',
    borderRadius: 2,
    color: '#00e5ff',
    fontSize: 12,
    letterSpacing: '0.15em',
    fontWeight: 700,
    cursor: 'pointer',
    fontFamily: 'inherit',
    transition: 'all 0.15s',
  },
  footer: {
    marginTop: 24,
    textAlign: 'center',
    fontSize: 9,
    color: 'rgba(100,130,150,0.5)',
    letterSpacing: '0.08em',
  },
}
