# Macro Snapshot Summary — Prompt Template

This file documents the **deterministic template** used by the agent layer to
produce macro snapshot summaries.  It is not an LLM prompt in the current
implementation — the summary is produced by
`agent.formatting.summaries.format_snapshot_summary` without any model calls.
The template is recorded here to make the output format explicit and to serve
as a reference for future LLM-assisted formatting.

---

## Output Template

```
Macro snapshot for country={country}:
{features_count} feature(s) available as of {snapshot_timestamp}.
```

### Field Descriptions

| Placeholder | Source | Notes |
|---|---|---|
| `{country}` | `MacroSnapshotSummaryRequest.country` | ISO 3166-1 alpha-2 code (e.g. `US`) |
| `{features_count}` | `GetMacroSnapshotResponse.features_count` | Number of macro features in the snapshot |
| `{snapshot_timestamp}` | `GetMacroSnapshotResponse.snapshot_timestamp` | ISO 8601 datetime string; `"unknown"` when `None` |

---

## Tone and Constraints

- **Factual**: the summary reports what data is available — it does not
  interpret macro conditions or recommend actions.
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
