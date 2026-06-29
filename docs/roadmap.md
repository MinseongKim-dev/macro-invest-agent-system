# Roadmap

> See also: `CLAUDE.md` → **PRD 로드맵** for the product-level Phase A/B/D/E roadmap
> from the 2026-06-26 PRD. The engineering chapter roadmap below covers the
> backend domain layer; the PRD roadmap covers the product surface.

## Phase 1 — Macro Data Foundation ✅

Objective: build reliable ingestion + normalization for priority macro indicators.

Primary deliverables:

- indicator catalog
- source mapping
- raw payload handling
- normalized observation schema
- ingestion run tracking
- freshness baseline

## Phase 2 — Macro Snapshot Layer ✅

- Snapshot contract
- Deterministic category-state derivation
- Snapshot build/persist
- Current-vs-previous snapshot comparison

## Phase 3 — Macro Regime Engine ✅ (baseline complete)

- Regime schema/contract
- Snapshot-to-regime deterministic mapping
- Regime confidence/degraded handling
- Regime transition comparison
- Regime persistence and read API contract
- Canonical docs index: `docs/regime_engine.md`

---

## Active Workstream — Multi-Engine Analysis Hub

**Current phase focus: Phase 3 completion → Phase 4 bridge**

This workstream extends Phase 3 with the signal and explanation layers that
complete the analyst-facing chain:

```
Snapshot → Regime → Signals → Explanations → API/UI
```

### Phase 3 bridge work (in progress)

- **Startup regime seeder** — synthetic bootstrap data for dev/test;
  idempotent, metadata-stamped, non-blocking on failure.
  See `docs/legacy_surface_status.md` for bootstrap data policy.
- **Regime-grounded signal rules** — deterministic `RegimeLabel → signals`
  mapping with structured `asset_class`, `signal_direction`, `signal_strength`,
  `signal_confidence`, `supporting_drivers`, `conflicting_drivers`.
- **Structured narrative explanations** — analyst-facing `summary`,
  `rationale_points`, `caveats`, `data_quality_notes`, `regime_context`
  surfaced via `GET /api/explanations/regime/latest`.
- **Regime backbone hardening** — `warnings` field on `MacroRegime` domain
  model; `derive_regime_warnings()` helper; `status` and `warnings` on
  `RegimeLatestResponse`; `current_rationale_summary`, `warnings`, `is_seeded`
  on `RegimeCompareResponse`.  See contract notes below.
- **Signal Engine v2 alignment** — `is_degraded` and `caveat` on `SignalOutput`
  and `SignalSummaryDTO`; regime degraded state propagated to every signal;
  `regime_label`, `as_of_date`, `is_regime_grounded`, `status` on
  `SignalsLatestResponse`.  Signal `status` values: `success`, `degraded`,
  `fallback`, `empty`.
- **Product surface & UX contract alignment** — explicit `status` fields on
  regime and signal responses; `_compute_regime_status()` helper; cross-endpoint
  contract tests.  See `tests/unit/api/test_product_surface_contract.py`.

### API/UI contract notes

#### Regime response `status` field
`GET /api/regimes/latest` now includes a top-level `status` field:
- `"success"` — healthy, non-synthetic, fresh data
- `"bootstrap"` — regime built from synthetic startup seed data
- `"stale"` — underlying data older than expected freshness window
- `"degraded"` — partial indicators, low confidence, or mixed/unclear regime

#### Signal response `status` field
`GET /api/signals/latest` now includes `status`, `is_regime_grounded`,
`regime_label`, and `as_of_date`:
- `"success"` — healthy regime-grounded signals
- `"degraded"` — regime-grounded but regime is degraded/stale/low-confidence
- `"fallback"` — no persisted regime, snapshot-based fallback engine used
- `"empty"` — no signals generated

#### Signal degraded propagation
When the grounding regime is degraded/stale/bootstrap, every derived signal
receives `is_degraded=True` and a `caveat` string explaining the specific
condition.  Caveat priority order:
1. bootstrap/seeded
2. mixed/unclear (non-directional)
3. stale freshness
4. unknown freshness
5. missing/source-unavailable degraded status
6. partial degraded status
7. low confidence

### Upcoming Phase 4 work

Phase 4 = **Multi-Engine Analysis Hub** (not yet started):

- Quant Scoring Engine
- Cross-Asset Signal Engine
- Risk / Conflict Engine
- AI Explanation Engine (LLM-backed)
- Ensemble / Consensus Engine

Phase details should be refined in backlog tasks, not duplicated in README.

---

## Chapter Roadmap (Chapters 6–12)

### Chapter 6 — Alerting & Monitoring Intelligence ✅ (complete)

Turns change detection into proactive analyst notification.

- Configurable alert-rule engine over `RegimeDelta` results and regime transitions
- Alert types: `threshold_breach`, `regime_transition`, `signal_reversal`,
  `staleness_warning`, `trust_degradation`
- Structured `AlertEvent` records with `trigger_type`, `severity`,
  `source_regime`, `target_regime`, `indicator_type`, `context_snapshot_id`
- Alert history store queryable by type, severity, country, and time range
- Read-only alert API: `GET /api/alerts/recent`, `GET /api/alerts/{id}`
- Analyst-facing acknowledgement/snooze: `PATCH /api/alerts/{id}/acknowledge`,
  `PATCH /api/alerts/{id}/snooze`

### Chapter 7 — External Event & Catalyst Intelligence (Ingestion Layer) ✅ (complete)

Introduces the external event ingestion layer with normalized, structured
event facts distinct from raw news aggregation.

- `NormalizedExternalEvent` domain model: `event_type`, `source`, `occurred_at`,
  `normalized_at`, `raw_payload_ref`, `structured_fields`
- `ExternalEventType`, `ExternalEventFreshness`, `SourceReliabilityTier`,
  `ExternalEventStatus` enums
- Normalization helpers: `compute_event_freshness()`, source reliability mapping
- `InMemoryEventStore` repository with full filtering support
- Event Impact Adapter producing `ExternalEventImpact` with explanation evidence,
  caveat notes, conflict contributors, and confidence downgrade hints
- Read API: `GET /api/events/recent`, `GET /api/events/{id}`

### Chapter 8 — Catalyst-Aware Interpretation ✅ (complete)

Attributes observed `FeatureDelta` records to candidate external event causes
using deterministic, rule-based matching.

- `AttributionRule` domain model: `(event_type, indicator_type, max_lag_days)`
- `AttributionConfidence` enum: `high` / `medium` / `low` / `unattributed`
- Deterministic `attribute_delta()` — single-delta attribution with exact-rule
  matching + heuristic fallback map
- `run_attribution()` — batch attribution for all changing deltas in a snapshot
  comparison
- `ChangeAttribution` read model with `CatalystContext` block for downstream
  embedding in explanation DTOs
- `AttributionRunResult` container with counts and `summary_context()` helper
- 9 built-in rules covering CPI, GDP, unemployment, retail sales, PMI, 10Y yield,
  and central bank rate decisions
- Advisory attribution adds context to explanations; does not override
  deterministic regime computation

### Chapter 9 — Fundamental Intelligence Layer

Introduces sector-level fundamental data distinct from macro indicators,
bridging macro signals to investment-relevant fundamentals.

- `FundamentalFact` domain model: `fact_type`, `value`, `period`, `source`,
  `observed_at`
- Sector-level aggregate views (S&P 500 sector earnings growth, consensus
  revision direction)
- Fundamentals ingestion pipeline separate from macro ingestion
- `FundamentalSnapshot` read model per sector per period
- Read API: `GET /api/fundamentals/sectors/latest`,
  `GET /api/fundamentals/{ticker}/latest`

### Chapter 10 — Scenario / What-If Engine

Deterministic parameterised exploration of the existing analytical model —
not speculative forecasting.

- `ScenarioSpec` model: named indicator overrides applied to a base snapshot
- `ScenarioResult` read model: derived regime label, signal outputs,
  conflict state, delta-vs-baseline
- Historical scenario lookup: "find periods where indicator X was in range Y"
- Explicit `is_hypothetical=True` labelling throughout the DTO chain

### Chapter 11 — Portfolio & Allocation Intelligence

Bridges macro signals to structured allocation guidance.

- `RegimeAllocationMatrix`: regime label → asset class positioning ranges
- `PortfolioOverlay` read model with signal alignment score
- Conflict/divergence surface: flags where current signals diverge from the
  historical matrix
- Read API: `GET /api/portfolio/overlay/latest`

### Chapter 12 — LLM-Assisted Narrative / Research Copilot

LLM-assisted communication of the structured analytical backbone — the
copilot summarises what the platform knows, it does not invent.

- `NarrativeRequest` schema grounded on specific snapshot/run/scenario IDs
- `NarrativeDraft` output with source-referenced sections
- Every LLM sentence traceable to a structured fact; non-groundable claims
  suppressed or marked `uncertain`
- Multi-turn analyst dialog resolved against the same grounded fact set
- Explicit separation of LLM narrative from deterministic computation

---

## Known Limitations / Deferred Work

These items are intentionally out of scope for the current v1 delivery and
are tracked here to prevent silent omission.  Each item is linked to a
future phase where it will be addressed.

### Phase 4–5
- **Dynamic signal confidence** — `signal_confidence` is currently hard-coded at
  the rule layer.  In a later phase it should be dynamically adjusted using regime
  confidence, indicator recency/freshness, missing/degraded inputs, and quant
  scoring outputs.
- **Cross-asset conflict resolution** — under `GOLDILOCKS`, equities may be `BUY`
  while bonds remain `HOLD`.  A dedicated Conflict / Ensemble Engine is needed to
  reconcile multi-asset disagreements and downgrade conviction where signals conflict.
- **Richer signal rationale** — current rationale is template-based.  A richer
  signal-level narrative that reflects real-time indicator deltas is deferred to
  the Quant Scoring Engine phase.

### Phase 5
- **Explanation persistence** — explanation generation remains in-memory in v1.
  Follow-up work should add persistence for auditability, reproducibility, and
  historical explanation retrieval.
- **Better narrative quality** — narrative templates will be expanded and improved
  as more regime/signal data becomes available.

### Phase 5–6
- **LLM-backed explanation** — current explanation logic is deterministic and
  template-based.  Replacing or augmenting this with an LLM-backed AI Explanation
  Engine is future work.
- **Conversational explanation** — multi-turn analyst dialog is a Phase 6+
  capability.

### Phase 7
- **Production-safe seeding controls** — startup seeding is controlled by the
  `SEED_ON_STARTUP` environment variable (default `True`).  A full feature-flag
  system with per-environment defaults, audit trail, and remote toggle is Phase 7
  work.
- **Persistence and audit trail** — the in-memory regime/snapshot stores must be
  backed by a durable repository before production deployment.
