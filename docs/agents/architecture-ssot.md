# Architektur — Single Sources of Truth

> Laden bei Architektur-, Vertrags- oder Routing-Fragen.

| Konzept | Kanonischer Pfad |
|---------|-----------------|
| API-Vertraege | `backend/app/contracts/` (Pydantic v2) |
| HTTP-API-Referenz | [`../api.md`](../api.md), Envelopes in [`../api-contracts.md`](../api-contracts.md) |
| Frontend-Spiegel | `frontend/src/contracts/` + generierte `schemas/` |
| Provider-Detection | `backend/app/llm/providers/registry.py::detect_provider` |
| Provider-Verbindung | `ProviderConnection` |
| Strukturierte LLM-Calls | `backend/app/llm/client.py::LLMClient.chat_json` (Pydantic-Schema, strict-mode, Repair) |
| Modellauswahl-UI | `frontend/src/components/v4/forms/AiModelPicker.vue` |
| Modellreferenz | `AiModelRef` / `AiRoute` / `LlmRoute` |
| Embedding-Config | `embedding_service.py` + `embedding_migration.py` |
| Evidence-Gating | ADR-0002 Hartanker (siehe `CLAUDE.md`) |

Chat-Routing und Embedding-Konfiguration sind strukturell getrennt.
