# Aleph-One

**v0.4.10** · Open-source, zero-cost financial intelligence terminal

Aleph-One is a J.A.R.V.I.S.-style hybrid financial intelligence system. It ingests live market data from Yahoo Finance, runs three quantitative engine layers inspired by legendary investors, streams structured signals to a Next.js UI over SSE, and interprets queries through a free-tier LangChain agent — all without a single paid API call.

---

## What's New in v0.4.10

- **SSE disconnection fix** — `useAlephStream` now uses `NEXT_PUBLIC_API_URL` for a direct browser→VPS connection when the env var is set, bypassing the Vercel Function proxy that was hard-terminating the stream at its 10 s (Hobby) / 25 s (Pro) execution limit. Same-origin proxy route kept as fallback for local dev.
- **Vercel `maxDuration = 300`** — added to the SSE proxy route as an additional safety net for Pro deployments.
- **STALE badge** — if no SSE frame has been received in > 60 s the header shows an amber `STALE` pill next to the LIVE dot (uses the 1-second `now` ticker already in the component, no extra timer).
- **PORTFOLIO ALPHA — Total NAV bar** — new summary row at the top of the PERFORMANCE section showing total NAV (₩ KRW), total P&L (₩), and return % aggregated across all virtual accounts.

---

## What's New in v0.4.9

- **Virtual Order Log panel** — new slide-out panel ("ORDERS" button in AI Advice section) listing all executed virtual trades: time, ticker, BUY/SELL (green/red), quantity, fill price, currency, and status (FILLED/PENDING/REJECTED). Includes a RESET button to clear the virtual portfolio from the panel.
- **`GET /api/v1/portfolio/orders`** — new backend endpoint returning the 100 most recent virtual orders from the `virtual_orders` table, newest first.
- **`fetch_virtual_orders()`** — new `src/database.py` helper (idiomatic query pattern, safe fallback on error).
- **`VirtualOrderDTO` / `VirtualOrdersResponse` types** — added to `lib/types.ts`; `useVirtualOrders` hook (10-s SWR poll); Next.js proxy at `/api/v1/portfolio/orders`.

---

## What's New in v0.4.8

- **Live Alert Bell** — `_ALERT_RING` ring buffer (capped at 30) is populated on every regime transition and exposed via `GET /api/v1/alerts/live`. A self-contained `AlertBell` component in the dashboard header shows a red unread-count badge and a dropdown of recent regime-transition alerts color-coded by severity (info / warning / critical). Marks all read on open.
- **`LiveAlertItem` / `LiveAlertsResponse` types** — added to `lib/types.ts`; `useAlertsFeed` hook polls every 15 s; Next.js proxy at `/api/v1/alerts/live`.

---

## What's New in v0.4.7

- **Daily Market Brief** — new `GET /api/narrative/brief` endpoint calls the configured LLM (Groq/Ollama) with the current market snapshot (regime, VIX, yields, top movers) and returns a structured brief: `headline`, `signal` (RISK-ON / RISK-OFF / NEUTRAL), `bullets`, and `body`. Cached 5 minutes in-process. Falls back to a rule-based summary when no LLM is available.
- **BRIEF panel** — new slide-out panel in the dashboard accessible via the "BRIEF" button in the AI Advice section. Shows the signal badge (colored by stance), headline, key observation bullets, and narrative paragraph. Auto-refreshes every 5 minutes.
- **OMNI universe expanded** — `_AGENT_SYSTEM_PROMPT` now lists all 16 tickers (was only 5) so the LangChain ReAct agent has full coverage when analyzing the portfolio.
- **`DailyBriefDTO` type** — added to `lib/types.ts`; `useDailyBrief` hook in `useAlephData.ts`; Next.js proxy at `/api/narrative/brief`.

---

## What's New in v0.4.6

- **Live fundamentals** — `GET /api/fundamentals/{ticker}` streams P/E (trailing + forward), EPS, market cap, beta, dividend yield, gross margin, revenue growth, D/E ratio via yfinance (10-min in-process cache). Works for all 16 tickers including KR codes (`.KS` suffix auto-applied via `LIVE_TICKERS`).
- **PRICE ↔ FUNDAMENTALS tab** — ticker detail panel now has a two-tab header. PRICE shows the existing mini chart + session stats; FUNDAMENTALS shows the full data grid with sector/industry labels.
- **Sector allocation bar chart** — sector heatmap toggle `% CHG / ALLOC` switches between the sentiment grid and a live horizontal bar chart derived from `GET /api/portfolio/allocation`. Concentration warning appears inline if any sector exceeds 40%.
- **AI Advice — real data** — the "DIVERSIFY TECH" advice card now reads from live `PortfolioAllocationDTO` (HHI + top sector + concentration warning) instead of a hardcoded string.
- **Correlation matrix panel** — CORREL button opens a slide-out panel with the 16-ticker 30-day Pearson matrix color-coded (green positive / red negative / intensity by strength). Fetched from `GET /api/portfolio/correlation`.

---

## What's New in v0.4.4 (quality pass)

- **API layer unification** — all `fetch()` calls removed from component files. New custom hooks: `useOmniStream` (OMNI-COMMAND SSE), `useNewsSummary` (news AI stream), `useSectorSummary`, `usePortfolio(period)`, `useRegimeStatus`, `useMacroSnapshot`.
- **Error handling** — regime badge now shows specific Korean messages (`서버 연결 실패` / `응답 시간 초과` / `분석에 필요한 지표 부족`) instead of generic "UNAVAILABLE". Trust metadata drives degraded/stale badges on GLOBAL MACRO and SIGNALS sections.
- **Data freshness UI** — "마지막 수집: X시간 전" in the status bar; per-indicator freshness dots on FED/T10Y rate rows.
- **Real performance data** — HOLDING/CASH tiles now compute from virtual portfolio SSE; risk bars derive from live SELL/HOLD/BUY signal distribution instead of hardcoded percentages. Commodity rows replaced with "AWAITING FEED".
- **TypeScript** — `MacroSnapshot`, `MacroFeature`, `PortfolioData` type aliases added to `lib/types.ts`; `tsc --noEmit` passes cleanly with zero `any`.
- **Legacy cleanup** — `legacy/` directory moved to `_archive/`; no active code referenced it.

---

## What's New in v0.4.4 (original)

- **Fixed 4 missing holdings rows** — the four KR tickers added to live collection in v0.4.1 (현대차/삼성바이오로직스/POSCO홀딩스/KB금융) were never added to the frontend's `TICKER_META`/`TICKER_ORDER` registries, so they silently never rendered in PORTFOLIO ALPHA despite being priced on the backend. All 16 holdings now display.
- **Real news source/link/timestamp** — `/api/events/recent` previously returned only headline strings with a fabricated "now" timestamp. It now carries each article's real publisher, source URL, and publish time through from Yahoo Finance, so the NEWS FEED detail panel's source badge and "VIEW SOURCE ↗" link are now real instead of always empty.
- **52-week range on ticker detail** — clicking a holding now also fetches and displays its 52-week high/low via a new on-demand `GET /api/tickers/{ticker}/detail` endpoint.

---

## What's New in v0.4.2

- **Floating detail panels** — clicking a holding row in PORTFOLIO ALPHA now opens a floating panel with that ticker's live price, session change, and price-history chart; clicking a NEWS FEED item opens a floating panel with the full headline, sentiment, source, and source link. Both reuse the OMNI-COMMAND `ResearchPanel` slide-out pattern (`apps/frontend/components/DetailPanel.tsx`).

---

## What's New in v0.4.1

- **KR large-cap sector diversification** — 4 new tickers added to live collection: 현대차/Hyundai Motor(005380, KR_AUTO), 삼성바이오로직스/Samsung Biologics(207940, KR_BIO), POSCO홀딩스(005490, KR_STEEL), KB금융(105560, KR_FINANCE). Risk matrix now 16 rows, spanning tech, chemicals, auto, bio, steel, and finance sectors instead of being tech/chem-heavy.

---

## What's New in v0.4.0

- **Virtual Broker (paper trading engine)** — typing a command like *"현재 자산 배분 리스크를 고려해서 포트폴리오 최적화하고 가상 매수해줘"* into OMNI-COMMAND now lets the LangChain agent autonomously place simulated trades. New `virtual_accounts` / `virtual_orders` / `portfolio_holdings` TimescaleDB tables back an immediate-fill execution model with currency-separated books (KRW account + USD account — no FX conversion).
- **LLM tool calling for trading** — three new LangChain tools registered on the agent: `get_portfolio_summary_tool` (cash/holdings/P&L), `run_backtest_tool` (strategy validation before sizing an order), and `execute_virtual_order_tool` (places the trade). The agent is instructed to check cash, validate the strategy, and confirm the resulting position before reporting back.
- **Lightweight vectorized backtesting** — new `BacktestEngine` in `src/engines.py` runs a SMA(5/20) crossover simulation entirely in pandas/NumPy (no event loop, no Backtrader dependency) — total return %, max drawdown %, and trade count over a ticker's price history.
- **`GET /api/v1/portfolio/summary`** — standalone REST endpoint for the current virtual-broker state. The same `virtual_portfolio` shape is also included additively on every SSE tick and OMNI command response.

---

## What's New in v0.3.1

- **Streaming AI Research Panel** — OMNI-COMMAND now opens a Framer Motion slide-out panel on the right side of the screen. Tokens stream word-by-word via a new `POST /api/v1/intelligence/command/stream` SSE endpoint, so the report appears progressively rather than all at once.
- **ResearchPanel.tsx** — new component with backdrop dimming, metadata chips (Regime / Health / Confidence / Signal), auto-scrolling during stream, and a custom lightweight markdown renderer (headers, bullets, bold, dividers — no heavy dependency).
- **Node.js 22 → 24 LTS** — all three Docker stages updated to `node:24-alpine`. `.nvmrc` added. `engines.node >= 24` enforced in `package.json`.
- **uv build tool** — API Dockerfile updated from pinned `uv:0.4.29` to `uv:latest`.
- **FRED adapter** — per-series graceful failure: one bad series (e.g. NAPM HTTP 400) no longer aborts the entire fetch. PMI mapping changed from restricted `NAPM` to publicly available `MANEMP`.

---

## What's New in v0.3.0

- **SSE reconnect with exponential backoff** — `useAlephStream` hook rebuilt with full jitter backoff (3→6→12→30 s), tab-visibility reconnect, and proper singleton teardown. Eliminates `RECONNECTING` freeze on Vercel.
- **Macro indicators batch engine** — `fetch_macro_indicators()` in `src/database.py` fetches T10Y, T3M, VIX from yfinance and FEDFUNDS/CPI/GDP/UNRATE from FRED (when `FRED_API_KEY` set). Persisted to `macro_indicators` TimescaleDB hypertable. Hourly `_macro_collector_loop()` starts at server boot.
- **`macro_indicators` in SSE payload** — `_MACRO_CACHE` dict included in every tick. Dashboard wires VIX, T10Y, FED_RATE from live stream instead of static hardcoded values.
- **Milvus price-alert sync bridge** — `embed_price_alert()` in `src/database.py` detects ≥2% price moves in `fetch_live_market_data()` and immediately embeds a text event ("삼성전자 3.2% 급락 …") into Milvus so the LangChain RAG agent has real-time context.
- **`macro_indicators` hypertable** — `macro_indicators(snapshot_time, series_id, value, source)` with 30-day TimescaleDB chunks.
- **`FRED_API_KEY` env var** — optional; falls back to yfinance proxies when absent.

---

## What's New in v0.2.1

- **KR large-cap expansion** — NAVER(035420), LG화학(051910), 삼성SDI(006400), KODEX LEV(122630) added to live collection. Risk matrix now 12 rows.
- **Real index data** — KOSPI(^KS11), S&P 500(^GSPC), USD/KRW(KRW=X) fetched live via yfinance every cycle, replacing GBM simulation. `market_indices` field added to SSE payload.
- **Index chart toggle** — `[PORTFOLIO][KOSPI][S&P][KRW]` neon buttons switch the central chart between portfolio value and live index history.
- **KST hybrid scheduler** — `_get_collection_interval()` returns 10 s during KR (09:00–15:30 KST) and US (22:30–05:00 KST) trading sessions, 60 s off-hours.
- **OMNI-COMMAND offline fallback** — command proxy returns HTTP 200 with a structured offline payload instead of propagating 502 when the backend is unreachable.

---

## What's New in v0.2.0

- **Production config** — `src/config.py` unified LLM switching: `ENV_MODE=PRODUCTION` forces Groq, `LOCAL` prefers Groq and falls back to Ollama. `CORS_ALLOWED_ORIGINS` env var for runtime domain injection.
- **Milvus Lite** — Docker Milvus (~1 GB RAM) replaced with embedded `MilvusClient` file-based store. Saves ~1 GB on a 2 GB VPS — no extra container needed.
- **`docker-compose.prod.yml`** — slim production stack: FastAPI + TimescaleDB only, 800 MB memory limit per container, named volumes. Oracle Free Tier-compatible.
- **GitHub Actions CD** — `.github/workflows/backend-cd.yml`: Docker Hub build/push + SSH rolling deploy to DigitalOcean / any VPS on every `main` push.
- **Frontend route fixes** — `/api/v1/intelligence/command` proxy route added, `/api/events/recent` proxy added, `API_BASE_URL` → `ALEPH_API_URL` unified.
- **Env var documentation** — `.env.example` and `apps/frontend/.env.local.example` updated for all new variables.

---

## What's New in v0.1.2

- **Global ETF pipeline** — QQQ (Nasdaq 100), BND (Total Bond), GLD (Gold) added to live collection. `risk_matrix` now 8 rows.
- **KST time axis** — all `market_ticks` DB inserts and SSE `timestamp` fields normalised to `Asia/Seoul` (`+09:00`).
- **ETF-specific volatility branch** — `QuantEngine` uses ATR(14)-based spike detection for ETFs (threshold 2.5 %, ratio 1.3×) vs raw σ for stocks.
- **Live news feed** — static `NEWS` array replaced by SWR 30-second polling from `/api/events/recent`.
- **Asset class tab UI** — `[ALL] [STOCKS] [ETFS] [FUNDS]` neon toggle tabs with `filteredOrder` dynamic rendering. `FUNDS` tab shows "AWAITING FEEDS" mask.
- **Holdings scroll lock** — `maxHeight: calc(100vh - 420px)` prevents layout collapse as ticker count grows.

---

## Features

### Live Data Pipeline — Yahoo Finance
- OHLCV ingestion for **16 assets**: AAPL · MSFT · TSLA · 삼성전자(005930) · SK하이닉스(000660) · NAVER(035420) · LG화학(051910) · 삼성SDI(006400) · KODEX LEV(122630) · 현대차(005380) · 삼성바이오로직스(207940) · POSCO홀딩스(005490) · KB금융(105560) · QQQ · BND · GLD
- News headline collection per ticker with automatic retry (×3, exponential back-off)
- DELETE + COPY bulk upsert into TimescaleDB hypertable (`market_ticks`, 7-day chunks)
- All timestamps stored and emitted in **KST (Asia/Seoul, +09:00)**
- Background asyncio collector: starts on first SSE connect, cancels on last disconnect — zero idle overhead

### Multi-Engine Intelligence Layer
Three quantitative formulas from legendary investors, wired in sequence:

| Engine | Formula | Trigger |
|--------|---------|---------|
| **QuantEngine** (Ray Dalio — Volatility Targeting) | Stocks: σ₅/σ₂₀ > 1.5 → `vol_spike`, score −0.15 · ETFs: ATR(14) ratio > 1.3 → spike, score −0.10 | 5-day vs baseline volatility |
| **SentimentEngine** (James Simons — Regime Switching) | Crisis keyword frequency ≥ 3 or > 3 % of tokens → `CRISIS_MODE` | News headlines |
| **PersonaAdapterEngine** (Warren Buffett — Margin of Safety) | CONSERVATIVE + RSI(14) ≥ 70 → BUY locked to HOLD | Per-ticker RSI |

### Virtual Broker — Paper Trading Engine
- LangChain agent tools: `get_portfolio_summary_tool`, `run_backtest_tool`, `execute_virtual_order_tool`
- Immediate-fill execution against the live tick price — no real brokerage involved
- Currency-separated books: a KRW account for 6-digit KR tickers, a USD account for everything else
- Orders are rejected (not raised as errors) on insufficient cash or insufficient holdings
- `GET /api/v1/portfolio/summary` — cash, mark-to-market holdings, and P&L per currency

### Real-Time SSE Stream
- `GET /api/v1/intelligence/stream` — 1-second tick, full UI-contract JSON payload
- Payload includes `timestamp` (KST ISO-8601), `portfolio_health`, `macro_regime`, `active_signals`, `network_nodes` (3D Fibonacci sphere), `risk_matrix` (16 rows)

### Aleph-One Dashboard UI (Next.js 15)
- Cyberpunk glassmorphism design — Orbitron / Rajdhani / JetBrains Mono fonts
- Real-time portfolio chart wired to SSE `portfolio_value`
- `[ALL][STOCKS][ETFS][FUNDS]` asset class tab filtering
- SWR live news feed (30 s polling)
- OMNI-COMMAND terminal → `POST /api/v1/intelligence/command`

### OMNI Command Terminal
- `POST /api/v1/intelligence/command` — natural-language query → structured intelligence report
- Primary path: LangChain agent with RAG `search_news_database` tool
- Fallback: keyword-scenario matching (no LLM dependency required to boot)

### Milvus RAG — Semantic News Search
- Every 60 s: Yahoo Finance headlines embedded with `all-MiniLM-L6-v2` → upserted to Milvus `news_collection` (HNSW, COSINE)
- SHA-256 title deduplication across cycles
- Graceful degradation: in-memory fallback if Milvus is unreachable

### Zero-Cost AI Architecture
- LLM: **ChatGroq** (Llama 3.1 8B Instant, free tier) or **ChatOllama** (fully local) — switched via `ENV_MODE`
- Embeddings: **HuggingFace sentence-transformers** (`all-MiniLM-L6-v2`, CPU, 384-dim)
- Vector DB: **Milvus Lite** (embedded file-based, zero extra RAM vs Docker Milvus)
- No Anthropic, OpenAI, or Cohere keys required

---

## Quick Start

### Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker + Compose | ≥ 24 | For TimescaleDB + Milvus |
| Python | ≥ 3.12 | Backend runtime |
| Node.js | ≥ 20 | Frontend (Next.js 15) |
| uv | latest | `pip install uv` |
| Groq API key | free | [console.groq.com](https://console.groq.com) — or use Ollama |

### 1. Clone and configure

```bash
git clone https://github.com/MinseongKim-dev/macro-invest-agent-system.git
cd macro-invest-agent-system
cp .env.example .env
# Set GROQ_API_KEY (or switch to Ollama — see below)
```

### 2. Start infrastructure

```bash
docker compose up -d timescaledb milvus-standalone
```

### 3. Install dependencies

```bash
# Backend
uv sync

# Frontend
cd apps/frontend && npm install && cd ../..
```

### 4. Run services

```bash
# Backend (port 8001)
uv run uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# Frontend (port 3000)
cd apps/frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) for the Aleph-One command center.

### 5. Full stack with Docker Compose

```bash
docker compose up --build
```

Brings up TimescaleDB, Milvus, MinIO, FastAPI backend, and Next.js frontend.

---

## Using Ollama instead of Groq

```bash
ollama pull llama3.1:8b
```

Set in `.env`:

```ini
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

---

## Environment Variables

```ini
# LLM — Groq (free tier) or Ollama (local)
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.1-8b-instant

# TimescaleDB
DATABASE_URL=postgresql+psycopg://macro_user:macro_pass@localhost:5432/macro_db
POSTGRES_USER=macro_user
POSTGRES_PASSWORD=macro_pass
POSTGRES_DB=macro_db

# Milvus (optional — in-memory fallback if absent)
MILVUS_HOST=localhost
MILVUS_PORT=19530

# Application
APP_ENV=local
LOG_LEVEL=INFO
LOG_PRETTY=true
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/api/v1/intelligence/stream` | SSE stream — 1 s tick, KST timestamp |
| `POST` | `/api/v1/intelligence/command` | OMNI terminal — LangChain agent + scenario fallback |
| `GET` | `/api/v1/regimes/latest` | Current macro regime |
| `GET` | `/api/v1/events/recent?limit=15` | Recent macro events (news feed) |
| `GET` | `/api/v1/portfolio/summary` | Virtual broker state — cash, holdings, P&L by currency |

### SSE Payload Schema (v0.1.2)

```json
{
  "timestamp": "2026-05-25T14:32:01+09:00",
  "status": "LIVE",
  "portfolio_health": { "score": 72.4, "source": "MARKET_DATA" },
  "macro_regime": {
    "regime_name": "POLICY_TIGHTENING",
    "market_phase": "LATE_CYCLE",
    "confidence_score": 0.85
  },
  "active_signals": [
    { "action": "BUY", "strategy": "momentum_breakout", "probability": 0.72 }
  ],
  "intelligence_synthesis": {
    "assets_count": 8,
    "network_nodes": [
      { "id": "QQQ ETF", "x": 0.15, "y": -0.32, "z": 0.45, "group": "ETF_TECH" }
    ],
    "risk_matrix": [
      { "ticker": "AAPL",  "momentum": "WATCH", "regime": "STABLE", "sig_score": "HOLD" },
      { "ticker": "QQQ",   "momentum": "STABLE", "regime": "STABLE", "sig_score": "BUY" },
      { "ticker": "BND",   "momentum": "STABLE", "regime": "STABLE", "sig_score": "HOLD" },
      { "ticker": "GLD",   "momentum": "WATCH",  "regime": "STABLE", "sig_score": "BUY"  }
    ]
  },
  "virtual_portfolio": {
    "accounts": {
      "USD": { "cash_balance": 98000.0, "market_value": 2000.0, "total_value": 100000.0, "initial_balance": 100000.0, "total_pl": 0.0, "total_pl_pct": 0.0 }
    },
    "holdings": [
      { "ticker": "AAPL", "quantity": 10.0, "avg_cost": 200.0, "currency": "USD", "live_price": 200.0, "market_value": 2000.0, "unrealized_pl": 0.0 }
    ]
  }
}
```

---

## Project Structure

```
macro-invest-agent-system/
├── apps/
│   ├── api/               # FastAPI Dockerfile + entry
│   └── frontend/          # Next.js 15 UI (AlephDashboard)
│       ├── app/           # App router, SSE proxy route
│       ├── components/    # AlephDashboard, panels
│       └── hooks/         # useAlephStream, useMarketStream, useNewsStream
├── src/                   # Tri-File Architecture backend core
│   ├── database.py        # TimescaleDB pool, DDL, yfinance pipeline, Milvus
│   ├── engines.py         # QuantEngine (ETF/stock branch), SentimentEngine, PersonaAdapterEngine
│   └── main.py            # FastAPI SSE + OMNI command + LangChain RAG
├── docs/                  # Architecture docs, ADRs, domain dictionary
├── docker-compose.yml     # TimescaleDB + Milvus + MinIO + app services
└── CLAUDE.md              # AI agent working instructions
```

---

## Roadmap

| Version | Status | Description |
|---------|--------|-------------|
| **v0.1.0** | ✅ Released | Monorepo layout, zero-cost LLM, Milvus RAG, KR stocks |
| **v0.1.1** | ✅ Released | ETF pipeline (QQQ/BND/GLD), KST time axis, live news feed |
| **v0.1.2** | ✅ Released | ETF ATR volatility branch, asset class tab UI, Holdings scroll lock |
| **v0.2.0** | ✅ Released | DigitalOcean hybrid infra — Milvus Lite, `docker-compose.prod.yml`, GitHub Actions CD |
| **v0.2.1** | ✅ Released | KR large-cap expansion (NAVER/LG화학/삼성SDI), `index_ticks` hypertable, chart index toggle, KST hybrid scheduler |
| **v0.3.0** | ✅ Released | SSE reconnect backoff, macro indicators batch engine, Milvus price-alert sync bridge |
| **v0.3.1** | ✅ Released | Slide-out AI Research Panel, LangChain real-time token streaming |
| **v0.4.0** | ✅ Released | Virtual Broker — paper trading engine, LLM tool calling, vectorized backtesting |
| **v0.4.1** | ✅ Released | KR large-cap sector diversification — auto/bio/steel/finance tickers, risk matrix → 16 rows |
| **v0.4.2** | ✅ Released | Floating click-to-expand detail panels for holdings and news items |
| **v0.4.3** | ✅ Released | Fixed missing holdings rows, real news source/link/timestamp, 52-week range on ticker detail |
| **v0.4.4** | ✅ Released | Chart period tabs (1D/1W/1M/3M), live sector heatmap, news AI analysis, ANALYZE wired to OMNI, real Sharpe metric |
| **v0.4.4-q** | ✅ Released | Quality pass: API hook unification, trust-badge error states, freshness UI, legacy cleanup |
| **v0.4.5** | ✅ Released | What-If Scenario Engine — 5 built-in presets (골디락스/공황/스태그플레이션/연준긴축/소프트랜딩), conviction delta, strategy pivot detection, OMNI `run_scenario_tool` |
| **v0.4.6** | ✅ Released | Fundamentals + Portfolio Intelligence — live P/E/EPS/market cap/beta/dividend via yfinance, PRICE↔FUNDAMENTALS tab in detail panel, sector allocation bar chart with HHI concentration warning, 16-ticker Pearson correlation matrix slide panel |
| **v0.4.7** | ✅ Released | LLM Narrative Copilot — daily market brief endpoint with Groq LLM integration, BRIEF slide-out panel (signal badge + bullets + narrative), OMNI universe expanded to all 16 tickers |
| **v0.4.8** | ✅ Released | Live Alert Feed + Notification Bell — regime-transition ring buffer, `/api/v1/alerts/live`, header bell with unread badge and severity-colored dropdown |
| **v0.4.9** | ✅ Released | Virtual Order Log — `/api/v1/portfolio/orders` endpoint, ORDERS slide-out panel with trade history (side-colored rows, fill price, status badge, inline reset) |
| **v0.4.10** | ✅ Released | SSE stability fix (direct browser→VPS connection bypassing Vercel timeout), STALE data badge, PORTFOLIO ALPHA total NAV summary bar |
| **v0.5.0** | ⏳ Pending | Fund NAV daily batch (KOFIA OpenAPI) — blocked on a working KOFIA/data.go.kr API key |
| **v1.0.0** | ⏳ Pending | Ray Dalio All-Weather rebalancing engine |
| **v2.0.0** | ⏳ Pending | Vercel (frontend) + VPS (backend) cloud deployment |

---

## Development

```bash
# Python lint
uv run ruff check src/ apps/api/

# Python type check
uv run mypy src/main.py src/engines.py src/database.py

# Frontend type check
npx tsc --noEmit -p apps/frontend/tsconfig.json

# Tests
uv run pytest tests/ -q
```

---

## License

MIT — see [LICENSE](LICENSE).
