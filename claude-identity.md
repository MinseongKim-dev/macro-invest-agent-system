# Aleph-One — Claude Identity & Execution Rules

> This file is the single source of truth for Claude's operating identity on this project.
> It must be read and respected before every task, without exception.

---

## 1. System Identity

| Field   | Value |
|---------|-------|
| Name    | **Aleph-One (알레프 원)** |
| Concept | J.A.R.V.I.S.-style polymorphic multi-engine financial intelligence synchronizer |
| Goal    | Analyze macro-global market data and deliver hyper-personalised investment intelligence via a cinematic spatial interface |

---

## 2. Tri-File Core Architecture (Anti-Bloat Law)

Backend logic must live in exactly these files. Do not split into sub-files unless explicitly commanded.

| File | Responsibility |
|------|---------------|
| `docker-compose.yml` | Infrastructure only — TimescaleDB, Milvus |
| `src/database.py` | DB connection, schema DDL (hypertables), seed data |
| `src/engines.py` | Multi-engine core — QuantEngine, SentimentEngine, PersonaAdapterEngine |
| `src/main.py` | FastAPI routes, SSE streams, orchestration entry point |

**Violation:** Creating `src/database/connection.py`, `src/engines/quant.py`, or any other split is forbidden unless the user explicitly overrides this rule.

---

## 3. Technology Constraints

| Layer | Stack | Notes |
|-------|-------|-------|
| Time-series storage | TimescaleDB (PostgreSQL 15) | `create_hypertable` mandatory on all time-indexed tables |
| Context / vector storage | Milvus Standalone v2.3 | For embedding news, reports, Fed statements |
| Orchestration & RAG | LangChain agents | Parse `OMNI://` terminal commands, execute tools |
| API | FastAPI + SSE | High-frequency mock-infused streaming to Next.js cards |
| Frontend | Next.js 14 + Tailwind CSS | Lives in `apps/frontend/` — do not touch from backend tasks |

---

## 4. Legacy Quarantine

`legacy/` contains past experiments and is permanently frozen.

- **Never** read, scan, import, or reference any file inside `legacy/`.
- **Never** move active `src/` or `apps/` code into `legacy/` without explicit instruction.
- If a task seems to require legacy code, ask the user instead of reading it.

---

## 5. Design-Driven Development

The backend unconditionally adapts to the frontend UI schema.

Frontend visual cards and their required data contracts:

| UI Card | Backend Source | Key Fields |
|---------|---------------|------------|
| Portfolio Health | `PersonaAdapterEngine` result | `signal`, `confidence`, `persona` |
| Macro Regime | `GET /api/v1/regimes/latest` | `regime_name`, `market_phase`, `confidence_score` |
| Live Portfolio / Sparklines | `GET /api/mock/stream/market` (SSE) | `prices`, `portfolio_value` |
| Risk · Opportunity Matrix | `GET /api/signals/latest` + engine scores | Per-ticker scores 0–1 |
| Global Intel Stream | `GET /api/events/recent` | Event `title`, `event_type`, region |

When adding or modifying endpoints, verify the response shape matches what the frontend component consumes.

---

## 6. Coding Standards (Non-Negotiable)

Every Python file in `src/` must satisfy all of the following:

- **Type hints** on every function argument and return value (`from __future__ import annotations`)
- **Logging** via the `logging` module — no `print()` in production paths
- **Error handling** — explicit `try/except` with typed exceptions; log before re-raising
- **OOP patterns** — logic lives in classes with clear single responsibilities
- **No dead imports** — remove any import not used after changes
- Ruff-clean: no `E501`, `B008`, `ANN`, `N`, `SIM`, `UP` violations

---

## 7. Task Execution Protocol

Before starting any task:

1. Re-read this file (`claude-identity.md`).
2. Confirm the task fits within the Tri-File Architecture — if it wants a fourth file, ask the user.
3. Check whether the change touches a UI data contract (Section 5) — if yes, verify frontend compatibility.
4. Execute with minimum blast radius: change only what the task requires.
5. Commit with a descriptive message after every meaningful milestone.
