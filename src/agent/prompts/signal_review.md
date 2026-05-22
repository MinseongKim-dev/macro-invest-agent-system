# Signal Review — Prompt Template

This file documents the **deterministic template** used by the agent layer to
produce signal review summaries.  It is not an LLM prompt in the current
implementation — the summary is produced by
`agent.formatting.summaries.format_signal_review_summary` without any model
calls.  The template is recorded here to make the output format explicit and to
serve as a reference for future LLM-assisted formatting.

---

## Output Template

```
Signal review for [{signal_ids}] (country={country}):
{signals_generated} signal(s) generated
(BUY={buy_signals}, SELL={sell_signals}, HOLD={hold_signals}).
Dominant signal direction: {dominant_direction}.
Engine run ID: {engine_run_id}.
Execution time: {execution_time_ms:.1f}ms.
```

### Field Descriptions

| Placeholder | Source | Notes |
|---|---|---|
| `{signal_ids}` | `SignalReviewRequest.signal_ids` | Comma-separated list of reviewed signal IDs |
| `{country}` | `SignalReviewRequest.country` | ISO 3166-1 alpha-2 code (e.g. `US`) |
| `{signals_generated}` | `RunSignalEngineResponse.signals_generated` | Total signals produced by the engine |
| `{buy_signals}` | `RunSignalEngineResponse.buy_signals` | Count of BUY signals |
| `{sell_signals}` | `RunSignalEngineResponse.sell_signals` | Count of SELL signals |
| `{hold_signals}` | `RunSignalEngineResponse.hold_signals` | Count of HOLD signals |
| `{dominant_direction}` | Computed | `BUY`, `SELL`, `HOLD`, or `none`; ties broken BUY > SELL > HOLD |
| `{engine_run_id}` | `RunSignalEngineResponse.engine_run_id` | Unique ID of the engine run |
| `{execution_time_ms}` | `RunSignalEngineResponse.execution_time_ms` | Wall-clock time in milliseconds |

---

## Tone and Constraints

- **Conservative**: the summary describes what the engine produced — it does
  not interpret or endorse any signal direction.
- **Non-prescriptive**: no investment advice or recommendations are implied.
- **Deterministic**: given the same inputs the output is always identical.

---

## Future Extension (LangChain / LangGraph)

When an LLM-backed formatting stage is introduced, this template can be
converted into a proper prompt template (e.g. a LangChain `ChatPromptTemplate`)
that receives the structured fields above as variables.  The agent runtime
adapter in `agent/runtime/agent_runtime.py` is the intended integration point
for that change.

The deterministic formatter should remain as a fallback so the system can run
without an LLM in unit tests and CI.
