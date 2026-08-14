# HTTP-API — Agora Backend

**Stand:** 14.08.2026, Backend `0.9.5` (`39b65297`). Uebersicht nach Domaenen, nicht jede Einzelroute. Response-Envelopes und `ApiErrorCode`-Katalog: [`api-contracts.md`](api-contracts.md). Vertragsmodelle: [`../backend/app/contracts/`](../backend/app/contracts/).

Quelle der Wahrheit fuer Routen: [`../backend/app/api/`](../backend/app/api/) (Blueprints registriert in [`../backend/app/__init__.py`](../backend/app/__init__.py)).

---

## Konventionen

- **Base URL:** Backend `:5001`, Frontend-Dev `:5173`. Fachliche Endpunkte unter `/api/*`.
- **Auth:** `Authorization: Bearer <AGORA_AUTH_TOKEN>`. SSE/Downloads nutzen signierte Tickets — keine Plaintext-Tokens in URLs. Details: [`auth.md`](auth.md).
- **Response-Envelope:** `{"success": bool, "data"?, "code"?, "error"?}`. Ausnahmen: SSE-Streams und Exporte (Markdown, CSV, ZIP) liefern rohe Responses.
- **SSE-Streams:** mit **(SSE)** gekennzeichnet.
- **Fehlercodes:** semantische `ApiErrorCode`-Werte — Katalog in [`api-contracts.md`](api-contracts.md).

---

## Domaenen-Uebersicht

13 Blueprints, 176 Route-Dekoratoren. Mount-Pfade aus `app/__init__.py`.

### Auth & API-Keys

| Blueprint | Mount | Routen |
|-----------|-------|--------|
| `auth_bp` | `/api/auth` | `POST /ticket` |
| `api_keys_bp` | `/api/api-keys` | `GET /`, `POST /`, `DELETE /<key_id>` |

### Onboarding & Profil

| Blueprint | Mount | Routen |
|-----------|-------|--------|
| `onboarding_bp` | `/api/onboarding` | `GET /`, `PUT /step`, `POST /complete`, `POST /dismiss`, `POST /reopen` |
| `user_profile_bp` | `/api/profile` | `GET /`, `PUT /`, `POST /avatar`, `GET /avatar`, `DELETE /avatar` |

### Graph — `/api/graph` (`graph_bp`)

| Modul | Routen |
|-------|--------|
| `graph_projects.py` | `GET /project/list`, `GET /project/<id>`, `DELETE /project/<id>`, `POST /project/<id>/reset` |
| `graph_build.py` | `POST /build`, `POST /ontology/generate` |
| `graph_data.py` | `GET /data/<graph_id>`, `GET /snapshot/<id>/<round>`, `GET /<id>/diff`, `GET /<id>/export`, `DELETE /delete/<id>`, `GET /task/<task_id>`, `GET /tasks` |

### Simulation — `/api/simulation` (`simulation_bp`)

| Modul | Routen |
|-------|--------|
| `simulation_prepare.py` | `POST /prepare`, `POST /prepare/status` |
| `simulation_lifecycle.py` | `POST /create`, `GET /<id>`, `GET /list`, `GET /available-models` |
| `simulation_run.py` | `POST /start`, `POST /stop`, `POST /<id>/pause`, `POST /<id>/resume`, `POST /close-env`, `POST /env-status`, `GET /<id>/run-status`, `GET /<id>/run-status/detail`, `GET /<id>/actions`, `GET /<id>/agent-stats`, `GET /<id>/timeline`, `GET /<id>/console-log` |
| `simulation_stream.py` | `GET /<id>/stream` **(SSE)** |
| `simulation_entities.py` | `GET /entities/<graph_id>`, `GET /entities/<graph_id>/<uuid>`, `GET /entities/<graph_id>/by-type/<type>` |
| `simulation_profiles.py` | `GET /<id>/profiles`, `POST /<id>/profiles`, `PATCH /<id>/profiles/<username>`, `DELETE /<id>/profiles/<username>`, `POST /<id>/profiles/<username>/approve`, `POST /<id>/profiles/<username>/reject`, `POST /<id>/profiles/<username>/regenerate`, `GET /<id>/profiles/<username>/entity-context`, `GET /<id>/profiles/quality`, `GET /<id>/profiles/realtime`, `GET /<id>/config`, `GET /<id>/config/download`, `GET /<id>/config/realtime`, `POST /<id>/branch`, `GET /<id>/branches`, `GET /persona-library`, `POST /persona-library`, `DELETE /persona-library/<template_id>`, `GET /script/<name>/download` |
| `simulation_interviews.py` | `POST /interview`, `POST /interview/all`, `POST /interview/batch`, `POST /interview/history` |
| `simulation_history.py` | `GET /history`, `POST /generate-profiles`, `GET /<id>/posts`, `GET /<id>/comments`, `GET /<id>/feed-snapshot` |
| `simulation_metrics.py` | `GET /<id>/metrics`, `GET /<id>/metrics/export` |
| `simulation_compare.py` | `GET /<id>/compare` |
| `simulation_budget.py` | `POST /preflight-estimate` |

Prepare-Kollision: Aktiver Prepare-Task → HTTP 409 `simulation_prepare_in_progress`. Kein neuer Run/Task erzeugt.

### Report — `/api/report` (`report_bp`)

| Modul | Routen |
|-------|--------|
| `report.py` | `POST /generate`, `POST /generate/status`, `GET /list`, `GET /check/<sim_id>`, `GET /by-simulation/<sim_id>`, `GET /<id>`, `DELETE /<id>`, `GET /<id>/progress`, `GET /<id>/sections`, `GET /<id>/section/<i>`, `GET /<id>/evidence`, `GET /<id>/evidence/<section>`, `GET /<id>/evidence/<section>/<claim_id>`, `GET /<id>/export`, `GET /<id>/download`, `GET /<id>/agent-log`, `GET /<id>/agent-log/stream`, `GET /<id>/console-log`, `GET /<id>/console-log/stream`, `POST /chat`, `POST /tools/search`, `POST /tools/statistics` (22 Routen) |

`GET /<id>/export` nimmt `?format=md|json|csv|zip`. Agent-log/console-log `/stream`-Varianten liefern bisherigen Puffer als JSON-Envelope, kein SSE.

Evidence-Hinweis: Vertragswidrige Evidenz → **422** mit `reason=contract_violation`. ZIP enthaelt dann `evidence-omitted.json` statt `evidence-map.json`.

### Runs — `/api/runs` (`runs_bp`)

| Modul | Routen |
|-------|--------|
| `runs.py` | `GET /<run_id>`, `POST /<run_id>/cancel`, `POST /<run_id>/stop`, `POST /<run_id>/resume`, `GET /<run_id>/events`, `GET /<run_id>/export`, `GET /<run_id>/manifest`, `POST /<run_id>/replay`, `GET /<run_id>/usage` |
| `llm_routing.py` | `GET /<run_id>/llm-routing`, `PUT /<run_id>/llm-routing`, `PATCH /<run_id>/llm-routing/stages/<stage_id>` |

### LLM — `/api/llm` (`llm_bp`)

| Modul | Routen |
|-------|--------|
| `llm_providers.py` | `GET /providers`, `GET /providers/api-keys`, `GET /providers/<id>/models`, `GET /providers/<id>/has-key`, `GET /providers/<id>/api-key`, `POST,PUT /providers/<id>/api-key`, `DELETE /providers/<id>/api-key`, `POST /providers/<id>/test`, `GET /provider-connections`, `PUT /provider-connections/<id>`, `DELETE /provider-connections/<id>`, `GET /provider-connections/<id>/models`, `POST /provider-connections/<id>/test` |
| `llm_active.py` | `GET /active-config`, `PUT /active-config` |
| `llm_routing.py` | `GET /routing/defaults`, `PUT /routing/defaults`, `PUT /routing/defaults/global`, `PATCH /routing/defaults/stages/<id>` |
| `llm.py` | `GET /model-stream` **(SSE)** |
| `embedding_configurations.py` | `GET /embedding/configurations`, `GET /embedding/configurations/active`, `POST /embedding/configurations/sync-legacy`, plus per-config CRUD und test/activate |
| `embedding_migrations.py` | `POST /embedding/migrations`, `GET /embedding/migrations`, `GET /embedding/migrations/<job_id>`, `POST /embedding/migrations/<job_id>/run`, `POST /embedding/migrations/<job_id>/cancel`, `POST /embedding/ollama/pull` |

### LLM-Profile — `/api/settings/llm-profiles` (`llm_profiles_bp`)

| Modul | Routen |
|-------|--------|
| `llm_profiles.py` | `GET /`, `POST /`, `PUT /<profile_id>`, `DELETE /<profile_id>`, `POST /<profile_id>/default` |

### Settings — `/api/settings` (`settings_bp`)

| Modul | Routen |
|-------|--------|
| `settings.py` | `GET /`, `PUT /`, `GET /schema`, `PUT /secrets`, `GET /stream` |

### Status & Logs

| Blueprint | Mount | Routen |
|-----------|-------|--------|
| `status_bp` | `/api/status` | `GET /` |
| `logs_bp` | `/api/logs` | `GET /`, `GET /stream` **(SSE)** |

---

## SSE-Streams

| Stream | Endpunkt | Zweck |
|--------|----------|-------|
| Simulations-Events | `GET /api/simulation/<id>/stream` | Live-Agenten-/Interaktions-Events |
| Model-Active | `GET /api/llm/model-stream` | Aktive Modell-/Provider-Aenderungen |
| Backend-Logs | `GET /api/logs/stream` | Live-Log-Viewer |
| Settings | `GET /api/settings/stream` | Settings-Aenderungen |

SSE-Verbindungen authentifizieren ueber signierte Tickets, nicht Bearer-Header in URLs.

---

## Vertraege und Schemas

- Pydantic-Vertraege: [`../backend/app/contracts/`](../backend/app/contracts/)
- Frontend-Spiegel: [`../frontend/src/contracts/`](../frontend/src/contracts/) + generierte Schemas
- Schema-Drift-Gate: `uv run python -m app.contracts.dump_schemas --check`
- Fehler-Envelope: [`api-contracts.md`](api-contracts.md)
