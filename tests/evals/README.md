# Evals — Structured Evaluation Suite

This directory contains a structured evaluation suite that verifies
end-to-end correctness, schema safety, and regression stability of the
macro-invest agent system.

---

## How to Run

```bash
# Run all tests (unit tests + evals)
pytest

# Run only evals
pytest evals/

# Run a specific sub-suite
pytest evals/multi_turn/ -v
pytest evals/comparison/ -v
pytest evals/provider_failure/ -v
pytest evals/schema_conformance/ -v
pytest evals/prompt_regression/ -v

# Run with coverage
pytest evals/ --cov=agent --cov=adapters --cov=domain --cov-report=term-missing
```

---

## Sub-suite Overview

### `multi_turn/` — Conversation context across turns

| File | What it verifies |
|---|---|
| `test_context_carryover.py` | Country established in turn 1 appears in context hint after turn 2 |
| `test_context_isolation.py` | Two sessions with different `session_id` values never share context |
| `test_bounded_turns.py` | Context length never grows beyond `max_context_turns` |

### `comparison/` — Snapshot comparison round-trips

| File | What it verifies |
|---|---|
| `test_comparison_happy.py` | change-detected and no-change full round-trips return `success=True`, correct counts, non-empty summary |
| `test_comparison_no_change.py` | All prior values identical → `changed_count == 0` |
| `test_comparison_prior_missing.py` | Empty `prior_features` → `success=False`, error references prior label |

### `provider_failure/` — Data provider failure paths

| File | What it verifies |
|---|---|
| `test_fred_failure.py` | `FredMacroDataSource.fetch_raw` raising `RuntimeError("FRED unavailable")` surfaces through ingestion service |
| `test_timeout.py` | `TimeoutError` at HTTP layer is wrapped as `RuntimeError` with actionable message |
| `test_partial_data.py` | FRED returning 3 of 5 indicators → `FeatureSnapshot.features_count == 3` |

### `schema_conformance/` — Schema regression

| File | What it verifies |
|---|---|
| `test_response_schemas.py` | Every `AgentResponse` subclass: extra fields rejected, `success=False` constructs, `model_dump()` round-trip |
| `test_request_schemas.py` | Every `AgentRequest` subclass: required fields, `model_dump()` round-trip, extra fields rejected |

### `prompt_regression/` — Prompt template regression

| File | What it verifies |
|---|---|
| `test_prompt_templates.py` | Each `render_*` function produces output containing expected substrings and no hallucinated fields |
| `test_context_hint_isolation.py` | Context hint appears only in the system message; rendered human message is unchanged regardless of hint content |

---

## How to Add New Scenarios

1. Pick the most appropriate sub-suite directory.
2. Add a new `test_*.py` file (or add a test class to an existing file).
3. Use fixtures from `evals/conftest.py` (`session_id`, `make_service`, `make_lc_runtime`) to avoid boilerplate.
4. Follow the existing naming conventions: `TestXxx` class with `test_` methods.
5. Mark all async tests with `@pytest.mark.asyncio` (inherited from `asyncio_mode = "auto"`).

---

## Design Principles

* **No new production code**: evals use only existing runtime/service/domain APIs.
* **Fixture-backed**: no live HTTP calls; external providers are mocked.
* **Deterministic**: every eval produces the same pass/fail result on repeated runs.
* **Isolated**: each test creates its own runtime/service instances; no shared state.
