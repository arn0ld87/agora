# Frontend-Next-Brief — Agora React-Redesign

**Status:** Entwurf / Analyse-Ergebnis, noch kein Lovable-Projekt angelegt, keine Umsetzung gestartet.
**Erstellt:** 2026-07-16, Branch `feat/frontend-next`.
**Quelle:** code-review-graph + gezielte Datei-Reads gegen `main`-Stand von `frontend/`, `backend/app/api/`, `backend/app/contracts/`, `docs/auth.md`, `README.md`, `deploy/nginx/agora.conf`.

Zielarchitektur laut Auftrag: eigenständige React-Vite-SPA (TypeScript strict) als Lovable-Projekt,
kein Lovable Cloud, kein Supabase, keine neue DB, kein eigener Backend-Code, Zugriff nur relativ
über `/api`, Mock-API mit Umschaltung auf echte Agora-API, keine fest eingebauten Tokens/Secrets im
Bundle, späterer Betrieb hinter dem vorhandenen nginx-Reverse-Proxy. Bestehendes Flask/Neo4j/Redis/
Ollama-Backend bleibt unverändert; das alte Vue-Frontend bleibt als Referenz/Fallback bestehen.

## 0. Vorab-Befund: `frontend-next/`-Namenskollision

Im Repo liegt bereits ein untracked `frontend-next/`-Verzeichnis — es ist ausschließlich das
unveränderte `npm create vite@latest -- vue-ts`-Scaffold (`package.json` mit `"vue": "^3.5.39"`,
Default-`main.ts`, Boilerplate-README, keine eigene Logik). Kollidiert im Namen, nicht im Inhalt,
mit der geplanten React-SPA. Da Lovable-Projekte remote in Lovables Cloud-Infrastruktur leben, ist
diese lokale Ordnerkollision funktional folgenlos — sie ist nur ein Dokumentations-/Mental-Model-
Stolperstein. Keine Aktion vorgenommen; falls ein lokaler Sync-Ordner mit demselben Namen später
gebraucht wird, vorher entscheiden: löschen, umbenennen oder ignorieren.

## 1. Benutzerabläufe (User Flows)

| Flow | Schritte | Primäre Views (Ist-Zustand) |
|---|---|---|
| Onboarding | Welcome → Profil → Provider wählen → Chat-Modell → Embedding-Modell → Privacy → Summary. Resumierbar über `OnboardingState.current_step`, Pflicht-Steps: `profile, chat_model, embeddings`. | `views/onboarding/OnboardingView.vue` |
| Projekt/Input anlegen | Dokument(e) hochladen (Multipart) → Ontologie generieren → Graph bauen (Task-Polling) | `views/MainView.vue` (`/process/:projectId`) |
| Persona-Erzeugung & Review | Quoten planen → Personas generieren → einzeln approven/rejecten/regenerieren, Branching möglich | `views/SimulationView.vue`, `simulation_profiles.py` (17 Routen) |
| Simulation starten & verfolgen | Start → Live-Feed via SSE (`post_created`) → Pause/Resume/Stop → Timeline/Agent-Stats | `views/SimulationRunView.vue`, `views/v4/steps/StepSimulationFeedView.vue` |
| Report generieren & lesen | Generate (mode: strict/balanced/explorative) → Progress-Poll → Sections/Evidence/Claims lesen → Chat mit Report-Agent | `views/ReportView.vue`, `views/InteractionView.vue` |
| Export/Download | Report als PDF/ZIP/CSV, Simulation-Config/Script als signierter Download | `report.py::/export`, `/download`; `simulation_profiles.py::/config/download`, `/script/.../download` |
| Runs-Dashboard | Liste aller Runs (Graph-Build, Simulation, Report), Filter nach Status, Live-Updates via SSE | `views/RunsView.vue` (`/runs`), `views/RunDetailView.vue` (`/runs/:id`) |
| Compare | Zwei Runs/Graph-Versionen gegenüberstellen (Diff) | `views/v4/CompareView.vue`, `graph_data.py::/diff` |
| Settings — Provider/Modelle | Provider-Connections anlegen/testen, Modelle je Stage routen, Embedding-Konfiguration + Migration | `Settings/LlmProvidersView.vue`, `LlmRoutingView.vue`, `EmbeddingConfigurationsView.vue` |
| Settings — Profil/API-Keys/Audit | Avatar, Sprache, Theme, Privacy; Workspace-API-Keys erzeugen/widerrufen; Audit-Log einsehen | `SettingsProfileView.vue`, `SettingsApiKeysView.vue`, `SettingsAuditLogsView.vue` |
| Auth-Bootstrap | Kein Login-Flow (Single-User) — Token wird einmalig gesetzt (Env/localStorage/Memory), Router-Guard blockt `requiresAuth`-Routen ohne Token | `router/index.ts:1355` |

**Strukturbefund:** Es existieren drei parallele View-Generationen im selben Baum — Flat-Legacy
(`views/*.vue`), `views/v4/*` (App-Shell-Redesign) und `views/agora2026/*` (weiterer Prototyp).
Vor Umsetzungsbeginn klären, welche Generation als fachliche Referenz gilt (vermutlich `v4`,
da zuletzt aktiv weiterentwickelt — unverifizierte Annahme).

## 2. Benötigte Seiten (React-Zielstruktur, aus Routen abgeleitet)

| Route | Zweck |
|---|---|
| `/` → Dashboard | Runs-Übersicht, Health/Status |
| `/onboarding` | Setup-Wizard |
| `/process/:projectId` | Upload + Graph-Build |
| `/simulation/:id` | Persona-Review, Branching |
| `/simulation/:id/start` | Live-Run + Feed |
| `/report/:reportId` | Report-Lesen, Evidence-Drilldown |
| `/interaction/:reportId` | Chat mit Report-Agent |
| `/runs`, `/runs/:id` | Runs-Liste/-Detail |
| `/compare/:simulationId` | Graph-/Report-Diff |
| `/history` | Historische Runs |
| `/settings/*` | general, integrations, profile, api-keys, audit-logs, llm-routing, llm-providers, embedding-configurations |
| 404 | Fallback |

## 3. Vom Frontend verwendete API-Endpunkte (vollständig, nach Blueprint)

Alle Prefixe aus `backend/app/__init__.py:345-357`:

| Blueprint | Prefix | Kernrouten (Auswahl der für Flows relevanten) |
|---|---|---|
| `auth_bp` | `/api/auth` | `POST /ticket` |
| `onboarding_bp` | `/api/onboarding` | `GET ""`, `PUT /step`, `POST /complete`, `POST /dismiss`, `POST /reopen` |
| `graph_bp` | `/api/graph` | `POST /ontology/generate` (Multipart-Upload), `POST /build`, `GET /task/:id`, `GET /tasks`, `GET /data/:graph_id`, `GET /:graph_id/diff`, `GET /:graph_id/export`, `GET/DELETE /project/*` |
| `simulation_bp` | `/api/simulation` | `GET /available-models`, `POST /create`, `GET /:id`, `GET /list`, `POST /prepare[/status]`, `POST /start`, `POST /stop`, `POST /:id/pause\|resume`, `GET /:id/run-status[/detail]`, `GET /:id/stream` (SSE), `GET /:id/timeline`, `GET /:id/agent-stats`, `GET /:id/compare`, 17 Profile-Routen (`/:id/profiles*`, `/persona-library*`), `GET /:id/metrics[/export]`, `GET /:id/config[/download]`, `GET /script/:name/download` |
| `report_bp` | `/api/report` | `POST /generate`, `GET /:id`, `GET /by-simulation/:simId`, `GET /list`, `GET /:id/evidence[...]`, `GET /:id/export`, `GET /:id/download`, `POST /chat`, `GET /:id/progress`, `GET /:id/sections`, `GET /:id/agent-log[/stream]`, `GET /:id/console-log[/stream]` |
| `runs_bp` | `/api/runs` | `GET ""`, `GET /:id`, `GET /:id/events`, `POST /:id/stop\|cancel\|resume`, `GET/PUT /:id/llm-routing[/stages/:id]` |
| `status_bp` | `/api/status` | `GET ""` |
| `logs_bp` | `/api/logs` | `GET ""`, `GET /stream` (SSE) |
| `settings_bp` | `/api/settings` | `GET/PUT ""`, `GET /schema`, `PUT /secrets`, `GET /stream` (SSE) |
| `llm_bp` | `/api/llm` | `GET /model-stream` (SSE), `GET/PUT /active-config`, `GET/PUT/DELETE /provider-connections[/:id]`, `POST .../test`, `GET .../models`, Legacy `/providers*`, `GET/PUT /routing/defaults[...]`, `GET/POST .../embedding/configurations*`, `GET/POST .../embedding/migrations*` |
| `llm_profiles_bp` | `/api/settings/llm-profiles` | CRUD + `/:id/default` |
| `api_keys_bp` | `/api/api-keys` | `GET/POST ""`, `DELETE /:id` |
| `user_profile_bp` | `/api/profile` | `GET/PUT ""`, `POST/GET/DELETE /avatar` |

**Doppelte Provider-API:** `llm_providers.py` exponiert sowohl den kanonischen Pfad
`/provider-connections` als auch einen Legacy-Pfad `/providers` parallel — im Rewrite nur
`provider-connections` + `AiRoute`/`AiModel` (kanonischer Contract) verwenden.

## 4. Request-/Response-Verträge (Kernmodelle)

Backend = Pydantic v2 (`backend/app/contracts/`, größtenteils `extra="forbid"`), Frontend-Spiegel =
Zod (`frontend/src/contracts/`). Zwei Contracts sind kein 1:1-Spiegel:

- **`ReportV3`** (`report_v3.py` ↔ `reportV3Contract.ts`): 1:1, `schema_version: 3`, 11 fachliche
  Listen (Personas, Segments, Claims, Multipliers, FrictionPoints, TrustSignals,
  ChangeRecommendations, ProjectImpacts, PositioningVariants, ContentIdeas, DataGaps) +
  `hypotheses[]` (eigener Slot, MAI-03) + `model_attribution[]` + `red_team_findings[]` (max 10).
  `Claim.evidence_refs` ist Pflicht (min_length=1) — Kernanker von ADR-0002.
- **`RunDetail`/`RunsListResponse`** (`runs_contract.py` ↔ `runsContract.ts`): bewusst
  `extra="allow"` (Zod `.passthrough()`), `RunStatus` genau 6 Werte
  (`pending|processing|paused|completed|failed|stopped`).
- **`AiRoute`/`AiModel`/`ProviderConnection`** (`ai_provider_contract.py`, kanonisch laut AGENTS.md)
  vs. **`AiModelRef`** (`aiModelRef.ts`, bewusst entkoppelt, eigenes `AiModelSourceSchema`-Enum mit
  Bindestrich-Naming statt Unterstrich). Entscheidung nötig: kanonischen `AiRoute` direkt übernehmen
  (empfohlen — weniger Adapter-Schulden) oder `AiModelRef` + Adapter neu bauen.
- **`OnboardingStatusResponse`**: Abweichung — Backend `embedding_source: str` (offen), Frontend
  `z.enum(['store','legacy','none'])` (geschlossen). Frontend ist strenger als Backend.
- **`PostCreatedEvent`** (`post_event_contract.py`, `frozen=True`): SSE-Payload für Live-Posts,
  `sentiment: float|None (-1..1)`, `sim_time` muss tz-aware sein.
- **`/api/status`**: kein Pydantic-Contract im Backend — nur lose Zod-`.passthrough()`-Hülle im
  Frontend. Response-Form im Rewrite nicht als stabil annehmen.
- **`settings_contract.py`**: dynamisch zur Laufzeit aus `settings_schema.py` generiert
  (`pydantic.create_model`), kein statisches Schema — Frontend bildet 13 Sektionen
  (`llm, neo4j, embedding, ontology, hybrid_search, agent_tools, event_bus, logging, locale, ui,
  webtools, oasis, security`) manuell nach.

## 5. Authentifizierung (X-Agora-Token)

Quelle: `docs/auth.md`, `frontend/src/api/index.ts`.

- **Header:** `X-Agora-Token: <token>` (primär, Axios-Interceptor hängt ihn automatisch an),
  Fallback `Authorization: Bearer <token>`. Backend-Vergleich timing-safe (`hmac.compare_digest`).
- **Storage-Modi** (`VITE_AGORA_TOKEN_STORAGE`):
  - `localStorage` (Dev-Default) — überlebt Reload, XSS-Risiko.
  - `memory` (Prod-Empfehlung) — nur JS-Heap, kein Reload-Überleben, räumt aktiv
    `localStorage.agora_token` weg.
  - HttpOnly-Cookie — nicht implementiert, nur Zielarchitektur (kein `/api/auth/login`, kein CSRF).
- **Kein Login-Endpoint.** Single-User-Modell: Token wird extern gesetzt.
- **Router-Guard:** ohne Token bei `requiresAuth`-Route → Redirect mit `?authRequired=1&next=<path>`.
- **Response-Envelope:** `success:false` (auch in 2xx-Hülle) → `ApiError{code, status, message,
  details}`. Sollte im React-Data-Layer 1:1 übernommen werden.

## 6. Signierter Ticket-Flow für SSE

Quelle: `backend/app/api/auth.py`, `useApiAuth.ts`, `stream.ts`.

1. `POST /api/auth/ticket` mit Header-Auth (`X-Agora-Token`), Body `{scope, ttl_seconds}`.
2. Erlaubte Scope-Präfixe: `sse:`, `settings-stream`, `download:report:`,
   `download:simulation_config:`, `download:simulation_script:`, `logs:stream`, `llm-stream`.
3. TTL: Default 60s, Max 300s. Rate-Limit (429 + `Retry-After`).
4. Response: `{ticket: "v1.<exp>.<scope>.<sig>", exp: <unix>}` — HMAC-signiert mit `SECRET_KEY`.
5. Client hängt `?ticket=<signed>` an die URL an. Backend prüft Signatur und Scope. Das Ticket-Verhalten unterscheidet sich nach Scope:
   - **Download-Endpunkte** (z. B. `download:report:`, `download:simulation_config:`, `download:simulation_script:`) sind Einweg-Tickets (`single_use=True`). Sie werden beim ersten Aufruf konsumiert und sind danach ungültig (Redis-gesichert, Multi-Worker-safe mit In-Memory-Fallback).
   - **SSE- & Stream-Endpunkte** (z. B. `sse:`, `settings-stream`, `logs:stream`, `llm-stream`) setzen im Backend `single_use=False`. Sie sind TTL-begrenzt, aber innerhalb der TTL mehrfach verwendbar, damit automatische `EventSource`-Reconnects des Clients im Fehlerfall keinen fälschlichen 401-Fehler auslösen. Der Replay-Schutz erfolgt hier primär über die kurze Gültigkeit (TTL).
6. Client-Cache pro Scope, 5s-Vorlauf vor `exp`, In-Flight-Dedup.
7. 401-Retry: einmaliger Cache-Invalidate + Refetch, zweites 401 propagiert.
8. `?token=<bearer>` ist deprecated aber noch aktiv (Warning-Log) — im Rewrite nicht neu verwenden.

## 7. SSE-Eventtypen

| Event | Payload | Quelle |
|---|---|---|
| `hello` | `{simulation_id, ts}` | einmalig bei Connect |
| `ping` | `{ts}` | Heartbeat alle ~15s |
| `state` | `{type, simulation_id, payload, ts}` — Run-State-Snapshot | Backend-dokumentiert |
| `control` | `{type, simulation_id, payload, ts}` — `{paused, stop_requested, ...}` | Backend-dokumentiert |
| `post_created` | `PostCreatedEvent` (Zod-validiert, Envelope wird ausgepackt) | Slice 5-pre, OASIS-Runner |
| `error` (kein Named-Event) | `source.onerror` | Standard-EventSource |

Transport: `Last-Event-ID` wird geloggt, aber kein Replay. Response-Header:
`Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`, `Connection: keep-alive`.
nginx hat einen eigenen `location /api/simulation/`-Block vor `location /api/` mit
`proxy_buffering off`, `proxy_read_timeout 600s` — bei neuem Reverse-Proxy-Setup übernehmen.

## 8. Upload-/Download-Abläufe

**Upload** (`POST /api/graph/ontology/generate`, `backend/app/api/graph_build.py:83-152`):
- Multipart-Feld `files` (mehrere Dateien, `request.files.getlist('files')`).
- Form-Felder: `simulation_requirement` (Pflicht), `project_name` (Default `"Unnamed Project"`),
  `additional_context`, optional `llm_model`, `llm_provider` (JSON-String), `llm_profile_id`.
- Größenlimit pro Datei: `Config.AGORA_MAX_UPLOAD_SIZE_MB` → `413 UPLOAD_TOO_LARGE` bei Überschreitung
  (Projekt wird dabei automatisch wieder gelöscht). nginx-seitig zusätzlich `client_max_body_size 50M`.
- Rate-Limit über `AGORA_UPLOAD_RATE_LIMIT_MAX`/`_WINDOW_SECONDS`.
- Fehlerfälle: `400 VALIDATION_FAILED` (fehlende Requirement/Dateien, ungültiges `llm_provider`-JSON),
  `400 UNSUPPORTED_FORMAT` (keine Datei erfolgreich verarbeitet).

**Downloads** (Ticket-scoped, siehe Abschnitt 6):
- `download:report:` → `GET /api/report/:id/export`, `GET /api/report/:id/download`
- `download:simulation_config:` → `GET /api/simulation/:id/config/download`
- `download:simulation_script:` → `GET /api/simulation/script/:name/download`
- CSV-Export (`ReportExportService.build_csv_export`) und gestreamtes ZIP-Bundle mit
  Größen-Schwellen (`_ZIP_STREAM_THRESHOLD_BYTES`, `_ZIP_HARD_CAP_BYTES`) für große Reports.
- Browser können keine Custom-Header an `<a href>`/Downloads anhängen → derselbe Ticket-Mechanismus
  wie SSE.

## 9. Fehlercodes und Loading-States

| Code | Bedeutung | Quelle |
|---|---|---|
| `429` | Rate-Limit (Ticket-Endpoint, Report-Generate/Chat, Upload) | `json_error(RATE_LIMITED, 429, extra={retry_after_seconds})` + `Retry-After`-Header |
| `400` | `invalid_scope`, `invalid_ttl` (Ticket), `VALIDATION_FAILED`, `UNSUPPORTED_FORMAT` (Upload) | `auth.py`, `graph_build.py` |
| `401` | Token ungültig/abgelaufen → einmaliger Ticket-Refresh, danach propagiert | `useApiAuth._is401` |
| `413` | `UPLOAD_TOO_LARGE` | `graph_build.py` |
| `500` | `no_secret` (SECRET_KEY fehlt) | `auth.py` |
| `INVALID_ID` | ungültiges `simulation_id`-Format | `simulation_stream.py` |
| `timeout` / `service_unavailable` (Client-Codes) | Timeout bzw. Network Error ohne Backend-Envelope | `api/index.ts` |

**Retry-Logik** (`requestWithRetry`): Nur transporthinweisende oder serverseitige Fehler (`timeout`, `service_unavailable`, `5xx`) sind prinzipiell retry-fähig (3 Versuche, exponentielles Backoff `1000 * 2^i`). Client-Fehler (`4xx`) bubbeln generell sofort hoch.
- **Wichtig für die Datensicherheit:** Automatische Retries bei Timeouts oder `5xx` dürfen **nur für idempotente Methoden** (`GET`, `PUT`, `DELETE` sowie explizit idempotente `POST`s wie Onboarding-Dismiss/Step) durchgeführt werden.
- Bei **non-idempotenten `POST`-Anfragen** (z. B. Generierung von Ontologien/Graphen, Persona-Erstellung, Report-Generierung) darf der Client bei einem Timeout/Network Error/5xx **keinen automatischen Retry** initiieren. Andernfalls drohen doppelte Datenbank-Einträge oder unnötige LLM-Kosten, falls das Backend die Anfrage bereits verarbeitet hatte, die Antwort den Client aber nicht mehr erreichte. Fehler bei non-idempotenten POSTs müssen stattdessen sofort dem Benutzer gemeldet werden.
- Diese idempotenz-bewusste Retry-Logik ist 1:1 in den React-Data-Layer zu übernehmen (z. B. über den `retry`-Callback in React-Query).

**Loading-States:** kein zentrales State-Machine-Contract gefunden. Graph-Build/Ontologie-Generierung
nutzt Task-Polling (`GET /graph/task/:id`), Runs nutzen `RunStatus`-Enum + SSE-Push, Report nutzt
`/progress`-Polling **und** `/agent-log/stream` SSE parallel.

## 10. Empfohlene Umsetzungsreihenfolge

1. **Contracts-Schicht zuerst**: Backend-Pydantic-Modelle 1:1 nach TS/Zod übertragen — beginnend mit
   `ReportV3`, `RunDetail`/`RunsListResponse`, `AiRoute`/`AiModel`/`ProviderConnection` (kanonisch,
   nicht `AiModelRef` neu erfinden), `PostCreatedEvent`, `UserProfile`/`OnboardingState`. Klärt den
   `embedding_source`-Enum-Drift und ob `/api/status` einen echten Contract bekommt.
2. **Auth + Ticket-Client**: Fetch/Axios-Wrapper mit `X-Agora-Token`-Interceptor + Error-Envelope-
   Unwrapping, dann `fetchTicket`/`withFreshTicket`-Äquivalent (Cache + In-Flight-Dedup + 401-Retry).
3. **Mock-Mode-Umschaltung**: MSW o. ä. gegen dieselben Zod-Schemas aus Schritt 1, damit die
   Lovable-Preview ohne Backend lauffähig ist und später nahtlos auf `/api` (relativ) umschaltet.
4. **Runs-Dashboard + Run-Detail**: kleinster geschlossener Flow mit Read-Only-SSE (`state`/`control`),
   `RunDetailView.vue` gibt bereits ein sauberes Contract-first-Muster vor.
5. **Onboarding**: reine REST-Calls, keine SSE — validiert Contract-Layer + Routing-Guard-Pattern.
6. **Simulation-Flow** (Start → Live-Feed → Persona-Review): größte SSE-Oberfläche, danach
   Ticket-Flow vollständig verifiziert.
7. **Report + Interaction (Chat)**: hängt von Simulation-Flow ab, bringt Export/Download-Flow mit.
8. **Settings** (Provider/Routing/Embedding): komplexeste Contracts, bewusst spät — Legacy-Adapter
   (`llm_profile_to_canonical` etc.) sind laut AGENTS.md noch in Migration (Phase F, #669–#671 offen).
9. **Compare/History**: nice-to-have, keine harten Abhängigkeiten.

**Offene Punkte vor Umsetzungsstart:**
- Ob `AiModelRef` (Frontend-eigen) oder `AiRoute` (Backend-kanonisch) die Zielabstraktion für React wird.
- Schicksal von `views/agora2026/*` — dritter Prototyp, unklar ob aktiv oder tot.
- Schicksal von `frontend-next/`-Namenskollision (Abschnitt 0).
