# [Jules][refactor][provider][backend][testing] Split monolithic `llm_client.py` into provider adapters + shared transport

Master issue: Master audit 2026-05-22.

## Problem
`llm_client.py` mixes schema transforms, retries, provider logic, streaming parsing, and tool-call handling.

## Evidence
- `backend/app/utils/llm_client.py` lines 1-1633

## Scope
- Introduce adapter interface and concrete providers (Ollama/OpenAI/Gemini)
- Move retry and error normalization to shared transport layer
- Keep behavior parity via tests

## Acceptance Criteria
- [ ] `llm_client.py` responsibilities reduced substantially
- [ ] Provider adapters have dedicated unit tests
- [ ] Streaming and non-streaming paths validated for each provider
- [ ] No regression in existing LLM client tests
