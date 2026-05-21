# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **IMPORTANT:** Before every task, read `claude-identity.md` in the project root.
> It defines system identity, the Tri-File Core Architecture, legacy quarantine rules,
> UI data contracts, and the task execution protocol that must be followed without exception.

## Project Identity

This project is a multi-engine economic and market analysis system for investment support.

The system ingests macroeconomic data, market data, and event metadata, normalizes them into structured forms, and runs multiple internal analysis engines to produce states, scores, regime classifications, confidence assessments, change summaries, and human-readable explanations.

Important:
- "Multi-engine" means internal analytical engines with separated responsibilities.
- It does NOT mean multiple external AI agents.
- This project is an investment support system, not an autonomous trading bot.

---

## Source of Truth Documents

Always treat the following documents as project context before making changes:

- `docs/project_brief.md`
- `docs/architecture.md`
- `docs/domain_dictionary.md`
- `docs/decisions.md`
- `docs/current_state.md`

If terminology, architecture, or project intent is unclear:
- consult these documents first
- do not silently redefine terms
- do not invent missing domain meanings

When there is a conflict:
1. `docs/decisions.md`
2. `docs/domain_dictionary.md`
3. `docs/architecture.md`
4. `docs/project_brief.md`
5. current task prompt

---

## Core Working Principles

### 1. Think Before Coding

Do not assume silently.

Rules:
- State important assumptions explicitly.
- If ambiguity affects domain meaning, architecture, or behavior, ask before implementing.
- If there are multiple reasonable interpretations, present 2-3 options briefly instead of choosing silently.
- Separate facts, assumptions, and recommendations.
- Push back when a simpler or safer approach is better.
- If confused, stop and name the confusion clearly.

Examples:
- If "confidence" could mean data quality or prediction confidence, ask which one is intended.
- If "regime" is not defined for the current task, do not invent a classification scheme without confirmation.
- If a task seems to require architecture changes outside the requested scope, say so explicitly before proceeding.

---

### 2. Simplicity First

Prefer the minimum code and structure that correctly solves the task.

Rules:
- Do not add features that were not requested.
- Do not add flexibility, configurability, or extensibility unless explicitly needed now.
- Do not create abstractions for single-use logic.
- Do not introduce plugin systems, registries, orchestration layers, or strategy hierarchies prematurely.
- Do not add speculative error handling for impossible scenarios.
- If 200 lines can be 50 lines without losing clarity, prefer 50.
- Prefer explicit code over clever code.
- Prefer testable functions over framework-heavy indirection.

Test:
- Would a strong senior engineer say this is overcomplicated for the current scope?
- If yes, simplify.

---

### 3. Surgical Changes

Touch only what is required for the task.

Rules:
- Do not modify unrelated files, comments, naming, formatting, or structure.
- Do not refactor adjacent code unless the task explicitly asks for it.
- Match the existing local style unless doing so would create a correctness problem.
- If you notice unrelated dead code, mention it separately but do not delete it unless asked.
- Remove only the imports, variables, functions, or code paths made unused by your own changes.
- Do not silently rewrite or delete domain comments you do not fully understand.
- Every changed line must trace directly to the task.

When editing:
- preserve existing intent
- minimize blast radius
- avoid side effects outside the requested scope

---

### 4. Goal-Driven Execution

Convert vague requests into verifiable goals.

Rules:
- Before implementing, define the goal briefly.
- For multi-step work, provide a short plan with verification points.
- Prefer tasks with explicit done criteria.
- Where appropriate, use tests or checks to verify behavior.
- If success cannot be verified, say what remains uncertain.

Examples:
- Instead of "add validation", think "add invalid-input tests, then implement validation until tests pass."
- Instead of "fix bug", think "reproduce bug, add test, implement fix, verify no regression."
- Instead of "write architecture doc", think "produce copy-paste-ready markdown with required sections."

Suggested plan format:
1. [step]
   - verify: [check]
2. [step]
   - verify: [check]
3. [step]
   - verify: [check]

---

### 5. Contract Over Cleverness

Prefer explicit contracts over smart abstractions.

Rules:
- Every engine should have explicit input and output contracts.
- Prefer clear types/interfaces/schemas over implicit coupling.
- Define boundaries before adding helpers.
- Versioned or stable structures are better than ad hoc dynamic shapes.
- Do not hide domain logic behind vague generic utilities.
- If an engine has failure behavior, make it explicit.

For each engine, aim to define:
- purpose
- inputs
- outputs
- dependencies
- failure behavior
- assumptions

---

### 6. Truth Before Narrative

Structured truth comes before explanation.

Rules:
- Explanation is a rendering layer, not a source of truth.
- Do not use generated prose as the primary representation of system state.
- Compute structured outputs first, then explain them.
- Narrative must be derived from structured results, not the other way around.
- If structured truth is unclear, do not compensate with polished wording.

Priority:
1. normalized data
2. computed state
3. derived interpretation
4. rendered explanation

---

## Architecture Rules

Follow these rules unless the task explicitly changes architecture.

- Keep engine boundaries explicit.
- Engines should have single responsibility.
- Separate normalization, scoring, classification, confidence, change detection, synthesis, and explanation where practical.
- Do not merge truth computation with presentation concerns.
- Core analysis logic should not depend on UI-specific models.
- Explanation should consume structured outputs from upstream engines.
- Avoid introducing microservices or distributed boundaries early.
- Prefer a modular monolith until complexity justifies more.
- Keep history-aware computations distinct from single-snapshot computations when possible.
- Favor deterministic logic in core analytical paths.
- Do not add LLM dependence to core deterministic computations unless explicitly requested.

---

## Documentation Rules

When writing or updating documents:

- Produce copy-paste-ready Markdown.
- Be concrete, not aspirational.
- Prefer short sections with clear headings.
- Use project terminology from `docs/domain_dictionary.md`.
- Keep architecture docs implementation-aware, not marketing-oriented.
- Distinguish current reality from future ideas.
- If including examples, make them realistic and domain-consistent.
- Do not bloat docs with generic best-practice filler.

For project docs:
- `project_brief.md` should define what the system is and is not.
- `architecture.md` should define layers, engines, responsibilities, and flow.
- `domain_dictionary.md` should stabilize terms.
- `decisions.md` should record explicit decisions and rationale.
- `current_state.md` should track current progress and next steps.

---

## Coding Rules

General coding rules:

- Prefer clarity over cleverness.
- Prefer pure functions where possible.
- Keep domain logic separated from IO and presentation logic.
- Use explicit names instead of short cryptic names.
- Favor small, composable units over deep inheritance or heavy indirection.
- Minimize hidden side effects.
- Keep functions focused and testable.
- Avoid premature optimization.

When writing types/interfaces:
- make domain meaning obvious
- avoid vague field names like `data`, `value`, `info` unless scoped clearly
- model business meaning explicitly

When modifying code:
- preserve compatibility unless breaking changes are explicitly requested
- call out breaking changes if unavoidable
- do not silently change semantics

---

## Task Execution Rules

For each task:

1. Restate the task briefly.
2. Name assumptions if any.
3. If needed, provide a short plan.
4. Execute only the requested scope.
5. Verify against explicit success criteria.
6. Summarize changes briefly.

When a task is too large:
- decompose it into smaller units
- suggest a safer execution order
- do not attempt a massive rewrite unless explicitly requested

Default task preference:
- document-first
- interface/type-first
- tests/checks where useful
- implementation after contracts are clear

For ambiguous requests:
- ask concise clarifying questions
- or provide 2-3 scoped options with tradeoffs

---

## Domain-Specific Rules

This project has domain-specific constraints.

### Terminology
- Use terminology from `docs/domain_dictionary.md`.
- Do not silently redefine terms such as:
  - snapshot
  - score set
  - regime
  - confidence
  - conflict
  - catalyst
  - synthesis
  - explanation

### Interpretation
- Do not present financial interpretation as certainty when it is heuristic.
- Distinguish observed data from inferred interpretation.
- Distinguish current state from forecast or scenario.
- Distinguish confidence in data quality from confidence in prediction.

### Scope
- MVP is focused on macro + market interpretation for investment support.
- Do not expand scope into full auto-trading, agent swarms, or broad cross-asset intelligence platforms unless explicitly requested.
- Do not broaden the system to every asset class by default.

### Safety
- Prefer auditable, inspectable logic.
- Preserve traceability from source data to derived outputs.
- If a derived output cannot be explained from upstream state, flag that issue.

---

## Non-Goals

Unless explicitly requested, do not do the following:

- turn the system into an autonomous trading bot
- introduce LLMs into core deterministic scoring/classification paths
- redesign the whole architecture for a local task
- replace simple structures with enterprise patterns
- broaden the MVP to all markets and asset classes
- create speculative abstractions for future flexibility
- clean up unrelated legacy or dead code
- rewrite comments or docs outside the requested scope
- silently rename domain concepts

---

## Default Output Preferences

Unless the user asks otherwise:

### For code tasks
- provide code first
- keep explanation brief
- mention assumptions or risks separately
- mention changed files explicitly if relevant

### For document tasks
- provide copy-paste-ready Markdown
- prefer practical structure over theory
- keep wording precise and non-promotional

### For architecture tasks
- list changed assumptions
- state tradeoffs briefly
- prefer diagrams in text form only if useful

### For planning tasks
- give a short prioritized list
- prefer tasks that can be completed in 30-90 minutes
- avoid giant undifferentiated backlogs

---

## Preferred Decision Heuristics

When multiple solutions exist, prefer the one that is:

1. simpler
2. more explicit
3. easier to test
4. easier to trace
5. more aligned with current docs
6. lower blast radius
7. easier to explain to a future maintainer

If a more complex solution is chosen, explain why the simpler one is insufficient.

---

## If You Are Unsure

Do this in order:

1. check `docs/` source-of-truth documents
2. identify the ambiguity precisely
3. state assumptions explicitly
4. ask a targeted question or present scoped options
5. do not guess on domain-critical meaning

---

## Reminder

The goal is not to sound smart.
The goal is to produce correct, minimal, traceable, maintainable work.

Small, explicit, verifiable progress is preferred over large speculative output.
