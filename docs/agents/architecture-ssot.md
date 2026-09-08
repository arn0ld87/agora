# Architektur — Single Sources of Truth

> Laden bei Architektur-, Vertrags- oder Routing-Fragen. Stand 08.09.2026; Details und bekannte Ausnahmen in [`../architecture.md`](../architecture.md) und [`../STATUS.md`](../STATUS.md).

| Konzept | Kanonischer Pfad |
|---------|-----------------|
| API-Verträge | `backend/app/contracts/` (Pydantic v2) |
| HTTP-API-Referenz | [`../api.md`](../api.md), Envelopes in [`../api-contracts.md`](../api-contracts.md) |
| Frontend-Spiegel | `frontend/src/contracts/` + generierte `schemas/` |
| Provider-Metadaten | `backend/app/services/llm_provider_registry.py` |
| Provider-Detection / Transport | `backend/app/llm/providers/registry.py::detect_provider` + Provideradapter |
| Provider-Verbindung | `ProviderConnection` |
| Provider mit `transport="cli"` | `backend/app/llm/providers/codex_cli.py` (kein HTTP, Session-Auth) |
| Strukturierte LLM-Calls | `backend/app/llm/client.py::LLMClient.chat_json` (Pydantic-Schema, strict-mode, Repair) |
| Modellauswahl-UI | `frontend/src/components/v4/forms/AiModelPicker.vue` |
| Modellreferenz / Route | `AiModelRef` / `AiRoute` / `LlmRoute` |
| Provider-Secrets | verschlüsselter Provider-Secret-Store, Master `AGORA_SECRET_KEY` |
| Workspace-API-Keys | `backend/data/api_keys.json`, Master `AGORA_FERNET_KEY` |
| Embedding-Config (Persistenz) | `backend/app/services/embedding_configuration_store.py` |
| Embedding-Verarbeitung/Migration | `embedding_service.py` + `embedding_migration.py` |
| Evidence-Gating | ADR-0002 Hartanker (siehe `CLAUDE.md`) |
| Run-/Jobstatus | RunRegistry / Run-Contracts |
| Report-Artefakte | `backend/uploads/reports/<report_id>/` |

## Bekannte SSoT-Ausnahme

**Embedding #1417:** Der `EmbeddingConfigurationStore` ist die beabsichtigte persistente Wahrheit, aber noch nicht jeder produktive Runtime-Consumer bezieht seine effektive Konfiguration ausschließlich von dort. Einige Pfade können weiterhin `Config.EMBEDDING_*`/Env lesen.

Daher bis zur Behebung nicht behaupten:

```text
aktive Embedding-Konfiguration in der UI == garantiert effektive Runtime-Konfiguration
```

Chat-Routing und Embedding-Konfiguration bleiben strukturell getrennt.

## Grundregel

Wenn bereits eine aufgelöste Run-/Stage-Route oder persistente Konfiguration existiert, darf ein Legacy-/Env-Fallback sie nicht durch Modell-/URL-Heuristik ersetzen. Fallbacks sind Bootstrap/Backward-Compatibility, keine zweite gleichberechtigte Wahrheit.
