import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
    './hooks/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        'a-bg':     '#000000',
        'a-deep':   '#08081A',
        'a-mid':    '#1A1A2E',
        'a-cyan':   '#00E5FF',
        'a-purple': '#BF00FF',
        'a-text':   '#E8F0FE',
      },
      fontFamily: {
        mono: ['"Space Mono"', '"Courier New"', 'monospace'],
      },
      animation: {
        'ticker-scroll': 'ticker 60s linear infinite',
        'glow-pulse':    'glow-pulse 2.5s ease-in-out infinite',
        'blink':         'blink 1.2s step-start infinite',
        'fade-in':       'fade-in 0.4s ease-out',
      },
      keyframes: {
        ticker: {
          '0%':   { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
        'glow-pulse': {
          '0%, 100%': { boxShadow: '0 0 8px rgba(0,229,255,0.2)' },
          '50%':      { boxShadow: '0 0 28px rgba(0,229,255,0.7)' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0' },
        },
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}

export default config
