# Agora Comprehensive Repository Audit - May 2026

## 1. Code Quality Scan Findings

### Finding: Unsafe 'any' Types in Frontend
- **File:** `frontend/src/composables/useGraphRender.ts`
- **Lines:** 135, 141, 169, 230
- **Risk:** medium
- **Problem:** Frequent use of `any` in D3.js rendering logic masks type errors when handling graph data.
- **Evidence:** `const { nodes, edges, getColor } = buildGraphRenderData(data, types) as { nodes: any[]; edges: any[]; ... }`
- **Recommended fix:** Define concrete TypeScript interfaces for D3 nodes and edges (e.g., `GraphNode`, `GraphEdge`) and use them instead of `any`.

### Finding: Broad 'except Exception' Blocks in Backend Services
- **File:** `backend/app/services/graph_tools.py`
- **Lines:** 381, 439, 458, 539
- **Risk:** medium
- **Problem:** Catching the base `Exception` class can swallow critical logic errors, keyboard interrupts, or system exits, making debugging nearly impossible.
- **Evidence:** `except Exception as e: return {"error": f"Search failed: {e}"}`
- **Recommended fix:** Narrow down exception blocks to specific types (e.g., `neo4j.exceptions.ServiceUnavailable`, `ValueError`) and let unexpected errors bubble up to the global error handler.

### Finding: Flaky Vector Index Test due to Global State
- **File:** `backend/tests/storage/test_vector_index_dim_drift.py`
- **Lines:** 213
- **Risk:** low
- **Problem:** The test relies on `Config.VECTOR_DIM` which is shared across the process, leading to failures depending on test execution order.
- **Evidence:** Test failed during the audit run with a dimension mismatch error despite being a mock test.
- **Recommended fix:** Use dependency injection for configuration in `Neo4jStorage` or ensure proper teardown/mocking of the `Config` class.

---

## 2. Code Simplification and Refactoring Opportunities

### Opportunity: Centralize LLM Context Heuristics
- **Files:** `backend/app/utils/llm_client.py`, `backend/scripts/agent_tools.py`, `backend/scripts/_sim_common.py`
- **What can be simplified:** The `_MODEL_CONTEXT_HEURISTICS` table and resolution logic are duplicated with slight variations.
- **Why it is safe:** The logic is pure and deterministic.
- **Idea:** Create `backend/app/utils/llm_heuristics.py` and import it in all three locations.
- **Follow-up Issue:** ISSUE-01

### Opportunity: Unify Platform Simulation Logic
- **File:** `backend/scripts/run_parallel_simulation.py`
- **What can be simplified:** `run_twitter_simulation` and `run_reddit_simulation` share ~90% of their code.
- **Why it is safe:** The differences are primarily configuration-based (platform name, action list, DB path).
- **Idea:** Extract a generic `run_platform_simulation(config, platform_type, ...)` function.
- **Follow-up Issue:** ISSUE-02

---

## 3. Frontend ↔ Backend Alignment

### Mismatch: Missing Abort/Cancellation Support
- **Frontend File:** `frontend/src/api/index.ts`
- **Backend File:** `backend/app/api/simulation_run.py`
- **Expected contract:** Client should be able to abort long-running LLM requests.
- **Actual behavior:** Frontend has no mechanism to pass `AbortSignal` to Axios; backend continues processing even if client disconnects.
- **Concrete fix:** Add `AbortController` support to `frontend/src/api/index.ts` and ensure backend tasks check for cancellation where possible.

### Mismatch: Inconsistent Error Envelope in 'close-env'
- **Backend File:** `backend/app/api/simulation_run.py:488`
- **Frontend File:** `frontend/src/api/simulation.ts:251`
- **Actual behavior:** Returns `jsonify({"success": result.get("success", False), "data": result})` which skips the standard `@handle_api_errors` formatting.
- **Concrete fix:** Refactor to use `json_success(result)` to ensure consistent envelope structure.

---

## 4. Provider Integration Audit

### Provider: Ollama Local
- **Files inspected:** `backend/app/utils/llm_client.py`, `backend/scripts/run_parallel_simulation.py`
- **Current request flow:** API calls go through `LLMClient` which uses the OpenAI Python SDK pointing to the Ollama `/v1` endpoint.
- **Current response flow:** Standard OpenAI response objects are parsed; `<think>` blocks are stripped via regex.
- **Current streaming behavior:** Enabled via `LLM_FORCE_STREAM=true` to bypass Ollama 0.21.0 non-streaming stalls.
- **Current auth/config behavior:** Uses `api_key="ollama"` as a dummy value for local instances.
- **Failure points:** Inconsistent schema enforcement; Ollama prefers native `/api/chat` with `format="json"` or a schema object, which the OpenAI SDK doesn't always transmit correctly to Ollama.
- **Recommended fixes:** Implement native `/api/chat` path in `LLMClient` specifically for Ollama routes to ensure robust structured output.

### Provider: OpenAI
- **Files inspected:** `backend/app/utils/llm_client.py`, `backend/app/services/llm_runtime.py`
- **Current request flow:** Direct usage of OpenAI SDK with `max_completion_tokens` vs `max_tokens` heuristic.
- **Current response flow:** Native SDK parsing.
- **Current streaming behavior:** Optional, handled by `LLMClient.chat`.
- **Current auth/config behavior:** Validates `sk-` prefix; resolves from `SecretResolver`.
- **Failure points:** Token limit key mismatches (fixed via `_swap_token_kwargs` fallback).
- **Recommended fixes:** Unified abstraction for token limit keys.

### Provider: Google Gemini
- **Files inspected:** `backend/app/utils/llm_client.py`, `backend/scripts/run_parallel_simulation.py`
- **Current request flow:** API uses OpenAI-compatible endpoint. OASIS scripts use native CAMEL `GeminiModel`.
- **Current response flow:** SDK-based parsing.
- **Current auth/config behavior:** Validates `AIza` prefix.
- **Failure points:** OpenAI-compatible wire path strips `thought_signature` in tool calls, leading to 400 errors during multi-turn ReACT loops.
- **Recommended fixes:** Add native Gemini SDK support to `LLMClient` to preserve internal state during tool-calling sessions.

### Proposed Unified Provider Interface
```typescript
type LlmProviderName = "ollama" | "openai" | "gemini";

type NormalizedLlmRequest = {
  provider: LlmProviderName;
  model: string;
  messages: Array<{ role: "system" | "user" | "assistant"; content: string }>;
  temperature?: number;
  maxTokens?: number;
  stream?: boolean;
  signal?: AbortSignal;
};

interface LlmProvider {
  name: LlmProviderName;
  validateConfig(): Promise<void>;
  complete(request: NormalizedLlmRequest): Promise<string>;
  stream(request: NormalizedLlmRequest): AsyncIterable<NormalizedLlmChunk>;
}
```

---

## 5. Implementation Plan

| Item | Why it matters | Files affected | Risk | Validation Command |
|---|---|---|---|---|
| **P0: Centralize Heuristics** | Prevents context truncation and drift between API and Sim | `llm_client.py`, `agent_tools.py`, `_sim_common.py` | Medium | `cd backend && uv run pytest tests/test_llm_heuristics.py` |
| **P0: Gemini Robustness** | Enables complex report generation with Gemini models | `llm_client.py` | High | `cd backend && uv run pytest tests/services/test_report_agent_gemini.py` |
| **P1: Abort Controller** | Saves provider costs and improves UI responsiveness | `frontend/src/api/index.ts` | Medium | Manual: Start ontology gen -> Cancel -> Check browser Network tab |
| **P1: Unify Sim Logic** | Reduces maintenance burden for OASIS platform scripts | `run_parallel_simulation.py` | Low | `cd backend && uv run python scripts/run_parallel_simulation.py --help` |
| **P2: Type Safety Push** | Prevents "undefined is not a function" runtime crashes | `frontend/src/**/*.ts` | Medium | `cd frontend && npm run check` |
