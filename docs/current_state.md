# Current State — v0.4.4 (quality-improvements-master branch)

## What is live

### Backend (`src/` + `apps/api/`)

| Component | Status | Notes |
|-----------|--------|-------|
| TimescaleDB hypertables | ✅ | market_ticks, index_ticks, macro_indicators, virtual_accounts, virtual_orders, portfolio_holdings, fund_nav_ticks (stub) |
| Live market data | ✅ | yfinance — 16 KR/US tickers, 10s during session / 60s off-hours |
| Global index data | ✅ | KOSPI, S&P 500, USD/KRW — SSE field `market_indices` |
| Macro indicators | ✅ | VIX, T10Y, T3M (yfinance); FEDFUNDS/CPI/GDP/UNRATE (FRED optional) |
| SSE stream | ✅ | `GET /api/v1/intelligence/stream` — full AlephStreamData payload |
| OMNI-COMMAND stream | ✅ | `POST /api/v1/intelligence/command/stream` — LangChain token SSE |
| News headline AI | ✅ | `POST /api/news/summarize` — Groq streaming analysis |
| Virtual broker | ✅ | `GET /api/v1/portfolio/summary`, LLM tool calling for paper trades |
| Sector summary | ✅ | `GET /api/tickers/sector/summary` |
| Portfolio metrics | ✅ | `GET /api/tickers/portfolio/metrics` — Sharpe/beta/alpha |
| Portfolio history | ✅ | `GET /api/tickers/portfolio/history?period=1D\|1W\|1M\|3M` |
| Ticker detail | ✅ | `GET /api/tickers/{ticker}/detail` — 52-week range |
| Events REST | ✅ | `GET /api/events/recent` — real publisher/url/timestamp |
| Regime REST | ✅ | `GET /api/regimes/latest`, `GET /api/regimes/compare` |
| Signals REST | ✅ | `GET /api/signals/latest` — with TrustMetadata |
| Quant score | ✅ | `GET /api/quant/latest` |
| Fund NAV | 🚧 | Stub — `fund_nav_ticks` DDL exists, KOFIA adapter is `NotImplementedError` |

### Frontend (`apps/frontend/`)

| Component | Status | Notes |
|-----------|--------|-------|
| Live SSE market stream | ✅ | `useAlephStream` / `useMarketStream` |
| Live news stream | ✅ | `useNewsStream` (SWR 30s) |
| Regime / Signals / Events REST | ✅ | `useAlephData.ts` custom hooks |
| Sector heatmap | ✅ | SWR `useSectorSummary` → live from backend |
| Portfolio chart (1D/1W/1M/3M) | ✅ | `usePortfolio` hook |
| Holdings 16 rows | ✅ | All KR + US tickers rendered |
| Ticker detail panel | ✅ | Click-to-expand with 52-week range |
| News detail panel | ✅ | AI analysis auto-stream on open |
| OMNI-COMMAND panel | ✅ | `useOmniStream` hook, Framer Motion slide-out |
| ANALYZE button | ✅ | Wired to portfolio analysis prompt |
| APPLY button | 🚧 | Disabled — Virtual Broker execution UI pending |
| Trust metadata badges | ✅ | Degraded (orange) / stale (red) indicators |
| Last-update display | ✅ | "마지막 수집: X시간 전" in status bar |
| Freshness dots | ✅ | Per-indicator dots on FED/T10Y rate rows |
| FUNDS tab | 🚧 | Awaiting KOFIA NAV feed |
| ALTERNATIVE DATA | 🚧 | Awaiting commodity pipeline |
| Performance bars | ✅ | Derived from SSE signal distribution (SELL/HOLD/BUY) |

## Active branch

`claude/quality-improvements-master` (pre-PR) — 6-step quality improvement pass:
1. ✅ API layer unification — all fetch via custom hooks
2. ✅ TypeScript types — `MacroSnapshot`, `MacroFeature`, `PortfolioData` added
3. ✅ Error handling E2E — specific Korean error messages, trust badges
4. ✅ Data freshness UI — "마지막 수집" bar, per-indicator dots
5. ✅ Legacy cleanup — `legacy/` → `_archive/`
6. 🔄 Documentation update (this file)

## Known gaps / next priorities

- KOFIA OpenAPI adapter (blocked on API key)
- Virtual Broker execution UI (APPLY button)
- Phase B: authentication (Supabase Auth or Clerk)
- Phase E: landing page and onboarding
