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

---

### v0.2.0 — DigitalOcean 하이브리드 인프라 (Production Infra)

**Status: RELEASED ✓**
Git tag: `v0.2.0`

#### Completed Tasks

- [X] **`src/config.py` 신규** — `ENV_MODE=PRODUCTION` 시 Groq API 강제, `LOCAL` 시 Groq 우선/Ollama 폴백. `CORS_ORIGINS` 런타임 주입(`CORS_ALLOWED_ORIGINS` 환경변수).
- [X] **Milvus Lite 마이그레이션** — `src/database.py` Docker Milvus(~1GB RAM) → `MilvusClient` 파일 기반 임베디드 스토어. `_MILVUS_LITE_PATH` 환경변수 설정.
- [X] **`src/main.py` 프로덕션 배선** — `config.CORS_ORIGINS` CORSMiddleware 연결, `_build_lc_agent()` `config.get_llm()` 위임. `/api/events/recent` 엔드포인트 신설(SWR 뉴스 피드용).
- [X] **`docker-compose.prod.yml` 신규** — FastAPI + TimescaleDB 전용, 컨테이너당 `memory: 800m` 제한, Milvus 컨테이너 제거.
- [X] **프론트엔드 환경변수 정비** — `apps/frontend/app/api/stream/market/route.ts` `API_BASE_URL` → `ALEPH_API_URL` 교체. `/api/v1/intelligence/command` 프록시 라우트 신설. `/api/events/recent` 프록시 라우트 신설.
- [X] **`.env.example` 업데이트** — `ENV_MODE`, `MILVUS_LITE_PATH`, `CORS_ALLOWED_ORIGINS` 문서화.
- [X] **`apps/frontend/.env.local.example` 신규** — `ALEPH_API_URL`, `NEXT_PUBLIC_API_URL` 문서화.
- [X] **`.github/workflows/backend-cd.yml` 신규** — Docker Hub 빌드/푸시 → SSH VPS 롤링 배포 CD 파이프라인.
- [X] **`pyproject.toml` 의존성 갱신** — `pymilvus>=2.4.0`, `milvus-lite>=2.4.0`, `langchain-ollama>=0.2.0`, `pytz>=2024.1` 추가.

---

### v0.2.1 — 국내 시장 정밀 타격 + 글로벌 지수 차트 + 하이브리드 스케줄러

**Status: RELEASED ✓**
Git tag: `v0.2.1`

#### Completed Tasks

- [X] **국장 대형주 라인업 확장** — `src/engines.py` TICKERS + `src/database.py` LIVE_TICKERS에 NAVER(035420) / LG화학(051910) / 삼성SDI(006400) / KODEX LEV(122630) 추가. Risk matrix 12행 확장.
- [X] **글로벌 지수 `index_ticks` 하이퍼테이블 + 실시간 수집** — `src/database.py` `INDEX_TICKERS` / `fetch_live_index_data()` 신설. KOSPI(^KS11) / S&P 500(^GSPC) / USD-KRW(KRW=X) yfinance 실시간 수집.
- [X] **`market_indices` SSE 페이로드 필드** — `src/main.py` `_INDEX_CACHE` + `_live_collector_loop()` 인덱스 fetch. `_build_payload()` → `market_indices` 필드 추가. `lib/types.ts` 타입 반영.
- [X] **중앙 차트 지수 원터치 토글** — `AlephDashboard.tsx` `activeIndex` 상태 + `indexHistory` 버퍼. `[PORTFOLIO][KOSPI][S&P][KRW]` 네온 버튼 → 선택 지수 실시간 차트 표시.
- [X] **KST 하이브리드 스케줄러** — `_get_collection_interval()` 헬퍼 신설. KR 장중(09:00–15:30 KST) / 미국 장중(22:30–05:00 KST) → 10초, 장 외 → 60초.
- [X] **OMNI-COMMAND 502 → 오프라인 폴백** — `apps/frontend/app/api/v1/intelligence/command/route.ts` 백엔드 연결 실패 시 HTTP 200 + 구조화된 오프라인 응답 반환.
- [X] **이름 수정** — UI `KIM MIN-HO` → `KIM MIN-SEONG` (AlephDashboard.tsx 2곳).

---

### v0.3.0 — 진짜 데이터 수혈 및 연결 안정화

**Status: RELEASED ✓**
Git tag: `v0.3.0`

#### Completed Tasks

- [X] **SSE 재연결 지수 백오프** — `useAlephStream.ts` 전면 재작성. 풀 지터 백오프(3→6→12→30 s), 탭 가시성 재연결, 싱글톤 정리. `RECONNECTING` 프리즈 해소.
- [X] **매크로 배치 수집 엔진** — `src/database.py` `fetch_macro_indicators()` 신설. T10Y/T3M/VIX(yfinance) + FEDFUNDS/CPI/GDP/UNRATE(FRED, 선택). `macro_indicators` 하이퍼테이블 저장. `src/main.py` `_macro_collector_loop()` 서버 기동 시 hourly 루프 시작.
- [X] **`macro_indicators` SSE 페이로드** — `_MACRO_CACHE` dict `_build_payload()` 포함. 대시보드 VIX·T10Y·FED_RATE 정적값 → 실시간 스트림 연결.
- [X] **Milvus 가격 동기화 브릿지** — `src/database.py` `embed_price_alert()` 신설. `fetch_live_market_data()` 내 ≥2% 가격 변동 감지 시 즉시 Milvus 임베딩 ("삼성전자 3.2% 급락 …") → RAG 에이전트 실시간 컨텍스트.
- [X] **`macro_indicators` 하이퍼테이블** — `macro_indicators(snapshot_time, series_id, value, source)` 30일 청크 TimescaleDB.
- [X] **`FRED_API_KEY` 환경변수** — 선택적; 미설정 시 yfinance 프록시 폴백.
- [X] **`lib/types.ts`** — `macro_indicators?: Record<string, number>` 추가.

---

### v0.3.1 — AI 리서치 패널 + OMNI 스트리밍

**Status: RELEASED ✓**

#### Completed Tasks

- [X] **슬라이드 아웃 AI 리서치 패널** — `ResearchPanel.tsx` 신규. 커스텀 마크다운 렌더러. Framer Motion 슬라이드 인/아웃. 백드롭 dimming. 메타데이터 칩(Regime/Health/Confidence/Signal).
- [X] **LangChain 실시간 토큰 스트리밍** — `POST /api/v1/intelligence/command/stream` SSE 엔드포인트 신설. 단어 단위 토큰 방출 (`asyncio.sleep(0.025)`). Next.js 스트림 프록시 라우트 추가. 프론트엔드 `ReadableStream` 파싱으로 SSE 수신.
- [X] **APP_VERSION v0.1.2 → v0.3.1** 갱신.

#### Deferred

- [ ] **공모 펀드 일일 NAV 적재** — KOFIA OpenAPI → `fund_nav_ticks` 하이퍼테이블. `[FUNDS]` 탭 실데이터 연결. (v0.4.0으로 이동)

---

### Next Milestone: v0.4.0 — Quant Score Engine (PRD Phase D-1)

**Status: PENDING**

#### PRD 연계 (Phase D-1 — 멀티엔진 분석 체계)

- [ ] **Quant Score 엔진** — 지표별 가중치 적용 정량 점수 시스템. `QuantScoreEngine` 도메인 레이어 신설.
- [ ] **엔진 간 충돌 표면화** — `conflict_surface_v1` 확장. 크로스엔진 합성 뷰.
- [ ] **공모 펀드 일일 NAV 적재** — KOFIA OpenAPI → `fund_nav_ticks`. `[FUNDS]` 탭 실데이터 연결.
- [ ] **백테스팅 기반 마련** — 과거 매크로 데이터 2년치 로드. Regime 분류 정확성 검증 스크립트.

---

## PRD 로드맵 (2026-06-26 기준)

### Phase A — 실사용 가능한 MVP ✓ COMPLETE

- A-1 실데이터 연동 (FRED/Yahoo Finance/Alpha Vantage) ✓
- A-2 프론트엔드-백엔드 연결 ✓
- A-3 배포 (Vercel + DigitalOcean VPS) ✓
- A-4 일상 사용 안정화 — v0.3.x 시리즈 진행 중

### Phase B — 프로덕트 기반 강화 (예정)

- B-1 인증 & 사용자 관리 (Supabase Auth 또는 Clerk)
- B-2 사용자 맞춤 기능 (관심 지표 선택, 위젯 레이아웃)
- B-3 모바일 반응형 (핵심 뷰 우선)

### Phase D — 분석 깊이 & 기술 고도화 (v0.4.0+ 대상)

- D-1 멀티엔진 분석 체계 — Quant Score 엔진, 크로스엔진 합성 (💰 무료)
- D-2 백테스팅 + Eval 하네스 — 과거 데이터 Regime 검증, 시그널 히트율 (💰 무료)
- D-3 AI 해석 레이어 고도화 — LLM 보강 설명, What-if 시나리오 (💰 Claude API)
- D-4 실시간 파이프라인 + 알림 — 이벤트 기반 수집, Regime 전환 알림 (💰 서버 비용)

### Phase E — 프로덕트화 & 커뮤니티 (장기)

- E-1 랜딩 페이지 & 온보딩
- E-2 사용자 피드백 & 분석
- E-3 커뮤니티 기능 (공유, 타임라인)
- E-4 수익화 (Stripe, Pro 티어)

