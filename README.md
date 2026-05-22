# Aleph-One

**v0.1.0** · Open-source, zero-cost financial intelligence terminal

Aleph-One is a J.A.R.V.I.S.-style hybrid financial intelligence system. It ingests live market data from Yahoo Finance, runs three quantitative engine layers inspired by legendary investors, streams structured signals to a Next.js UI over SSE, and interprets queries through a free-tier LangChain agent — all without a single paid API call.

---

## Features

### Live Data Pipeline — Yahoo Finance
- On-demand OHLCV ingestion for equities across US and KR markets (AAPL, MSFT, TSLA, Samsung 005930.KS, SK Hynix 000660.KS)
- News headline collection per ticker with automatic retry (×3, exponential back-off)
- DELETE + COPY bulk upsert into TimescaleDB hypertable (`market_ticks`, 7-day chunks)
- Background asyncio collector: starts on first SSE connect, cancels on last disconnect — zero idle overhead

### Multi-Engine Intelligence Layer
Three quantitative formulas from legendary investors, wired in sequence:

| Engine | Formula | Trigger |
|--------|---------|---------|
| **QuantEngine** (Ray Dalio — Volatility Targeting) | σ₅ / σ₂₀ > 1.5 → `vol_spike=True`, momentum score −0.15 | 5-day vs 20-day σ ratio |
| **SentimentEngine** (James Simons — Regime Switching) | Crisis keyword frequency ≥ 3 or > 3 % of tokens → `regime_switch=True` → `CRISIS_MODE` | News headlines |
| **PersonaAdapterEngine** (Warren Buffett — Margin of Safety) | CONSERVATIVE persona + RSI(14) Wilder ≥ 70 → BUY locked to HOLD | Per-ticker RSI |

### Real-Time SSE Stream
- `GET /api/v1/intelligence/stream` — 1-second tick, full UI-contract JSON payload
- Includes `portfolio_health`, `macro_regime`, `active_signals`, `network_nodes` (3D Fibonacci sphere), `risk_matrix` (5 × 5 SVG grid)
- Hyper-futuristic glassmorphism frontend at `apps/frontend/public/aleph-one/` (Three.js, pure SVG, no framework)

### OMNI Command Terminal
- `POST /api/v1/intelligence/command` — natural-language query → structured intelligence report
- Primary path: LangChain 1.x agent (`langchain.agents.create_agent`) with two `@tool` functions calling live engine data
- Fallback: keyword-scenario matching (no LLM dependency required to boot)

### Zero-Cost AI Architecture
- LLM: **ChatGroq** (Llama 3.1 8B Instant, free tier — 14 400 req/day) or **ChatOllama** (fully local, no API key)
- Embeddings: **HuggingFace sentence-transformers** (`all-MiniLM-L6-v2`) — pre-wired for Milvus RAG in Phase 3.2
- No Anthropic, OpenAI, or Cohere API keys required

---

## Quick Start

### Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker + Compose | ≥ 24 | For TimescaleDB + Milvus |
| Python | ≥ 3.12 | Backend runtime |
| uv | latest | Dependency manager (`pip install uv`) |
| Groq API key | free | [console.groq.com](https://console.groq.com) — or use Ollama instead |

### 1. Clone and configure environment

```bash
git clone https://github.com/MinseongKim-dev/macro-invest-agent-system.git
cd macro-invest-agent-system
cp .env.example .env
# Edit .env — set GROQ_API_KEY (or switch to Ollama, see below)
```

### 2. Start infrastructure

```bash
docker compose up -d timescaledb milvus-standalone
```

TimescaleDB is ready when `pg_isready` returns healthy (the compose healthcheck handles this automatically).

### 3. Install Python dependencies

```bash
uv sync
```

### 4. Run the backend

```bash
uv run uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

The API is live at `http://localhost:8001`. Open `apps/frontend/public/aleph-one/index.html` in your browser to launch the Aleph-One command center.

### 5. (Optional) Full stack with Docker Compose

```bash
docker compose up --build
```

This brings up TimescaleDB, Milvus, MinIO, and the FastAPI backend in a single command.

---

## Using Ollama instead of Groq

If you prefer fully local inference with no API key:

```bash
# Install Ollama: https://ollama.com
ollama pull llama3.1:8b
```

Then set in `.env`:

```
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

The agent will automatically route through ChatOllama at startup.

---

## Environment Variables

Copy `.env.example` → `.env` and fill in the values below.

```
# LLM — choose Groq (free tier) or Ollama (local)
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.1-8b-instant      # default

# Optional Ollama override
# LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=llama3.1:8b

# TimescaleDB
DATABASE_URL=postgresql+psycopg://macro_user:macro_pass@localhost:5432/macro_db
POSTGRES_USER=macro_user
POSTGRES_PASSWORD=macro_pass
POSTGRES_DB=macro_db

# Application
APP_ENV=local
LOG_LEVEL=INFO
LOG_PRETTY=true
```

No `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or any other paid-tier key is needed.

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/api/v1/intelligence/stream` | SSE stream — full UI-contract payload, 1 s tick |
| `POST` | `/api/v1/intelligence/command` | OMNI terminal — LangChain agent + scenario fallback |
| `GET` | `/api/v1/regimes/latest` | Current macro regime from TimescaleDB |
| `GET` | `/api/v1/events/recent` | Recent macro events |

### SSE Payload Schema

```json
{
  "timestamp": "<ISO-8601>",
  "status": "LIVE | SYNCING | ERROR",
  "portfolio_health": { "score": 0.0, "source": "MARKET_DATA" },
  "macro_regime": {
    "regime_name": "POLICY_TIGHTENING | CRISIS_MODE | VOLATILITY_REGIME",
    "market_phase": "LATE_CYCLE",
    "confidence_score": 0.85
  },
  "active_signals": [
    { "action": "BUY | HOLD | SELL", "strategy": "...", "probability": 0.72 }
  ],
  "intelligence_synthesis": {
    "assets_count": 5,
    "vector_mode": "AI-WEIGHTED VECTORS",
    "network_nodes": [{ "id": "AAPL", "x": 0.15, "y": -0.32, "z": 0.45, "group": "TECH" }],
    "risk_matrix": [
      { "ticker": "AAPL", "momentum": "WATCH", "regime": "STABLE",
        "rates": "WATCH", "sentiment": "STABLE", "sig_score": "HOLD" }
    ]
  }
}
```

---

## Project Structure

```
macro-invest-agent-system/
├── apps/                  # Deliverable surfaces
│   ├── api/               # FastAPI app, routers, DTOs, startup seeder
│   ├── frontend/          # Next.js 14 UI + Aleph-One glassmorphism prototype
│   └── cli/               # Developer CLI
├── src/                   # All backend logic (layered architecture)
│   ├── core/              # Config, exceptions, logging, metrics, tracing
│   │   ├── alembic/       # DB migration scripts
│   │   └── storage/       # Repository interfaces
│   ├── agent/             # LangChain agent, MCP tools, data adapters
│   ├── domain/            # Pure domain models (macro, signals, events, quant)
│   ├── pipelines/         # Ingestion jobs, FRED normalizer
│   ├── services/          # Application services (orchestration layer)
│   ├── database.py        # TimescaleDB connection, DDL, yfinance pipeline
│   ├── engines.py         # QuantEngine, SentimentEngine, PersonaAdapterEngine
│   └── main.py            # FastAPI app, SSE stream, OMNI terminal
├── tests/                 # Unit tests + eval harness
│   └── evals/             # Schema conformance, multi-turn, provider failure evals
├── docs/                  # Architecture docs, ADRs, domain dictionary
├── deploy/                # Docker, Kubernetes manifests
└── docker-compose.yml     # TimescaleDB + Milvus + MinIO orchestration
```

---

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 2.x | ✅ Done | Multi-engine formulas, Aleph-One UI, yfinance live pipeline |
| 3.1 | ✅ Done | LangChain agent wired to OMNI terminal |
| 3.2 | 🔜 Next | Milvus vector store — news embedding + semantic RAG search |
| 4.0 | ✅ Done | v0.1.0 layered architecture refactor + zero-cost LLM migration |

---

## Development

```bash
# Lint
uv run ruff check src/ apps/ tests/

# Type check
uv run mypy src/main.py src/engines.py src/database.py

# Tests
uv run pytest tests/ -q
```

**1 385 tests, 0 failures** on Python 3.12 (CI-verified).

---

## License

MIT — see [LICENSE](LICENSE).
