'use client'

import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface PanelMeta {
  regime?:     string
  phase?:      string
  confidence?: number
  signal?:     string
  health?:     number
}

interface ResearchPanelProps {
  open:      boolean
  onClose:   () => void
  streaming: boolean
  content:   string
  meta?:     PanelMeta
  query?:    string
}

function SimpleMarkdown({ text }: { text: string }) {
  const lines = text.split('\n')
  return (
    <div style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 12, color: 'rgba(255,255,255,.78)', lineHeight: 1.7 }}>
      {lines.map((line, i) => {
        if (line.startsWith('# '))  return <div key={i} style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 14, color: '#00e5ff', marginTop: 14, marginBottom: 4, fontWeight: 700 }}>{line.slice(2)}</div>
        if (line.startsWith('## ')) return <div key={i} style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 11, color: '#a855f7', marginTop: 10, marginBottom: 3, letterSpacing: '1px' }}>{line.slice(3)}</div>
        if (line.startsWith('### ')) return <div key={i} style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 11, color: '#00ff88', marginTop: 8, marginBottom: 2, fontWeight: 700 }}>{line.slice(4)}</div>
        if (line.startsWith('**') && line.endsWith('**')) return <div key={i} style={{ fontWeight: 700, color: '#fff', marginBottom: 2 }}>{line.slice(2, -2)}</div>
        if (line.startsWith('- ') || line.startsWith('• ')) return (
          <div key={i} style={{ display: 'flex', gap: 6, marginBottom: 2, paddingLeft: 4 }}>
            <span style={{ color: '#00e5ff', flexShrink: 0, marginTop: 1 }}>›</span>
            <span>{line.slice(2)}</span>
          </div>
        )
        if (line.startsWith('→ ') || line.startsWith('▸ ')) return (
          <div key={i} style={{ display: 'flex', gap: 6, marginBottom: 2, paddingLeft: 4 }}>
            <span style={{ color: '#00ff88', flexShrink: 0 }}>→</span>
            <span>{line.slice(2)}</span>
          </div>
        )
        if (line.startsWith('══') || line.startsWith('──')) return <div key={i} style={{ height: 1, background: 'rgba(0,229,255,.12)', margin: '8px 0' }} />
        if (line.trim() === '') return <div key={i} style={{ height: 6 }} />
        // Inline bold: **text**
        const parts = line.split(/(\*\*[^*]+\*\*)/)
        return (
          <div key={i} style={{ marginBottom: 1 }}>
            {parts.map((part, j) =>
              part.startsWith('**') && part.endsWith('**')
                ? <strong key={j} style={{ color: '#fff', fontWeight: 700 }}>{part.slice(2, -2)}</strong>
                : <span key={j}>{part}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

function MetaChip({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{
      display:    'flex', flexDirection: 'column', gap: 1,
      padding:    '5px 10px', borderRadius: 6,
      background: `${color}12`, border: `1px solid ${color}30`,
      minWidth:   72,
    }}>
      <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 7.5, letterSpacing: '1.5px', color: `${color}88`, textTransform: 'uppercase' }}>{label}</span>
      <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 10, fontWeight: 700, color }}>{value}</span>
    </div>
  )
}

export function ResearchPanel({ open, onClose, streaming, content, meta, query }: ResearchPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom while streaming
  useEffect(() => {
    if (streaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [content, streaming])

  const regime     = meta?.regime ?? '—'
  const health     = meta?.health != null ? `${Math.round(meta.health)}` : '—'
  const confidence = meta?.confidence != null ? `${Math.round(meta.confidence * 100)}%` : '—'

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            style={{
              position: 'fixed', inset: 0, zIndex: 90,
              background: 'rgba(2,6,18,.55)',
              backdropFilter: 'blur(2px)',
            }}
          />

          {/* Panel */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 320, damping: 34 }}
            style={{
              position:       'fixed', top: 0, right: 0, bottom: 0,
              width:          440, zIndex: 100,
              background:     'rgba(2, 9, 22, 0.98)',
              backdropFilter: 'blur(28px)',
              borderLeft:     '1px solid rgba(168,85,247,.28)',
              display:        'flex', flexDirection: 'column',
            }}
          >
            {/* Header */}
            <div style={{
              padding:      '14px 16px 12px',
              borderBottom: '1px solid rgba(168,85,247,.18)',
              display:      'flex', alignItems: 'center', gap: 10, flexShrink: 0,
            }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#a855f7', boxShadow: '0 0 8px #a855f7', animation: streaming ? 'glow-pulse .7s ease-in-out infinite' : 'none' }} />
              <span style={{ fontFamily: "'Orbitron',sans-serif", fontSize: 9, letterSpacing: '3px', color: '#a855f7', flex: 1 }}>
                ◈ INTELLIGENCE REPORT
              </span>
              {streaming && (
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 8, color: 'rgba(168,85,247,.55)', animation: 'blink .8s step-end infinite' }}>
                  ▌ STREAMING
                </span>
              )}
              <button
                onClick={onClose}
                style={{
                  background: 'none', border: '1px solid rgba(255,255,255,.12)', borderRadius: 5,
                  color: 'rgba(255,255,255,.38)', fontSize: 11, cursor: 'pointer',
                  width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  lineHeight: 1, flexShrink: 0,
                }}
              >✕</button>
            </div>

            {/* Query echo */}
            {query && (
              <div style={{ padding: '8px 16px', borderBottom: '1px solid rgba(0,229,255,.07)', flexShrink: 0 }}>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'rgba(0,229,255,.38)' }}>› </span>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'rgba(0,229,255,.6)' }}>{query}</span>
              </div>
            )}

            {/* Metadata chips */}
            {meta && (
              <div style={{
                padding:      '8px 16px 6px', flexShrink: 0,
                borderBottom: '1px solid rgba(168,85,247,.1)',
                display:      'flex', gap: 6, flexWrap: 'wrap',
              }}>
                <MetaChip label="REGIME"     value={regime}     color="#00e5ff" />
                <MetaChip label="HEALTH"     value={health}     color="#00ff88" />
                <MetaChip label="CONFIDENCE" value={confidence} color="#a855f7" />
                {meta.signal && <MetaChip label="SIGNAL" value={meta.signal} color="#fbbf24" />}
              </div>
            )}

            {/* Content */}
            <div
              ref={scrollRef}
              style={{ flex: 1, overflowY: 'auto', padding: '14px 16px', scrollbarWidth: 'thin' }}
            >
              {content ? (
                <>
                  <SimpleMarkdown text={content} />
                  {streaming && (
                    <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 13, color: '#a855f7', animation: 'blink .8s step-end infinite' }}>▌</span>
                  )}
                </>
              ) : (
                <div style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  height: '60%', gap: 10, opacity: 0.4,
                }}>
                  <div style={{ width: 32, height: 32, borderRadius: '50%', border: '2px solid #a855f7', borderTopColor: 'transparent', animation: 'orbit-spin .9s linear infinite' }} />
                  <span style={{ fontFamily: "'Rajdhani',sans-serif", fontSize: 10, color: 'rgba(255,255,255,.5)', letterSpacing: '2px' }}>ANALYZING</span>
                </div>
              )}
            </div>

            {/* Footer */}
            <div style={{
              padding:    '8px 16px', flexShrink: 0,
              borderTop:  '1px solid rgba(168,85,247,.1)',
              display:    'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 7.5, color: 'rgba(255,255,255,.18)' }}>
                ALEPH-ONE AI ANALYSIS · ADVISORY ONLY
              </span>
              <button
                onClick={onClose}
                style={{
                  padding:    '4px 12px', borderRadius: 5, cursor: 'pointer',
                  background: 'rgba(168,85,247,.12)', border: '1px solid rgba(168,85,247,.3)',
                  fontFamily: "'Orbitron',sans-serif", fontSize: 7.5, letterSpacing: '1px', color: '#a855f7',
                }}
              >CLOSE</button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
