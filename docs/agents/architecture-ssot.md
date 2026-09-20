# Architektur — Single Sources of Truth

> Laden bei Architektur-, Vertrags- oder Routing-Fragen. Stand 20.09.2026, geprüfte Main-Baseline `4296b7de`; Details und bekannte Ausnahmen in [`../architecture.md`](../architecture.md) und [`../STATUS.md`](../STATUS.md).

| Konzept | Kanonischer Pfad |
|---------|-----------------|
| API-Verträge | `backend/app/contracts/` (Pydantic v2) |
| HTTP-API-Referenz | [`../api.md`](../api.md), Envelopes in [`../api-contracts.md`](../api-contracts.md) |
| Frontend-Spiegel | `frontend/src/contracts/` + generierte `schemas/` |
| Provider-Metadaten | `backend/app/services/llm_provider_registry.py` (`_CONNECTION_DEFINITIONS`) |
| Provider-Detection / Transport | `backend/app/llm/providers/registry.py::detect_provider` + Provideradapter |
| Provider-Verbindung | `ProviderConnection` |
| Provider mit `transport="cli"` (Codex, ChatGPT-Abo) | `backend/app/llm/providers/codex_cli.py` (kein HTTP, Session-Auth via `codex login`, #1405) |
| Provider mit `transport="cli"` (Claude Code, Claude-Abo) | `backend/app/llm/providers/claude_cli.py` (kein HTTP, `CLAUDE_CODE_OAUTH_TOKEN` im Fernet-Secret-Store, isoliertes `HOME`/`cwd` je Aufruf, #1531) |
| Amazon Bedrock (OpenAI-kompatibler mantle-Pfad) | `OpenAIAdapter` + Bearer-Token, Host-Erkennung `registry.py::_is_bedrock_host` (`bedrock-mantle.<region>.api.aws` / `bedrock-runtime.<region>.amazonaws.com`, #1282) |
| Request-Shaping (kwargs-Bau, Provider-Quirks) | `backend/app/llm/request_plan.py::build_request` + `RequestOptions` |
| Request-Fehlerbehandlung/Retry | `backend/app/llm/request_plan.py::execute` |
| Strukturierte LLM-Calls | `backend/app/llm/client.py::LLMClient.chat_json` (Pydantic-Schema, strict-mode, Repair) |
| Modellauswahl-UI | `frontend/src/components/v4/forms/AiModelPicker.vue` |
| Modellreferenz / Route | `AiModelRef` / `AiRoute` / `LlmRoute` |
| Provider-Secrets | verschlüsselter Provider-Secret-Store, Master `AGORA_SECRET_KEY` |
| Workspace-API-Keys | `backend/data/api_keys.json`, Master `AGORA_FERNET_KEY` |
| Embedding-Config (Persistenz) | `backend/app/services/embedding_configuration_store.py` |
| Embedding-Verarbeitung/Migration | `embedding_service.py` + `embedding_migration.py` |
| Evidence-Gating | ADR-0002 Hartanker (siehe `CLAUDE.md`) |
| Run-/Jobstatus | RunRegistry / Run-Contracts |
| Run-Read-Model (Listen-/Detail-Anreicherung) | `backend/app/services/run_read_model.py` (aus `api/runs.py` extrahiert, #1496) |
| Simulations-Read-Metriken (Timeline/Agent-Stats) | `backend/app/services/sim/run_metrics.py` (aus `sim/monitor.py` extrahiert, #1496) |
| Report-Artefakte | `backend/uploads/reports/<report_id>/` |
| Report-Vollständigkeitsprüfung vor Abschluss | `backend/app/services/report_agent/requirement_checker.py` (`RequirementChecker`, #1302) |
| Interview-Panel-Rotation | `backend/app/services/interview_panel.py` (`InterviewPanelTracker`, #1303) |
| Projekt-Metadaten-Vertrag | `backend/app/contracts/project_contract.py` (Pydantic v2, ersetzt die `Project`-Dataclass) |
| Projekt-Repository-Port | `backend/app/repositories/project_repository.py::ProjectRepository` (Protocol), Datei-Adapter `FileProjectRepository`, Default `AGORA_PROJECT_BACKEND=file` |
| Projekt-Repository, PostgreSQL-Adapter | `backend/app/infrastructure/postgres/repositories/project_repository.py::PostgresProjectRepository` (Tabelle `agora.projects`, Kern-Spalten + `payload jsonb`) |
| LLM-Profil-Repository-Port | `backend/app/repositories/llm_profile_repository.py::LlmProfileRepository` (Protocol), SQLite-Adapter `SqliteLlmProfileRepository` (vormals `LlmProfilesStore`), Default `AGORA_LLM_PROFILE_BACKEND=sqlite` |
| LLM-Profil-Repository, PostgreSQL-Adapter | `backend/app/infrastructure/postgres/repositories/llm_profile_repository.py::PostgresLlmProfileRepository` (Tabelle `agora.llm_profiles`; API-Keys bleiben im Fernet-`LlmProfileSecretsStore`, keine `api_key`-Spalte) |
| PostgreSQL-Grundlage (SQLAlchemy/Alembic) | `backend/app/infrastructure/postgres/` (`Database.session()`), Migrationen unter `backend/migrations/` (Alembic), Default `AGORA_METADATA_BACKEND=legacy` |

## Bekannte SSoT-Ausnahme

**Embedding #1417:** Der `EmbeddingConfigurationStore` ist die beabsichtigte persistente Wahrheit, aber noch nicht jeder produktive Runtime-Consumer bezieht seine effektive Konfiguration ausschließlich von dort. Einige Pfade können weiterhin `Config.EMBEDDING_*`/Env lesen.

Daher bis zur Behebung nicht behaupten:

```text
aktive Embedding-Konfiguration in der UI == garantiert effektive Runtime-Konfiguration
```

Chat-Routing und Embedding-Konfiguration bleiben strukturell getrennt.

## PostgreSQL ist ein zweiter Adapter, keine Ablösung

Projekt- und LLM-Profil-Metadaten haben seit `docs/plans/supabase.md` je einen Repository-Port mit zwei Implementierungen: dem bestehenden JSON-/SQLite-Adapter (Default) und einem PostgreSQL-Adapter. Beide Umschalter (`AGORA_PROJECT_BACKEND`, `AGORA_LLM_PROFILE_BACKEND`) stehen im Default auf dem Datei-/SQLite-Pfad; `AGORA_METADATA_BACKEND=postgres` erzeugt ohne einen dieser Umschalter noch keine einzige Verbindung. Nicht behaupten, PostgreSQL habe die Dateiablage oder SQLite abgelöst — es ist ein paralleler, migrierbarer Adapter hinter demselben Port.

## Grundregel

Wenn bereits eine aufgelöste Run-/Stage-Route oder persistente Konfiguration existiert, darf ein Legacy-/Env-Fallback sie nicht durch Modell-/URL-Heuristik ersetzen. Fallbacks sind Bootstrap/Backward-Compatibility, keine zweite gleichberechtigte Wahrheit.
