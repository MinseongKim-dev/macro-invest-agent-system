# CLAUDE.md

> **MANDATORY FIRST STEP:** Read `claude-identity.md` before every task.
> It contains: system role, Tri-File Architecture law, legacy quarantine, UI API contract, coding standards, and task execution protocol.
> Do not proceed until it is loaded.

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

---

## Release Milestones

### v0.1.0-RELEASE (Stable) — 2026-05-24

**Status: FROZEN ✓**  
Git tag: `v0.1.0`  
HEAD commit: `0762ff0`

#### Completed Tasks

**① 폴더 구조 개편 (Monorepo layout)**
- [X] `apps/api/` — FastAPI 백엔드 격리
- [X] `apps/frontend/` — Next.js 15 프론트엔드 격리
- [X] `src/` — Tri-File Architecture 백엔드 코어 (`database.py`, `engines.py`, `main.py`)
- [X] `docker-compose.yml` 멀티 서비스 구성 (`aleph-api`, `aleph-frontend`)
- [X] `.dockerignore` 최적화 (빌드 컨텍스트 최소화, `uv.lock` 보호)
- [X] `apps/api/Dockerfile` 레이어 분리 캐싱 (`uv sync --frozen`)
- [X] `apps/frontend/Dockerfile` `--legacy-peer-deps` 호환성 처리

**② 무과금 오픈소스 AI 전환**
- [X] LangChain `create_react_agent` 기반 RAG 에이전트 파이프라인 구성
- [X] `_run_agent_async` 메시지 역순 탐색 — 최종 AIMessage 정확 추출
- [X] ESLint `^9.27.0` 다운그레이드 (`eslint-config-next` 호환)
- [X] `uv.lock` 커밋 추가 (`.gitignore` 제외 해제)

**③ Milvus RAG 연동**
- [X] `search_news_database` LangChain 툴 — Milvus 뉴스 임베딩 시맨틱 검색
- [X] Milvus 불가 시 in-memory 폴백 자동 전환
- [X] RAG 결과 → `AlephStreamData.briefing` 필드로 SSE 방출

**④ 프론트엔드 UI/UX 싱크 및 레이아웃 버그 픽스**
- [X] 자산 리스트 통일 — `GOOGL`/`NVDA` → `005930`(삼성전자) / `000660`(SK하이닉스)
- [X] `NetworkCanvas.tsx` 노드 레이블 한국 종목으로 교체
- [X] `RiskMatrix.tsx` 연속 스코어 적용 (`quant_score`, `sentiment_score`, `sig_confidence`)
- [X] SIG SCORE 셀 레이아웃 수정 — 텍스트 + 스파크라인 분리 (`CH=52`)
- [X] `AlephRiskRow` 타입에 선택적 수치 필드 추가 (`lib/types.ts`)
- [X] `LiveChart.tsx` JARVIS 호버 인터랙션 — 네온 글로우 + 슬라이드 패널
- [X] Framer Motion `AnimatePresence` / `motion.div` 패널 애니메이션 적용
- [X] `page.tsx` → `<LiveChart riskMatrix={...} />` SSE 스트림 연결
- [X] `formatPrice()` 한국 주식 ₩ 통화 포맷
- [X] `volScore()` 롤링 표준편차 기반 단기 변동성 지수

#### Core Files Locked at v0.1.0

| 레이어 | 파일 | 역할 |
|--------|------|------|
| Backend core | `src/database.py` | SQLite 스냅샷 스토어 |
| Backend core | `src/engines.py` | Quant / Sentiment / PersonaAdapter 엔진 |
| Backend core | `src/main.py` | FastAPI SSE + LangChain RAG 오케스트레이션 |
| Frontend | `apps/frontend/app/page.tsx` | 루트 레이아웃 + SSE 훅 연결 |
| Frontend | `apps/frontend/components/panels/LiveChart.tsx` | 실시간 포트폴리오 차트 + JARVIS 패널 |
| Frontend | `apps/frontend/components/panels/RiskMatrix.tsx` | 리스크/기회 매트릭스 SVG |
| Frontend | `apps/frontend/components/panels/NetworkCanvas.tsx` | Three.js 3D 네트워크 구체 |
| Frontend | `apps/frontend/lib/types.ts` | 백엔드 DTO 타입 계약 |
| Infra | `docker-compose.yml` | 멀티 서비스 오케스트레이션 |
| Infra | `apps/api/Dockerfile` | API 빌드 (uv 레이어 캐싱) |
| Infra | `apps/frontend/Dockerfile` | Next.js 빌드 |
| Infra | `.dockerignore` | 빌드 컨텍스트 최적화 |
| Deps | `uv.lock` | Python 의존성 잠금 파일 |
| Deps | `apps/frontend/package.json` | Node 의존성 (framer-motion 포함) |

---

### v0.1.1 + v0.1.2 — ETF 공급망 + KST 시간축 + 탭 UI

**Status: RELEASED ✓**
Git tag: `v0.1.2` (HEAD)

#### Completed Tasks

- [X] **ETF 3종 수집 타깃 추가** — `src/engines.py` TICKERS + `src/database.py` LIVE_TICKERS에 QQQ/BND/GLD 추가. SSE `risk_matrix` 8행으로 확장.
- [X] **ETF 전용 변동성 알고리즘 분기** — `src/engines.py` QuantEngine에 `if ticker in _ETF_TICKERS:` 분기 신설. ATR(14) 기반 spike detection (threshold 2.5%, spike_ratio 1.3×, penalty 0.10) 적용.
- [X] **KST 시간축 표준화** — `src/database.py` `_to_kst()` 헬퍼 + `_fetch_ticker_ohlcv()`에서 UTC→KST 변환 후 DB 적재. SSE `timestamp` 필드 KST(`+09:00`) ISO-8601 방출.
- [X] **뉴스 피드 실시간 교체** — `hooks/useNewsStream.ts` SWR 30초 폴링 (`/api/events/recent`). `AlephDashboard.tsx` 정적 `NEWS` 배열 완전 제거.
- [X] **[ALL][STOCKS][ETFS][FUNDS] 네온 탭 UI** — `AlephDashboard.tsx` `assetTab` 상태 + `filteredOrder` useMemo. FUNDS 탭은 "AWAITING FEEDS" 마스킹 (v0.3.0 예정).
- [X] **Holdings 스크롤 프레임 락** — `maxHeight: calc(100vh-420px)` 대형 자산 대응.

---

### Next Milestone: v0.2.0 — 국내 시장 정밀 타격 + 글로벌 지수 차트

**Status: PENDING**

#### Queued Tasks

- [ ] **국장 대형주 라인업 확장** — NAVER(035420), LG화학(051910), 삼성SDI(006400), KODEX 레버리지(122630) 수집 타깃 추가.
- [ ] **글로벌 지수 `index_ticks` 하이퍼테이블** — KOSPI(^KS11), KOSDAQ(^KQ11), S&P(^GSPC), NASDAQ(^IXIC), USD/KRW(KRW=X) 별도 테이블 신설.
- [ ] **중앙 차트 지수 원터치 토글** — `[KOSPI][S&P][KRW]` 버튼 → 선택 지수 실시간 차트 표시.
- [ ] **장문 AI 레포트 수신 버퍼 확장** — SSE 응답 스트림에서 LangChain RAG가 반환하는 장문 분석 텍스트가 잘리는 현상 방지.

