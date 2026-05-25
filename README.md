# Aleph-One

**v0.1.2** · Open-source, zero-cost financial intelligence terminal

Aleph-One is a J.A.R.V.I.S.-style hybrid financial intelligence system. It ingests live market data from Yahoo Finance, runs three quantitative engine layers inspired by legendary investors, streams structured signals to a Next.js UI over SSE, and interprets queries through a free-tier LangChain agent — all without a single paid API call.

---

## What's New in v0.1.2

- **Global ETF pipeline** — QQQ (Nasdaq 100), BND (Total Bond), GLD (Gold) added to live collection. `risk_matrix` now 8 rows.
- **KST time axis** — all `market_ticks` DB inserts and SSE `timestamp` fields normalised to `Asia/Seoul` (`+09:00`).
- **ETF-specific volatility branch** — `QuantEngine` uses ATR(14)-based spike detection for ETFs (threshold 2.5 %, ratio 1.3×) vs raw σ for stocks.
- **Live news feed** — static `NEWS` array replaced by SWR 30-second polling from `/api/events/recent`.
- **Asset class tab UI** — `[ALL] [STOCKS] [ETFS] [FUNDS]` neon toggle tabs with `filteredOrder` dynamic rendering. `FUNDS` tab shows "AWAITING FEEDS" mask (v0.3.0 pipeline).
- **Holdings scroll lock** — `maxHeight: calc(100vh - 420px)` prevents layout collapse as ticker count grows.

---

## Features

### Live Data Pipeline — Yahoo Finance
- OHLCV ingestion for **8 assets**: AAPL · MSFT · TSLA · 삼성전자(005930) · SK하이닉스(000660) · QQQ · BND · GLD
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

### Real-Time SSE Stream
- `GET /api/v1/intelligence/stream` — 1-second tick, full UI-contract JSON payload
- Payload includes `timestamp` (KST ISO-8601), `portfolio_health`, `macro_regime`, `active_signals`, `network_nodes` (3D Fibonacci sphere), `risk_matrix` (8 rows)

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
- LLM: **ChatGroq** (Llama 3.1 8B Instant, free tier) or **ChatOllama** (fully local)
- Embeddings: **HuggingFace sentence-transformers** (`all-MiniLM-L6-v2`, CPU, 384-dim)
- Vector DB: **Milvus Standalone** (self-hosted Docker)
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
| **v0.1.0** | ✅ Stable | Monorepo layout, zero-cost LLM, Milvus RAG, KR stocks |
| **v0.1.1** | ✅ Released | ETF pipeline (QQQ/BND/GLD), KST time axis, live news feed |
| **v0.1.2** | ✅ Released | ETF ATR volatility branch, asset class tab UI, Holdings scroll lock |
| **v0.2.0** | ⏳ Pending | KR large-cap expansion (NAVER/LG화학/삼성SDI), `index_ticks` hypertable, chart index toggle |
| **v0.2.1** | ⏳ Pending | KST-aware market-hours hybrid scheduler (10 s during session, 60 s off-hours) |
| **v0.3.0** | ⏳ Pending | Fund NAV daily batch (KOFIA OpenAPI), `[FUNDS]` tab live data |
| **v0.3.1** | ⏳ Pending | Milvus financial chunking + keyword re-ranking |
| **v0.4.0** | ⏳ Pending | Slide-out AI Research Panel (react-markdown) |
| **v0.4.1** | ⏳ Pending | LangChain real-time token streaming |
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
