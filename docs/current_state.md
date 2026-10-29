# Current State — v0.4.19 (claude/aleph-one-ui-design-flkCj)

Latest commit: `071edd6` · All CI checks passing

---

## Architecture

Two independent backends:

| Backend | Entry point | Port | Role |
|---------|------------|------|------|
| Tri-File Core | `src/main.py` | 8001 | SSE stream, LangChain OMNI, yfinance collection |
| Domain API | `apps/api/main.py` | 8000 | Analyst read API (regimes, signals, quant, alerts, events) |

`src/` Tri-File Core is excluded from pytest coverage (`pyproject.toml`).

---

## Backend — `src/` (Tri-File Core)

| Component | Status | Notes |
|-----------|--------|-------|
| TimescaleDB hypertables | ✅ | market_ticks, index_ticks, macro_indicators, virtual_accounts, virtual_orders, portfolio_holdings, fund_nav_ticks (stub) |
| Live market data | ✅ | yfinance — 16 KR/US tickers, 10s during session / 60s off-hours (KST hybrid scheduler) |
| Global index data | ✅ | KOSPI, S&P 500, USD/KRW — SSE `market_indices` field |
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
| Fund NAV | 🚧 | Stub — `fund_nav_ticks` DDL exists, KOFIA adapter is `NotImplementedError` |

## Backend — `apps/api/` (Domain API)

| Component | Status | Notes |
|-----------|--------|-------|
| Regime REST | ✅ | `GET /api/regimes/latest`, `/compare`, `/history` |
| Signals REST | ✅ | `GET /api/signals/latest` — with TrustMetadata |
| Quant score | ✅ | `GET /api/quant/latest` |
| Alerts REST | ✅ | `GET /api/alerts/recent`, PATCH acknowledge/snooze |
| External events | ✅ | `GET /api/events/recent`, `GET /api/events/{id}` |
| Snapshot REST | ✅ | `GET /api/snapshots/latest`, `POST /api/snapshots/compare` |
| Explanations | ✅ | `GET /api/explanations/regime/latest` |
| Startup seeder | ✅ | Reads real data from TimescaleDB; no synthetic fallback (D-01a) |
| Hourly refresh | ✅ | `_hourly_refresh_loop` — G-02 fix |

### D-01a (confirmed)

`apps/api/startup_seeder.py` no longer contains `_SYNTHETIC_VALUES`.
If TimescaleDB is unreachable at boot: all indicator states = `UNKNOWN`,
`regime_label` = `UNCLEAR`, `source` = `no_data_available`. No invented data.

---

## Frontend — `apps/frontend/`

### Default route

`apps/frontend/app/page.tsx` → `AlephHome` (dynamic import, SSR disabled).
`AlephDashboard.tsx` still exists but is not the default route.

### AlephHome screen (관찰/실험/계좌/회고 tabs)

| Component | Status | Notes |
|-----------|--------|-------|
| `AlephHome.tsx` | ✅ | Root orchestrator; 4-tab layout |
| `home/AlephNav.tsx` | ✅ | Sticky header, tab switcher, stream status, auth chip |
| `home/MarketContextStrip.tsx` | ✅ | Regime chip, confidence, transition text |
| `home/RelevantChangeFeed.tsx` | ✅ | Alert + news feed, filter buttons, keyboard accessible |
| `home/EvidencePanel.tsx` | ✅ | Right sidebar; quant dimension bars, regime detail, item detail |
| `home/ComparisonFooter.tsx` | ✅ | KRW/USD account summary, P&L chip |
| `components/ui/DataStatus.tsx` | ✅ | 12-state availability×freshness badge |
| `관찰` tab | ✅ | Full layout with live data |
| `실험` tab | 🚧 | Stub — "준비 중입니다." placeholder |
| `계좌` tab | 🚧 | Stub — "준비 중입니다." placeholder |
| `회고` tab | 🚧 | Stub — "준비 중입니다." placeholder |
| HypothesisSummary | ❌ | Not built |
| DecisionTimeline | ❌ | Not built |
| EvidenceReference | ❌ | Not built |

### AlephDashboard screen (legacy, still reachable)

| Component | Status | Notes |
|-----------|--------|-------|
| Live SSE market stream | ✅ | `useAlephStream` / `useMarketStream` |
| Live news stream | ✅ | `useNewsStream` (SWR 30s) |
| Regime / Signals / Events REST | ✅ | `useAlephData.ts` custom hooks |
| Sector heatmap | ✅ | SWR `useSectorSummary` |
| Portfolio chart (1D/1W/1M/3M) | ✅ | `usePortfolio` hook |
| Holdings 16 rows | ✅ | All KR + US tickers rendered |
| Ticker detail panel | ✅ | Click-to-expand with 52-week range |
| News detail panel | ✅ | AI analysis auto-stream on open |
| OMNI-COMMAND panel | ✅ | `useOmniStream` hook, Framer Motion slide-out |
| APPLY button | 🚧 | Disabled — Virtual Broker execution UI pending |
| FUNDS tab | 🚧 | Awaiting KOFIA NAV feed |
| ALTERNATIVE DATA | 🚧 | Awaiting commodity pipeline |

---

## Known limitations (verified, not inferred)

- Dev server not running in this session — no browser screenshot confirmation for AlephHome
- Mobile real-device testing not done
- `AlephHome.tsx` has no `APP_VERSION` constant (release checklist not fully applied)
- R0 defect fixes (G-01 through G-04b) verified by CI only; production runtime behavior not confirmed
- `실험` / `계좌` / `회고` tabs are stubs with placeholder text

---

## Pending next work

- KOFIA OpenAPI adapter (blocked on API key)
- Virtual Broker execution UI (APPLY button)
- AlephHome `실험` / `계좌` / `회고` tab implementations
- Phase B: authentication (Supabase Auth or Clerk)
- Phase E: landing page and onboarding
