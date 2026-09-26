# HTTP-API — Agora Backend

**Stand:** 20.09.2026  
**Geprüfte Main-Baseline:** `b62aea62`  
**Backend:** `0.9.6`

Diese Datei ist eine **Domänenübersicht**, keine handgepflegte vollständige Routenliste. Quelle der Wahrheit für konkrete Routen ist [`../backend/app/api/`](../backend/app/api/) mit der Blueprint-Registrierung in [`../backend/app/__init__.py`](../backend/app/__init__.py). Response-Verträge und Fehlerkonventionen: [`api-contracts.md`](api-contracts.md).

---

## Konventionen

- **Backend:** standardmäßig Port `5001`; Frontend-Dev standardmäßig `5173`.
- **Fachliche API:** überwiegend `/api/*`.
- **Auth:** bevorzugt `Authorization: Bearer <token>`; `X-Agora-Token` bleibt kompatibel. Workspace/API-Keys können über `X-Agora-Api-Key` bzw. Bearer laufen. Details: [`auth.md`](auth.md).
- **SSE/Downloads:** nutzen dort, wo Browser-APIs keine Custom-Header erlauben, signierte kurzlebige Tickets statt Klartext-Mastertokens in URLs.
- **JSON-Envelopes:** reguläre API-Endpunkte verwenden strukturierte Success-/Error-Envelopes; Streams und Datei-Exporte sind bewusst Ausnahmen.
- **Contracts-first:** neue oder geänderte JSON-Grenzen bekommen Pydantic-v2-Vertrag, Zod-Spiegel und JSON-Schema im selben Slice.

---

## Domänen

### Auth & API-Keys

Mounts unter `/api/auth` und `/api/api-keys`.

Wichtige Funktionen:

- signierte Tickets für Browser-Streams/Downloads
- API-Key-Erzeugung, Widerruf und Scope-Prüfung
- Mastertoken-/API-Key-Auflösung über die zentrale Auth-/Scope-Schicht
- `GET /api/auth/config` (öffentlich): `auth_backend`, `jwt_enabled` und nur bei aktivem JWT `supabase_url` und `supabase_anon_key` für den Browser-Client. Kein Geheimnis (#1616).

### Workspaces — `/api/workspaces` (#1616)

Der aktive Workspace kommt immer aus dem Principal (`X-Agora-Workspace`, vom Guard gegen die Mitgliedschaft geprüft), nie aus dem Pfad.

| Methode und Pfad | Wer | Wirkung |
|---|---|---|
| `GET /api/workspaces` | jeder angemeldete Nutzer, auch ohne Workspace | eigene Workspaces mit Rolle; Betreiber sehen den Default-Workspace |
| `POST /api/workspaces/bootstrap` | Supabase-Nutzer | legt beim ersten Aufruf genau einen persönlichen Workspace an (Owner), danach idempotent (`created: false`). Body optional `{"name": "..."}`. Betreiber: `400 not_applicable` |
| `GET /api/workspaces/current/members` | jedes Mitglied | Mitglieder des aktiven Workspace |
| `PUT /api/workspaces/current/members/<user_id>` | Owner, Admin | Mitglied anlegen oder Rolle ändern, Body `{"role": "owner"\|"admin"\|"member"\|"viewer"}` |
| `DELETE /api/workspaces/current/members/<user_id>` | Owner, Admin, jeder für sich selbst | Mitglied entfernen, Antwort `{"user_id": ...}` (`WorkspaceMemberRemoval`) |

Regeln: Owner-Rollen vergibt und entzieht nur ein Owner (`403 owner_required`); der letzte Owner bleibt (`409 last_owner`); Member und Viewer verwalten niemanden (`403 role_required`). Ein neues Mitglied muss in `auth.users` existieren (`404 not_found`), ist `auth.users` nicht lesbar: `503 user_directory_unavailable`. Ohne `DATABASE_URL` antworten Bootstrap und Mitgliederpfade mit `503 workspaces_unavailable`. Ein Body, der kein JSON-Objekt ist, ergibt `400`. `POST`, `PUT` und `DELETE` sind rate-limitiert (`AGORA_WORKSPACE_RATE_LIMIT_*`, `429` mit `Retry-After`), erst nach dem Guard und je Nutzer; Anfragen ohne gültige Anmeldung zählen nicht.

### Onboarding & Profil

Mounts unter `/api/onboarding` und `/api/profile`.

- Onboarding-Status und Schritte
- Profil- und Avatarverwaltung

### Graph — `/api/graph`

Module:

- `graph_projects.py` — Projekt-/Graph-Metadaten und Reset/Delete
- `graph_build.py` — Graph-Build und Ontologie-Generierung
- `graph_data.py` — Graphdaten, Snapshots, Diff, Export und Task-Sichten

Langlaufende Graph-Jobs werden über die Run-/Task-Infrastruktur sichtbar gemacht. Restart-/SIGTERM-Semantik für daemonisierte Graph-Build-Threads ist als Teil von #1472 noch nicht vollständig gelöst. `GET /api/graph/task/<task_id>` und `GET /api/graph/tasks` serialisieren seit #1466 über den Pydantic-Vertrag `TaskStatusResponse` (Spiegel von `Task.to_dict()`, inklusive `message_key`).

### Simulation — `/api/simulation`

Die Simulations-API ist nach Verantwortlichkeiten aufgeteilt:

- `simulation_lifecycle.py` — Create/List/Detail/Model-Verfügbarkeit
- `simulation_prepare.py` — Prepare und Prepare-Status
- `simulation_run.py` — Start/Stop/Pause/Resume/Run-Status/Aktionen/Logs
- `simulation_stream.py` — Live-Stream
- `simulation_entities.py` — Graph-Entitäten für Simulation/Persona-Setup
- `simulation_profiles.py` — Profile, Review, Qualität, Branching, Persona-Library
- `simulation_interviews.py` — Interviews
- `simulation_history.py` — historische Posts/Kommentare/Feeds und Profilgenerierung
- `simulation_metrics.py` — Simulationsmetriken und Export
- `simulation_compare.py` — Branch-/Run-Vergleich
- `simulation_budget.py` — Budget-Preflight

Wichtige Konfliktcodes:

- aktiver Prepare → `409 simulation_prepare_in_progress`
- nicht vorbereitete Simulation → `simulation_not_prepared`
- aktive Simulation → `simulation_already_running`
- ausstehendes Persona-Review → `persona_review_required`
- aktive Report-Generierung → `409 report_generate_in_progress`

Nutzer-Stop und Infrastrukturabbruch sind unterschiedliche Zustände: ein expliziter Stop wird als `stopped` mit `termination_reason="user_stop"` geführt; stale Prozesse nach Worker-/Container-Restart können durch Startup-Reconciliation als `failed/process_restart` markiert werden.

`POST /api/simulation/<id>/branch` akzeptiert seit #886 eine kanonische `ai_model_ref` (Provider-Connection + Modell, `BranchOverrides`-Contract, `backend/app/contracts/branch_request_contract.py`) statt nur des Legacy-Strings `llm_model`; eine unbekannte oder deaktivierte Connection antwortet mit HTTP 400, die Kombination beider Felder ebenso. `llm_model` bleibt als deprecated Key erhalten. `POST /api/runs/<id>/replay` reicht seither die volle `AiModelRef` an `create_branch` durch statt nur die `model_id`.

### Report — `/api/report`

Wichtige Bereiche:

- Generierung und Fortschritt
- Report-Liste/Detail/Sections
- Evidence-Map sowie Section-/Claim-Evidence
- Markdown/JSON/CSV/ZIP-Export
- Agent-/Console-Logs
- Report-Chat und Report-Tools

#### Report-Generierung (Serialisierung)

Eine zweite parallele Report-Generierung für dieselbe Simulation wird mit HTTP `409 report_generate_in_progress` abgewiesen, solange bereits ein Run mit `run_type=report_generate` und Status `pending` oder `processing` existiert. Dies ist **bewusst serialisierend** (Issue #1265), da parallele Report-Generierungen den Faktor ~6 an Ressourcenverbrauch (Tokens, LLM-Calls, Laufzeit) verursachen, ohne Mehrwert zu liefern. Der aktive `run_id` wird im Fehlerfall nicht im Response-Body mitgegeben; der Client fragt `/api/report/generate/status` mit der `simulation_id` ab, um den laufenden Run zu identifizieren.

Nach Completion (`completed`, `failed`, `stopped`) ist ein neuer Start wieder erlaubt. Ein bereits existierender, abgeschlossener Report (`COMPLETED`) wird bei `force_regenerate=false` weiterhin wiederverwendet — der Guard läuft dabei zuerst, die Wiederverwendung wird erst danach geprüft.

#### Reportstatus

`COMPLETED` und `INCOMPLETE` sind fachlich verschieden. Ein nutzbarer Teilreport kann `INCOMPLETE` sein und trotzdem ausgeliefert werden. Cancel-, Section-Failure-, Requirement- und Fallback-Outline-Degradierungen dürfen nicht durch einen generischen „completed“-Status verschluckt werden (#1479).

`POST /api/simulation/prepare`/`/prepare/status` und `POST /api/report/generate/status` liefern seit #1174 neben dem Klartext `message` einen stabilen `message_key` (z. B. `prepare.already_completed`, `report.generated`, `report.failed`); das Frontend löst bekannte Schlüssel zentral auf, ein unbekannter Schlüssel fällt auf `message` zurück. Details: [`api-contracts.md`](api-contracts.md#status-meldungen-message_key).

#### Evidence-Endpunkt

`GET /api/report/<id>/evidence` verwendet einen Contract mit zwei Varianten:

1. erfolgreiche, validierte Evidence-Map,
2. `evidence_omitted` mit `reason=contract_violation`.

Bei einem **persistierten Altartefakt**, das die heutige Evidence-Semantik nicht mehr erfüllt, kann der direkte Evidence-Endpunkt deshalb HTTP 200 mit `evidence_omitted` liefern. Das hält den Bericht lesbar, ohne ungültige Evidence als geprüft auszugeben (#1477).

Exportpfade bleiben strenger: Wenn ein Format Evidence als geprüfte Datei ausliefern würde, wird sie weggelassen (`evidence-omitted.json`) oder der spezifische Export antwortet mit Contract-Fehler. Die alten pauschalen Aussagen „jede invalide Evidence = 422“ sind damit nicht mehr korrekt.

### Runs — `/api/runs`

Die Run-API umfasst unter anderem:

- Run-Detail
- Cancel/Stop/Resume
- Events
- Export
- Manifest
- Replay
- Usage/Budget
- LLM-Routing je Run bzw. Stage

Ungültige Filterparameter von `GET /api/runs` (z. B. `limit` außerhalb 1–200, unbekannter `status`) liefern `400` mit `code: "validation_error"`, einem Text in `error` und den Pydantic-Details unter `details` (#1679).

Resume ist semantisch **nicht** dasselbe wie Replay. Resume setzt einen bestehenden fachlichen Vorgang fort; Replay startet einen neuen Lauf aus einem Manifest. Vollständige Reproduzierbarkeit des Replay-Pfads ist noch Gegenstand von #763/#1274.

### LLM — `/api/llm`

Bereiche:

- öffentliche Provider-Metadaten
- ProviderConnections
- Secret-/API-Key-Verwaltung
- Modell-Discovery und Verbindungstest
- Active Config
- Workspace-/Stage-Routing
- Model-Stream
- Embedding-Konfigurationen und Embedding-Migrationen
- LLM-Profile (`llm_profiles.py`) — Metadaten-CRUD hinter `LlmProfileRepository`, Default-Ablage SQLite, optional PostgreSQL (`AGORA_LLM_PROFILE_BACKEND`, siehe [`architecture.md`](architecture.md))

Kanonische Provider-Matrix: `backend/app/services/llm_provider_registry.py`.

Transportklassen:

- `http` (inkl. Amazon Bedrock über den OpenAI-kompatiblen mantle-Pfad, #1282)
- `local` (lokaler HTTP-Dienst, z. B. Ollama)
- `cli` — `codex_cli` (ChatGPT-Abo, #1405) und `claude_cli` (Claude-Abo, #1531), beide Session-Auth, keine Base-URL

`PUT /api/llm/active-config` übernimmt seit #1289 die `base_url` einer gespeicherten, aktivierten `ProviderConnection` und prüft die Modell-Capabilities gegen genau diesen Endpunkt; ohne gespeicherte Connection (bzw. ohne dort gesetzte `base_url`) greift weiterhin der Registry-Default. Eine `base_url` im Request-Body bleibt ignoriert, `cli`-/Session-Provider bekommen nie eine erfundene Base-URL.

`GET /api/llm/providers` liefert je `ProviderDescriptor` seit #1415 auch `transport` und `auth_mode` aus der Registry-Matrix; die Provider-Einstellungen blenden damit für `cli`-Provider das Base-URL-Feld und für Session-Auth (`codex_cli`) auch das API-Key-Feld aus.

Details: [`provider-runtime-settings.md`](provider-runtime-settings.md).

### Settings — `/api/settings`

- Settings lesen/schreiben
- Schema
- Secret-Updates
- Settings-Stream

### Status & Logs

- `/api/status` — aggregierte Komponenten-Sicht
- `/api/logs` — Logs
- `/api/logs/stream` — Live-Stream

`/api/status` gibt bei internen Provider-/Disk-/Neo4j-Fehlern keine rohen `str(exception)`-Details mehr an den Client weiter; maschinenlesbare Codes werden geloggt/gespiegelt (#1459). Der Neo4j- und der Disk-Teilbaum haben seit #1466 einen eigenen Pydantic-Vertrag (`SystemStatusNeo4j`/`SystemStatusDisk`); Details in [`api-contracts.md`](api-contracts.md#status--und-task-contracts).

---

## SSE-Streams

Aktuelle Stream-Klassen umfassen insbesondere:

| Bereich | Beispiel | Zweck |
|---|---|---|
| Simulation | `/api/simulation/<id>/stream` | Live-Zustand/Aktionen |
| Modell/Provider | `/api/llm/model-stream` | aktive Modell-/Provider-Änderungen |
| Logs | `/api/logs/stream` | Live-Log-Viewer |
| Settings | `/api/settings/stream` | Settings-Änderungen |

Streams sind keine normalen JSON-Responses. Authentifizierung erfolgt über die dafür vorgesehene Ticket-/Header-Logik.

---

## Verträge und Schemas

- Backend: [`../backend/app/contracts/`](../backend/app/contracts/)
- Frontend: [`../frontend/src/contracts/`](../frontend/src/contracts/)
- eingecheckte JSON-Schemas: [`../schemas/`](../schemas/)
- Generator/Drift-Check: `uv run python -m app.contracts.dump_schemas --check`

Bei Contract-Änderungen gelten die Regeln aus `AGENTS.md`: Pydantic zuerst, Zod/Schema im selben Slice, Consumer/Tests mitziehen.

## Wo nicht raten

Wenn diese Übersicht und der Code auseinanderlaufen, gewinnt der Code. Routenanzahl, Testanzahl und Modellkataloge werden deshalb hier bewusst nicht als statische Marketingzahlen geführt. Wer eine exakte Liste benötigt, liest die Blueprints bzw. die generierten Contracts statt einen Monate alten Zähler zu verehren.
