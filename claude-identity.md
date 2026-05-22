# Aleph-One — Claude Identity & Operational Manual

> **READ THIS BEFORE EVERY TASK. NO EXCEPTIONS.**
> This is the single source of truth for Claude's role, architecture rules, coding standards, and API contracts on this project.

---

## 1. Role & Context Boundaries

- **Role:** Senior Backend & DevOps Engineer for *Aleph-One* — a J.A.R.V.I.S.-style polymorphic financial multi-engine synchronizer.
- **Legacy Quarantine:** NEVER scan, open, index, or reference any file inside `legacy/`. If past logic is needed, wait for the user to paste it into chat explicitly.
- **Incremental Rule:** Do not modify multiple core files at once. State the planned changes, await confirmation, then execute file by file.
- **Token Efficiency:** Keep explanations minimal. Write perfect production-grade code. This document provides all implicit guidelines — do not re-ask what is already defined here.

---

## 2. Tri-File Core Architecture (Anti-Bloat Law)

All backend logic lives in exactly these four files. Creating sub-files or sub-directories is **forbidden** unless the user explicitly overrides this rule.

| File | Sole Responsibility |
|------|---------------------|
| `docker-compose.yml` | Infrastructure only — TimescaleDB (PG15), Milvus Standalone |
| `src/database.py` | DB connection, DDL (hypertables), seed data |
| `src/engines.py` | QuantEngine, SentimentEngine, PersonaAdapterEngine under BaseEngine ABC |
| `src/main.py` | FastAPI routes, SSE/polling streams, LangChain orchestration |

**Current file state (do not re-create):**
- `src/database.py` — `DatabaseConfig`, `_PoolManager` singleton, `get_pool()`, `get_connection()` (ctx-mgr, auto-return), `init_db()` (market_ticks hypertable 7-day chunks + macro_regimes, idempotent), `seed_mock_data()` (pandas GBM OHLCV COPY bulk-insert + dummy regimes for AAPL/MSFT)
- `src/engines.py` — `BaseEngine` ABC, `QuantEngine` (5/20 EMA crossover + σ), `SentimentEngine` (growth/surpass/bullish vs drag/drop/bearish keyword rule-base), `PersonaAdapterEngine` (AGGRESSIVE/BALANCED/CONSERVATIVE → BUY/HOLD/SELL + confidence), `build_intelligence_row()` orchestration helper. Universe: AAPL · MSFT · TSLA · 005930 · 000660
- `src/main.py` — CORS + lifespan (init_db → seed → history → regime cache), `GET /api/v1/intelligence/stream` (SSE EventSourceResponse 1s, full UI contract + random walk), `POST /api/v1/intelligence/command` (OMNI:// terminal, 3 keyword scenarios → JARVIS report + twisted network_nodes)

---

## 3. Technology Stack

| Layer | Stack |
|-------|-------|
| Time-series DB | TimescaleDB (PostgreSQL 15) — `create_hypertable` mandatory on all time-indexed tables |
| Vector DB | Milvus Standalone v2.3 — for embedding news, reports, Fed statements |
| Orchestration | LangChain agents — parse `OMNI://` terminal → execute tools |
| API | FastAPI + SSE — high-frequency streaming to Next.js UI cards |
| Frontend | Next.js 14 + Tailwind — `apps/frontend/` — never modified from backend tasks |
| Python env | psycopg v3 (`psycopg[binary]`), `psycopg-pool>=3.2`, pandas, numpy, uvicorn |

---

## 4. UI-Driven API Contract (Immutable Schema)

Every payload from `/api/v1/intelligence` must match this shape exactly.
**Do not rename keys, change casing, or restructure top-level fields.**

```json
{
  "timestamp": "<ISO-8601>",
  "status": "LIVE | SYNCING | ERROR",
  "portfolio_health": {
    "score": 0,
    "source": "MARKET_DATA"
  },
  "macro_regime": {
    "regime_name": "POLICY_TIGHTENING",
    "market_phase": "LATE_CYCLE",
    "confidence_score": 1.00
  },
  "active_signals": [
    { "action": "HOLD | BUY | SELL", "strategy": "<string>", "probability": 0.48 }
  ],
  "intelligence_synthesis": {
    "assets_count": 5,
    "vector_mode": "AI-WEIGHTED VECTORS",
    "network_nodes": [
      { "id": "AAPL", "x": 0.15, "y": -0.32, "z": 0.45, "group": "TECH" }
    ],
    "risk_matrix": [
      {
        "ticker": "AAPL",
        "momentum":  "WATCH | STABLE",
        "regime":    "WATCH | STABLE",
        "rates":     "WATCH | STABLE",
        "sentiment": "WATCH | STABLE",
        "sig_score": "BUY | HOLD | SELL"
      }
    ]
  }
}
```

Frontend UI card → backend source mapping:

| UI Card | Endpoint / Source | Key Fields |
|---------|-------------------|------------|
| Portfolio Health arc | `/api/v1/intelligence` | `portfolio_health.score` |
| Macro Regime badge | `/api/v1/regimes/latest` | `macro_regime.*` |
| Live Portfolio sparklines | `/api/mock/stream/market` (SSE) | `prices`, `portfolio_value` |
| Risk · Opportunity Matrix | `intelligence_synthesis.risk_matrix` | per-ticker status fields |
| 3D Network sphere | `intelligence_synthesis.network_nodes` | `id`, `x`, `y`, `z`, `group` |
| Global Intel ticker | `/api/events/recent` | `title`, `event_type` |

---

## 5. Coding Standards (Non-Negotiable)

- **Typing:** Every function/method must have Python 3.10+ type hints. Use `from __future__ import annotations`.
- **Resilience:** All DB queries, external API fetches, and LLM calls must be in `try/except`. Log before re-raising. `src/main.py` must never crash — return `{"status": "ERROR", ...}` instead.
- **Performance:** `QuantEngine` must use vectorised NumPy/Pandas operations. No raw Python loops over time-series data.
- **Logging:** Standard `logging` module only. No `print()` in production paths.
- **Ruff-clean:** No violations for `E`, `W`, `F`, `I`, `B`, `C4`, `UP`, `SIM`, `ANN`, `N`.

---

## 6. Task Execution Protocol

1. Re-read this file.
2. Confirm the task fits Tri-File Architecture — if a fourth file is needed, ask the user first.
3. Check if the change touches a UI contract (Section 4) — if yes, verify schema compatibility.
4. State the exact files that will change before writing any code.
5. Execute with minimum blast radius.
6. Commit with a descriptive message after every milestone.

---

## 7. Phase Milestones

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 2.1 | SSE stream → UI component bindings (useAlephStream hook, StatusBar sync dot, AlphaPanel/RiskMatrix stream props, page.tsx orchestration) | [X] |
| Phase 2.2 | Polymorphic multi-engine upgrade + real DB price data wiring (SMA golden/dead cross, weighted sentiment lexicon, per-persona thresholds; market_ticks → engines → SSE payload) | [X] |
| Phase 3.1 | LLM / LangChain orchestration for OMNI command terminal | [ ] |
| Phase 3.2 | Milvus vector store wiring (news embeddings, semantic search) | [ ] |
