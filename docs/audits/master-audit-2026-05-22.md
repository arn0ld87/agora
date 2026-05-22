# Agora Master Audit (2026-05-22)

## Area 1 — Code Quality Findings

### Finding: Divergent provider naming across contracts increases runtime mismatch risk
- File: `backend/app/services/llm_runtime.py`
- Lines: 20-29, 115-120
- Risk: high
- Problem: Runtime config aliases map `gemini -> google`, while other API/contracts expose both `gemini` and `google` conventions.
- Evidence: `_PROVIDER_ALIASES` normalizes to `google`; invalid-provider error message only lists `google`, not `gemini`.
- Recommended fix: Introduce one canonical provider enum in shared contract (`ollama|openai|gemini|custom_openai`), and normalize all route and registry layers to it.

### Finding: Provider metadata hard-codes stale model defaults
- File: `backend/app/services/llm_provider_registry.py`
- Lines: 43, 52
- Risk: medium
- Problem: Fallback models include legacy names (`o1-preview`, `gemini-1.5-*`) that can drift from actually supported models.
- Evidence: Static list literals are returned to UI with no freshness validation.
- Recommended fix: Move defaults into versioned config and validate with `/models` probe + health-cache.

### Finding: API error envelope is inconsistent with modern typed error envelope goal
- File: `backend/app/utils/api_responses.py`
- Lines: 149-156
- Risk: high
- Problem: Error shape uses `{ success:false, error:string, code?:string }`, while frontend proposals and typed handling expect nested error object.
- Evidence: `json_error()` writes a flat `error` string; no provider/retryable metadata.
- Recommended fix: Add v2 envelope (`{error:{code,message,provider,retryable,details}}`) and migrate endpoints incrementally.

### Finding: Frontend transport layer logs full errors in interceptors
- File: `frontend/src/api/index.ts`
- Lines: 58-59, 84, 109, 129
- Risk: medium
- Problem: `console.error` is called with potentially rich error objects from backend responses.
- Evidence: raw error objects and wrapped response bodies are printed.
- Recommended fix: Route through centralized redacted logger utility and strip provider/base-url/response payload details in production.

### Finding: Large LLM client module mixes multiple responsibilities
- File: `backend/app/utils/llm_client.py`
- Lines: 1-1633
- Risk: medium
- Problem: Single file handles schema flattening, provider heuristics, retries, streaming parsing, tools, and vision.
- Evidence: 1600+ LOC with many concerns and provider-specific branches.
- Recommended fix: Split into provider adapters + shared transport + schema utilities.

## Area 2 — Simplification / Maintainability

### Proposal: Extract model context heuristics into one shared module
- Current file/function: `backend/app/utils/llm_client.py` `_MODEL_CONTEXT_HEURISTICS`; comment references duplication in scripts.
- What can be simplified: Centralize heuristics table used by runtime and scripts.
- Why safe: Read-only lookup logic; behavior preserved by importing same constant.
- Before/after:
  - Before: duplicated tuple in app and script paths.
  - After: `app/llm/context_limits.py` imported by both.
- Follow-up issue: yes.

### Proposal: Consolidate SSE reconnect constants and behavior
- Current files: `backend/app/api/logs.py`, `backend/app/api/simulation_stream.py`, `backend/app/api/settings.py`, frontend `useEventStream.ts`.
- What can be simplified: Duplicate retry/poll constants and reconnect logic.
- Why safe: Transport-only behavior; can preserve existing defaults.
- Before/after: Shared SSE config helper and explicit reconnect policy docs/tests.
- Follow-up issue: yes.

### Proposal: Consolidate API error handling to a typed frontend helper
- Current files: `frontend/src/api/index.ts`, `frontend/src/api/envelope.ts`.
- What can be simplified: Duplicate code paths for success:false and Axios error path.
- Why safe: Same thrown `ApiError`, reduced branching.
- Before/after: `parseApiError(responseOrAxiosError)` utility.
- Follow-up issue: yes.

## Area 3 — Frontend ↔ Backend Alignment

### Mismatch: Provider naming (`gemini` vs `google`) leaks through UI/backend boundaries
- Frontend reference: `frontend/src/contracts/llmProfileContract.ts` provider literal includes `gemini`.
- Backend reference: `backend/app/services/llm_runtime.py` alias and normalization to `google`; `backend/app/services/llm_provider_registry.py` uses id/type `google`.
- Expected contract: One stable provider identifier across payloads and runtime routing.
- Actual frontend behavior: Can emit `gemini` in profile/runtime data.
- Actual backend behavior: Converts to `google`, but surfaces mixed naming externally.
- Fix: Canonicalize to `gemini` in API contracts and keep internal mapping only at adapter boundary.

### Mismatch: Error envelope semantics differ between backend and frontend target
- Frontend reference: `frontend/src/api/index.ts` custom wrapper expects flat success/error envelope and builds `ApiError` heuristically.
- Backend reference: `backend/app/utils/api_responses.py` only returns flat error plus optional `code`.
- Expected contract: Consistent `ApiError` envelope with provider/retryable/details.
- Actual frontend behavior: infers timeout/network locally; retryability not authoritative.
- Actual backend behavior: lacks structured provider/retryable fields.
- Fix: Introduce backend error normalizer and generated TS type from backend schema.

### Mismatch: Abort/cancellation semantics are inconsistent
- Frontend reference: axios client in `frontend/src/api/index.ts` lacks default AbortSignal propagation helper.
- Backend reference: SSE endpoints rely on connection close, but standard POST endpoints do not expose cancellation status semantics.
- Expected contract: Predictable abort behavior for long-running LLM-triggered routes.
- Actual frontend behavior: mixed (SSE reconnect logic exists; request cancel not standardized).
- Actual backend behavior: long-run operations mainly rely on timeout/errors.
- Fix: add cancellable request wrappers on frontend and cancellation-aware API contract for long operations.

## Area 4 — Provider Integration Audit

### Provider: Ollama Local
- Files inspected: `backend/app/utils/llm_client.py`, `backend/app/services/llm_runtime.py`, `backend/app/services/llm_provider_registry.py`.
- Current request flow: OpenAI-compatible client, with local profile shortcut allowing missing key and default `api_key='ollama'`.
- Current response flow: mostly `chat.completions`; some direct httpx call path for schema chat.
- Current streaming behavior: force-stream path for ollama cloud/non-local variants in chat and tools code paths.
- Current auth/config behavior: key optional for local URLs, base URL from profile/runtime/registry.
- Failure points: mixed transport paths (OpenAI SDK + raw httpx) produce inconsistent error mapping; model context heuristics may be stale.
- Recommended fixes: dedicated Ollama adapter, normalized errors, consolidated streaming parser, explicit local/cloud mode.

### Provider: OpenAI
- Files inspected: `backend/app/utils/llm_client.py`, `backend/app/services/llm_runtime.py`.
- Current request flow: OpenAI SDK `chat.completions.create` with retry wrapper.
- Current response flow: post-processing for text/tool calls and strict schema fallback logic.
- Current streaming behavior: conditional stream in some branches.
- Current auth/config behavior: resolved via runtime config, active provider store, or env fallback.
- Failure points: key-source/base-url precedence is complex and hard to reason about; strict-schema fallbacks are embedded and not unit-separated.
- Recommended fixes: deterministic precedence matrix + per-provider config validator + isolated schema transformer unit tests.

### Provider: Google Gemini
- Files inspected: `backend/app/services/llm_runtime.py`, `backend/app/services/llm_provider_registry.py`, `backend/app/utils/llm_client.py`.
- Current request flow: routed through OpenAI-compatible Gemini endpoint.
- Current response flow: shares OpenAI parsing branch.
- Current streaming behavior: inherited from shared chat completion path.
- Current auth/config behavior: prefix-check for `AIzaSy` when provider is `google`.
- Failure points: nomenclature mismatch (`gemini` vs `google`) + OpenAI-compat behavior hidden behind generic path can mask provider-specific errors.
- Recommended fixes: explicit Gemini adapter wrapper with provider-specific error codes and test fixtures.

## Unified Provider Abstraction (proposed)
1. Add `backend/app/services/llm/providers/base.py` interface with `complete`, `stream`, `validate_config`.
2. Add adapters: `ollama_provider.py`, `openai_provider.py`, `gemini_provider.py`.
3. Keep one normalized request/response model in `backend/app/contracts/llm_provider_runtime_contract.py`.
4. Centralize error normalization (provider, code, retryable, status, details).
5. Keep retry policy in one layer (transport), not in each adapter.
6. Add integration tests with mocked provider responses for non-streaming, streaming, timeout, 401, and malformed chunk.

## Prioritized Implementation Plan
1. **Critical:** unify provider naming + error envelope contract (high risk reduction).
2. **High:** extract provider adapters from `llm_client.py` and freeze precedence rules for key/base_url/model.
3. **High:** frontend/backend cancellation + retry semantics alignment.
4. **Medium:** de-duplicate context-limit heuristics and SSE reconnect config.
5. **Medium:** model-catalog freshness checks and stale fallback model cleanup.
6. **Medium:** expand regression tests around provider-specific failures.

## Suggested follow-up issue set (created as local issue drafts)
See `docs/issues/` files prefixed `2026-05-22-`.
