# Architektur-Single-Sources-of-Truth

> **Progressive Disclosure** — ausgelagert aus [`AGENTS.md`](../../AGENTS.md). Bei Architektur-, Code- oder Vertragsfragen laden.

- API-Verträge: `backend/app/contracts/` mit Pydantic v2
- HTTP-API-Referenz (Endpunkte nach Domänen): [`../api.md`](../api.md) — Envelopes/Fehlercodes in [`../api-contracts.md`](../api-contracts.md)
- Frontend-Spiegel: `frontend/src/contracts/` und generierte `schemas/`
- Provider-Erkennung: `backend/app/llm/providers/registry.py::detect_provider`
- Provider-Verbindung: `ProviderConnection`
- strukturierte JSON-LLM-Calls: `backend/app/llm/client.py::LLMClient.chat_json` mit Pydantic-Schema — roher `OpenAI`-Client nicht für JSON-Outputs
- kanonische Modellauswahl: `frontend/src/components/v4/forms/AiModelPicker.vue`
- kanonische Modellreferenz: `AiModelRef`
- kanonische Route: `AiRoute` / `LlmRoute`
- Embedding-Konfiguration: `embedding_service.py` und `embedding_migration.py`
- Evidence-Gating: ADR-0002-Hartanker

Chat-Routing und Embedding-Konfiguration bleiben strukturell getrennt.