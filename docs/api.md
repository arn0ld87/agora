# HTTP-API — Agora Backend

**Status:** Referenz zu Backend `0.9.4` (Stand 11.08.2026, Europe/Berlin). Diese Datei beschreibt die HTTP-Endpunkte nach Domänen (Übersicht, nicht jede Einzelroute). Für Response-Envelopes, `ApiErrorCode`-Katalog und Schema-Tests siehe [`api-contracts.md`](api-contracts.md). Für die Vertragsmodelle siehe [`../backend/app/contracts/`](../backend/app/contracts/) und die generierten Schemas via `uv run python -m app.contracts.dump_schemas`.

Quelle der Wahrheit für die Routen ist der Code in [`../backend/app/api/`](../backend/app/api/) (Blueprints registriert in [`../backend/app/__init__.py`](../backend/app/__init__.py)). Bei Änderungen am Code: diese Datei mit-pflegen, sonst driftet die Doku.

---

## Konventionen

- **Base URL:** Backend lauscht produktiv auf `:5001`, Frontend-Dev auf `:5173`. Alle fachlichen Endpunkte liegen unter `/api/*`.
- **Authentifizierung:** `Authorization: Bearer <AGORA_AUTH_TOKEN>` für `/api/*`-Aufrufe. SSE-Streams und Datei-Downloads nutzen zeitbegrenzte **signierte Tickets** — keine Plaintext-Tokens in URLs. Details: [`auth.md`](auth.md), [ADR-0001](decisions/0001-auth-model.md).
- **Response-Envelope:** JSON-API-Responses liefern `{"success": bool, "data"?, "code"?, "error"? …}`. Siehe [`api-contracts.md`](api-contracts.md). **Ausnahmen:** SSE-Streams (`text/event-stream`) und Export-/Download-Endpunkte (Markdown, CSV, ZIP, Binär) liefern rohe Responses ohne JSON-Envelope — nicht als Envelope dekodieren.
- **SSE-Streams:** Endpunkte mit `text/event-stream` sind unten mit **(SSE)** gekennzeichnet.
- **Fehlercodes:** semantische `ApiErrorCode`-Werte (z. B. `simulation_not_prepared`, `persona_review_required`, `neo4j_unavailable`) statt String-Matching — Katalog in [`api-contracts.md`](api-contracts.md).

---

## Domänen-Übersicht

13 Blueprints, 171 Routen (Zählung der Route-Dekoratoren unter `backend/app/api/`, Stand 11.08.2026). Mount-Pfade aus `app/__init__.py`.

### Auth & API-Keys

| Blueprint (Mount) | Modul | Auswahl |
|---|---|---|
| `auth_bp` — `/api/auth` | [`auth.py`](../backend/app/api/auth.py) | `POST /api/auth/ticket` — signiertes Ticket für SSE/Download |
| `api_keys_bp` — `/api/api-keys` | [`api_keys.py`](../backend/app/api/api_keys.py) | CRUD für API-Keys (5 Routen) |

### Onboarding & Profil

| Blueprint (Mount) | Modul | Auswahl |
|---|---|---|
| `onboarding_bp` — `/api/onboarding` | [`onboarding.py`](../backend/app/api/onboarding.py) | `GET`, `PUT /step`, `POST /complete`, `POST /dismiss`, `POST /reopen` |
| `user_profile_bp` — `/api/profile` | [`user_profile.py`](../backend/app/api/user_profile.py) | `GET`, `PUT`, `POST/GET/DELETE /avatar` |

### Graph — `/api/graph` (`graph_bp`)

| Modul | Auswahl |
|---|---|
| [`graph_projects.py`](../backend/app/api/graph_projects.py) | `GET /project/list`, `GET /project/<id>`, `DELETE /project/<id>`, `POST /project/<id>/reset` |
| [`graph_build.py`](../backend/app/api/graph_build.py) | `POST /build`, `POST /ontology/generate` |
| [`graph_data.py`](../backend/app/api/graph_data.py) | `GET /data/<graph_id>`, `GET /snapshot/<id>/<round>`, `GET /<id>/diff`, `GET /<id>/export`, `DELETE /delete/<id>`, `GET /task/<task_id>`, `GET /tasks` |
| [`graph.py`](../backend/app/api/graph.py) | Graph-Grundrouten |

### Simulation — `/api/simulation` (`simulation_bp`)

| Modul | Auswahl |
|---|---|
| [`simulation_prepare.py`](../backend/app/api/simulation_prepare.py) | `POST /prepare`, `POST /prepare/status` |
| [`simulation_lifecycle.py`](../backend/app/api/simulation_lifecycle.py) | Start/Stop/Cancel/Resume |
| [`simulation_run.py`](../backend/app/api/simulation_run.py) | Simulationsausführung |
| [`simulation_stream.py`](../backend/app/api/simulation_stream.py) | `GET /<simulation_id>/stream` **(SSE)** |
| [`simulation_entities.py`](../backend/app/api/simulation_entities.py) | Entity-Routen (3) |
| [`simulation_profiles.py`](../backend/app/api/simulation_profiles.py) | Simulationsprofile |
| [`simulation_interviews.py`](../backend/app/api/simulation_interviews.py) | 1-zu-1-Gespräche / Umfragen |
| [`simulation_history.py`](../backend/app/api/simulation_history.py) | Historie |
| [`simulation_metrics.py`](../backend/app/api/simulation_metrics.py) | `GET /<id>/metrics`, `GET /<id>/metrics/export` |
| [`simulation_compare.py`](../backend/app/api/simulation_compare.py) | `GET /<id>/compare` (Branch-Compare, #66) |
| [`simulation_budget.py`](../backend/app/api/simulation_budget.py) | `POST /preflight-estimate` (Token-/Kosten-/Laufzeit-Schätzung vor Run-Start, #764) |

Budget-Hinweis (#764, [ADR-0012](decisions/0012-run-budgets.md)): `POST /prepare` und `POST /start` akzeptieren ein optionales `budget`-Objekt (Contract `run-budget-config.schema.json`: `max_tokens`, `max_cost_micros`, `max_duration_seconds`, `max_llm_calls`, `enforcement` soft/hard, `currency`). Report-Generierung erbt das Budget der zugehörigen Simulation.

Prepare-Kollision (#1271): Läuft für dieselbe Simulation bereits ein Prepare-Task (`status=preparing`), antwortet `POST /prepare` mit HTTP 409 und `code=simulation_prepare_in_progress`. Dabei wird kein weiterer Run oder Task erzeugt; `force_regenerate` ändert daran nichts.

### Report — `/api/report` (`report_bp`)

| Modul | Auswahl |
|---|---|
| [`report.py`](../backend/app/api/report.py) | `POST /generate`, `POST /generate/status`, `GET /<id>`, `GET /by-simulation/<sim_id>`, `GET /list`, `GET /<id>/evidence`, `GET /<id>/evidence/<section>`, `GET /<id>/evidence/<section>/<claim_id>`, `GET /<id>/export`, `GET /<id>/download`, `DELETE /<id>`, `POST /chat`, `GET /<id>/progress`, `GET /<id>/sections`, `GET /<id>/section/<i>`, `GET /check/<sim_id>`, `GET /<id>/agent-log`, `GET /<id>/agent-log/stream`, `GET /<id>/console-log`, `GET /<id>/console-log/stream`, `POST /tools/search`, `POST /tools/statistics` (22 Routen) |

`GET /<id>/export` nimmt `?format=md|json|csv|zip`; `/agent-log/stream` und `/console-log/stream` sind **kein** SSE, sondern liefern den bisherigen Logpuffer als JSON-Envelope.

Export-Hinweis (#764): ZIP-Exporte (`/export`, `/download`) enthalten zusätzlich `usage.json` (Verbrauch) und `budget.json` (Limits + Warnungen) des Report-Runs, secretsfrei. `POST /generate` akzeptiert ein optionales `budget`-Objekt (`run-budget-config.schema.json`); ohne Angabe erbt der Report-Run das Budget der Simulation.

Evidence-Hinweis ([#1160](https://github.com/arn0ld87/agora/issues/1160) G): vertragswidrige Evidenz verlässt das System in keinem Format als scheinbar geprüfte Datei. `GET /<id>/evidence`, die Claim-Sub-Route und der Claims-CSV-Abruf antworten dann mit **422** und `reason=contract_violation` — derselbe Grund, den auch der JSON-Envelope trägt; das ZIP enthält in diesem Fall `evidence-omitted.json` statt `evidence-map.json`/`claims.csv`.

### Runs — `/api/runs` (`runs_bp`)

| Modul | Auswahl |
|---|---|
| [`runs.py`](../backend/app/api/runs.py) | Run-Status, Run-Verwaltung; `GET /<run_id>` reichert `budget`/`usage`/`termination_reason` an (#764), `GET /<run_id>/usage` (Verbrauchsaufstellung) |
| [`llm_routing.py`](../backend/app/api/llm_routing.py) | `GET/PUT /<run_id>/llm-routing`, `PATCH /<run_id>/llm-routing/stages/<stage_id>` |

### LLM — `/api/llm` (`llm_bp`)

| Modul | Auswahl |
|---|---|
| [`llm_providers.py`](../backend/app/api/llm_providers.py) | Provider-CRUD (13 Routen) |
| [`llm_active.py`](../backend/app/api/llm_active.py) | `GET/PUT /active-config` |
| [`llm_routing.py`](../backend/app/api/llm_routing.py) | `GET/PUT /routing/defaults`, `PATCH /routing/defaults/stages/<id>`, `PUT /routing/defaults/global` |
| [`llm.py`](../backend/app/api/llm.py) | Model-Active **(SSE)** (#213) |
| [`embedding_configurations.py`](../backend/app/api/embedding_configurations.py) | `GET /embedding/configurations`, `/active`, `/<id>` GET/PUT/DELETE, `/<id>/test`, `/<id>/activate` |
| [`embedding_migrations.py`](../backend/app/api/embedding_migrations.py) | Embedding-Re-Index-Migrations-Lifecycle (ADR-0007) |

### LLM-Profile — `/api/settings/llm-profiles` (`llm_profiles_bp`)

| Modul | Auswahl |
|---|---|
| [`llm_profiles.py`](../backend/app/api/llm_profiles.py) | CRUD, `POST /<profile_id>/default` (7 Routen) |

### Settings — `/api/settings` (`settings_bp`)

| Modul | Auswahl |
|---|---|
| [`settings.py`](../backend/app/api/settings.py) | App-Settings (#133) |

### Status & Logs

| Blueprint (Mount) | Modul | Auswahl |
|---|---|---|
| `status_bp` — `/api/status` | [`status.py`](../backend/app/api/status.py) | System-/Run-Status |
| `logs_bp` — `/api/logs` | [`logs.py`](../backend/app/api/logs.py) | `GET`, `GET /`, `GET /stream` **(SSE)** (#132) |

---

## SSE-Streams

| Stream | Endpunkt | Zweck |
|---|---|---|
| Simulations-Events | `GET /api/simulation/<id>/stream` | Live-Interaktions-/Agenten-Events |
| Model-Active | `GET /api/llm/model-stream` (#213) | Aktive Modell-/Provider-Selection |
| Backend-Logs | `GET /api/logs/stream` | Live-Log-Viewer |

SSE-Verbindungen authentifizieren sich über signierte Tickets (siehe [`auth.md`](auth.md)), nicht über Bearer-Header in der URL.

---

## Verträge und Schemas

- Pydantic-Verträge: [`../backend/app/contracts/`](../backend/app/contracts/) — SSoT für Request-/Response-Shapes.
- Frontend-Spiegel: [`../frontend/src/contracts/`](../frontend/src/contracts/) und generierte Schemas.
- Schema-Drift-Gate: `uv run python -m app.contracts.dump_schemas --check` (siehe [`runbooks/pre-push-gate.md`](runbooks/pre-push-gate.md)).
- Fehler-Envelope und `ApiErrorCode`: [`api-contracts.md`](api-contracts.md).
