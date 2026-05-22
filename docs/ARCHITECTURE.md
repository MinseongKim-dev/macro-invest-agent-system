# Aleph-One — Architecture Reference

**v0.1.0** · Last updated: 2026-05-22

---

## 1. Layered Architecture

Aleph-One follows a strict layered architecture. Every layer has a single responsibility and depends only on layers below it. No upward dependencies are permitted.

```
┌─────────────────────────────────────────────────────────────────┐
│  apps/                         Deliverable surfaces              │
│  ├── api/          FastAPI routers, DTOs, startup seeder        │
│  ├── frontend/     Next.js 14 + glassmorphism UI prototype      │
│  └── cli/          Developer CLI                                │
├─────────────────────────────────────────────────────────────────┤
│  src/main.py                   SSE stream + OMNI terminal       │
│  src/engines.py                Multi-engine intelligence layer  │
│  src/database.py               TimescaleDB + yfinance pipeline  │
├─────────────────────────────────────────────────────────────────┤
│  src/agent/                    Agent & integration layer        │
│  ├── runtime/      LangChain agent executor                     │
│  ├── mcp/          MCP tool schemas + handlers                  │
│  └── adapters/     In-memory stores, FRED source adapter        │
├─────────────────────────────────────────────────────────────────┤
│  src/services/                 Application services             │
│  (MacroService, RegimeService, SignalService, SnapshotService)  │
├─────────────────────────────────────────────────────────────────┤
│  src/domain/                   Domain model (pure logic)        │
│  ├── macro/        Snapshot, regime, comparison, history        │
│  ├── signals/      Signal engine, conflict detection, rules     │
│  ├── events/       Macro events, impact scoring                 │
│  ├── quant/        Scoring models                               │
│  └── alerts/       Alert rules and rule engine                  │
├─────────────────────────────────────────────────────────────────┤
│  src/pipelines/                Data ingestion                   │
│  └── ingestion/    FRED normalizer, indicator catalog           │
├─────────────────────────────────────────────────────────────────┤
│  src/core/                     Shared infrastructure            │
│  ├── config/       Settings (pydantic-settings)                 │
│  ├── exceptions/   Base error types, failure taxonomy           │
│  ├── logging/      Structured logger, timing decorator          │
│  ├── metrics/      Prometheus registry                          │
│  ├── tracing/      OpenTelemetry span attributes                │
│  ├── contracts/    Repository ABCs                              │
│  ├── storage/      Repository interfaces                        │
│  └── alembic/      DB migration scripts                         │
└─────────────────────────────────────────────────────────────────┘
```

### Dependency rule

```
apps  →  src/main, src/engines, src/database
       →  src/agent  →  src/services  →  src/domain
                     →  src/pipelines →  src/core
```

`src/domain` and `src/core` have no imports from any layer above them. This makes them independently testable and safe to refactor.

---

## 2. Directory Reference

| Path | Responsibility |
|------|---------------|
| `src/core/config/` | `Settings` dataclass — all env vars resolved at import time via pydantic-settings |
| `src/core/exceptions/` | `AlephBaseError`, `FailureCategory` enum — used by all layers for typed error propagation |
| `src/core/logging/` | `get_logger()`, `@timed_operation` decorator — wraps structlog with OpenTelemetry trace context |
| `src/core/metrics/` | Prometheus `CollectorRegistry` — exposes `/metrics` endpoint |
| `src/core/contracts/` | Abstract base classes for all repository interfaces (hexagonal port layer) |
| `src/core/storage/` | `AlertRepositoryInterface`, `EventRepositoryInterface`, `ExplanationRepositoryInterface` |
| `src/core/alembic/` | Alembic migration scripts for relational schema (non-hypertable tables) |
| `src/domain/macro/` | `MacroSnapshot`, `MacroRegime`, `RegimeLabel`, `SnapshotComparison`, `RegimeHistory` |
| `src/domain/signals/` | `SignalEngine`, `SignalConflictDetector`, regime-grounded signal rules |
| `src/domain/events/` | `MacroEvent`, `EventImpactScorer`, event normalizer |
| `src/domain/quant/` | `QuantScoreSet`, quant scoring logic |
| `src/domain/alerts/` | Alert `Rule`, `RuleEngine` — evaluated against regime + signal state |
| `src/pipelines/ingestion/` | `MacroIngestionService`, FRED normalizer, `IndicatorCatalog` |
| `src/services/` | Orchestrates domain objects; stateless application services |
| `src/agent/runtime/` | `LangChainRuntime`, `AgentRuntime`, output validation |
| `src/agent/mcp/` | MCP tool schemas (`get_macro_features`, `run_signal_engine`) |
| `src/agent/adapters/` | In-memory stores (regime, snapshot, alert, event, feature); FRED source adapter |
| `src/database.py` | psycopg3 connection pool, TimescaleDB DDL, yfinance OHLCV + news pipeline |
| `src/engines.py` | `QuantEngine`, `SentimentEngine`, `PersonaAdapterEngine`, `build_intelligence_row()` |
| `src/main.py` | FastAPI app, lifespan, SSE stream, OMNI terminal, LangChain agent |
| `apps/api/` | FastAPI routers (signals, regimes, events, alerts), DTOs, startup seeder |
| `apps/frontend/public/aleph-one/` | Standalone glassmorphism UI — Three.js 3D sphere, SVG risk matrix, world map |
| `tests/evals/` | Schema conformance, multi-turn conversation, provider failure, prompt regression evals |

---

## 3. On-Demand Hybrid Stream — Sequence Diagram

This is the critical path from browser connect to rendered intelligence card.

```
Browser                FastAPI (src/main.py)      src/database.py         src/engines.py
   │                          │                          │                      │
   │── GET /api/v1/intelligence/stream ──────────────────┤                      │
   │                          │                          │                      │
   │                          │── _SSE_CONNECTION_COUNT += 1                    │
   │                          │── asyncio.create_task(_live_collector_loop())   │
   │                          │                          │                      │
   │                ┌─────────┴─── Background task (60 s cycle) ───────────────┤
   │                │         │                          │                      │
   │                │         │── fetch_live_market_data()                      │
   │                │         │     yfinance.Ticker.history(period="5d")        │
   │                │         │     DELETE old rows + COPY bulk upsert          │
   │                │         │     → market_ticks hypertable (TimescaleDB)     │
   │                │         │                          │                      │
   │                │         │── fetch_live_news()       │                      │
   │                │         │     yfinance news headlines per ticker           │
   │                │         │     → _LIVE_NEWS_CACHE (in-memory)              │
   │                └─────────┤                          │                      │
   │                          │                          │                      │
   │          ┌── 1 s SSE tick loop ───────────────────────────────────────────┤
   │          │               │                          │                      │
   │          │               │── _fetch_price_df_from_db(ticker)              │
   │          │               │     SELECT close_price FROM market_ticks        │
   │          │               │     (cached 10 s per ticker)                   │
   │          │               │                          │                      │
   │          │               │── build_intelligence_row(ticker, price_df, news, phase, persona)
   │          │               │                          │── QuantEngine.analyze()
   │          │               │                          │     5/20 EMA crossover
   │          │               │                          │     σ₅/σ₂₀ Dalio spike
   │          │               │                          │── SentimentEngine.analyze()
   │          │               │                          │     Simons crisis keyword ratio
   │          │               │                          │── PersonaAdapterEngine.analyze()
   │          │               │                          │     Buffett RSI margin-of-safety
   │          │               │                          │                      │
   │          │               │── _build_payload(risk_matrix, regime_cache, rng)
   │          │               │     portfolio_health, macro_regime,             │
   │          │               │     active_signals, network_nodes, risk_matrix  │
   │          │               │                          │                      │
   │◄─────────┤ data: {...}\n\n (EventSourceResponse)    │                      │
   │          └───────────────┤                          │                      │
   │                          │                          │                      │
   │── (browser disconnect) ──┤                          │                      │
   │                          │── _SSE_CONNECTION_COUNT -= 1                    │
   │                          │── if count == 0: task.cancel()                  │
   │                          │     → collector loop terminates                 │
```

### Key timing properties

| Property | Value | Rationale |
|----------|-------|-----------|
| SSE tick interval | 1 s | Smooth UI animation; GBM random walk keeps prices live between DB fetches |
| DB price cache TTL | 10 s | Avoids a DB query on every tick; fresh enough for 1 s display cadence |
| yfinance collector cycle | 60 s | API rate limit headroom; Yahoo Finance throttles at ~2 req/s per IP |
| Live collector lifetime | On-demand | Started on first SSE connect, cancelled when connection count reaches 0 — no idle polling |

---

## 4. OMNI Terminal — Agent Pipeline

```
POST /api/v1/intelligence/command
  {"query": "Should I reduce tech exposure?", "persona": "AGGRESSIVE"}

         │
         ▼
  intelligence_command()
         │
         ├── _run_agent_async(query, persona)            [primary path]
         │         │
         │         ├── _build_lc_agent()  [lazy, once]
         │         │     ChatGroq(llama-3.1-8b-instant)
         │         │     tools = [get_quant_intelligence, get_sentiment_intelligence]
         │         │     create_agent(llm, tools, system_prompt=_AGENT_SYSTEM_PROMPT)
         │         │
         │         ├── asyncio.to_thread(agent.invoke, {"messages": [query]})
         │         │         │
         │         │         ├── @tool get_quant_intelligence(ticker)
         │         │         │     QuantEngine + _compute_rsi → JSON
         │         │         │
         │         │         └── @tool get_sentiment_intelligence(ticker)
         │         │               SentimentEngine + _LIVE_NEWS_CACHE → JSON
         │         │
         │         ├── full engine pipeline → live risk_matrix (all tickers)
         │         └── assemble UI-contract response + omni_report briefing
         │
         └── _match_scenario(query)                      [fallback if agent fails]
               keyword groups → static scenario response
```

---

## 5. Multi-Engine Formula Reference

### QuantEngine — Ray Dalio Volatility Targeting

```
recent_vol  = σ(close[-5:])    # 5-day rolling std
baseline_vol = σ(close[-20:])  # 20-day rolling std

if recent_vol / baseline_vol > 1.5:
    vol_spike        = True
    momentum_score  -= 0.15
    status           = "WATCH"
```

Also computes: 5/20 EMA golden/dead cross, SMA5, SMA20.

### SentimentEngine — James Simons Regime Switching

```
CRISIS_KEYWORDS = {"inflation", "hawkish", "tightening", "crisis"}

crisis_count = count(tokens ∩ CRISIS_KEYWORDS)
crisis_ratio = crisis_count / total_tokens

if crisis_count >= 3 or crisis_ratio > 0.03:
    regime_switch = True
    → macro_regime.regime_name = "CRISIS_MODE"
```

Weighted positive/negative lexicon scoring also produces a `sentiment_score` ∈ [0, 1].

### PersonaAdapterEngine — Warren Buffett Margin of Safety

```
RSI(14) using Wilder smoothed average:
  avg_gain = EWM(gains, alpha=1/14)
  avg_loss = EWM(losses, alpha=1/14)
  RSI      = 100 − 100 / (1 + avg_gain / avg_loss)

if persona == "CONSERVATIVE" and signal == "BUY" and RSI >= 70:
    signal              = "HOLD"   # overbought lock
    margin_of_safety    = True
```

---

## 6. Zero-Cost AI Architecture

### Why paid APIs were removed

The v0.1.0 design principle is that core analytical output must be **deterministic and reproducible without any external API dependency**. The three engine layers (`src/engines.py`) are pure NumPy/Pandas — they produce identical results for identical input, regardless of network conditions or API quotas.

The LLM layer (`OMNI terminal`) is advisory, not authoritative. It synthesises structured engine output into natural-language briefings. This makes it safe to run against a free or local model without degrading the quality of the underlying signal.

### LLM routing

```
LLM_PROVIDER env var
       │
       ├── "groq"   (default)
       │     ChatGroq(model=GROQ_MODEL)
       │     Free tier: 14 400 req/day, 6 000 tokens/min
       │     No local GPU required
       │
       └── "ollama"
             ChatOllama(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL)
             Fully local, no API key, no rate limit
             Requires: ollama pull llama3.1:8b
```

### Embedding layer (Phase 3.2 pre-wire)

```python
# src/core/ — stub ready for Milvus RAG wiring
from langchain_huggingface import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)
# 384-dim vectors, ~22 MB model download, CPU-friendly
```

When Phase 3.2 (Milvus vector store) is implemented, news headlines are embedded at collection time and queried via approximate nearest-neighbour search. The agent's `get_sentiment_intelligence` tool will be augmented with a semantic retrieval step before lexicon scoring.

### Cost comparison

| Component | Paid (before v0.1.0) | Free (v0.1.0) |
|-----------|----------------------|---------------|
| LLM inference | Anthropic Claude API (~$3/M tokens) | Groq free tier or Ollama |
| Embeddings | — (not yet wired) | HuggingFace sentence-transformers |
| Market data | — | Yahoo Finance (yfinance) |
| Vector DB | — | Milvus Standalone (self-hosted) |
| Time-series DB | — | TimescaleDB (self-hosted) |
| **Monthly cost at 1 000 queries/day** | **~$90** | **$0** |

---

## 7. Infrastructure

### docker-compose.yml services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `timescaledb` | `timescale/timescaledb:latest-pg15` | 5432 | OHLCV hypertable, macro regimes |
| `milvus-standalone` | `milvusdb/milvus:v2.3.0` | 19530 | Vector store (Phase 3.2) |
| `minio` | `minio/minio` | 9000/9001 | Raw data artefacts (S3-compatible) |

### TimescaleDB schema

```sql
-- market_ticks: 7-day chunks, partitioned by timestamp
CREATE TABLE market_ticks (
    timestamp   TIMESTAMPTZ NOT NULL,
    ticker      TEXT        NOT NULL,
    open_price  NUMERIC,
    high_price  NUMERIC,
    low_price   NUMERIC,
    close_price NUMERIC,
    volume      BIGINT
);
SELECT create_hypertable('market_ticks', 'timestamp', chunk_time_interval => INTERVAL '7 days');

-- macro_regimes: latest regime state, polled at startup
CREATE TABLE macro_regimes (
    id               SERIAL PRIMARY KEY,
    regime_name      TEXT,
    market_phase     TEXT,
    confidence_score NUMERIC,
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 8. Observability

| Signal | Implementation | Endpoint |
|--------|---------------|---------|
| Structured logs | `src/core/logging/logger.py` — structlog + JSON | stdout |
| Metrics | Prometheus `CollectorRegistry` — `src/core/metrics/registry.py` | `/metrics` |
| Tracing | OpenTelemetry spans — `src/core/tracing/tracer.py` | OTLP HTTP exporter |
| Health | FastAPI `GET /health` | `/health` |

---

## 9. Testing

```
tests/
├── core/          Settings, exceptions, logging, common schemas
├── unit/
│   ├── domain/    Macro models, regime schema, signal engine, quant scoring
│   ├── services/  MacroService, RegimeService, SignalService end-to-end
│   ├── agent/     Context store, trimming, schemas
│   ├── api/       Startup seeder, trust DTO
│   ├── pipelines/ FRED normalizer, phase-1 foundation
│   └── mcp/       Tool handlers
└── evals/
    ├── schema_conformance/   API response schema validation
    ├── multi_turn/           Context carryover, bounded turn count
    ├── prompt_regression/    Prompt hash drift detection
    ├── provider_failure/     FRED timeout, partial data, typed failures
    └── tracing/              Trace ID propagation
```

**1 385 tests, 0 failures** on Python 3.12 (CI: pytest + coverage + mypy + ruff).
