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
- **Versionierung und Kompatibilität:** Die API hat keinen URL-Präfix, ihre Version ist die App-Version (SemVer). Ab `v1.0.0` gibt es kein Breaking in `1.x` an den hier dokumentierten Endpunkten und an persistierten Formaten. Eine Deprecation wird im Changelog angekündigt, im Log gewarnt und in der Antwort über die Header `Deprecation` und `Link: rel="successor-version"` gekennzeichnet. Entfernt wird frühestens in `2.0.0`. Details, Breaking-Definition und offene Einzelfälle: [ADR-0021](decisions/0021-kompatibilitaet-ab-1-0.md).

---

## Domänen

### Auth & API-Keys

Mounts unter `/api/auth` und `/api/api-keys`.

Wichtige Funktionen:

- signierte Tickets für Browser-Streams/Downloads
- API-Key-Erzeugung, Widerruf und Scope-Prüfung
- Mastertoken-/API-Key-Auflösung über die zentrale Auth-/Scope-Schicht
- `GET /api/auth/config` (öffentlich): `auth_backend`, `jwt_enabled`, `demo_mode` (aus `AGORA_DEMO_MODE`, Gate für die Frontend-Demo-Vorschau, #1697) und nur bei aktivem JWT `supabase_url` und `supabase_anon_key` für den Browser-Client. Kein Geheimnis (#1616).

### Workspaces — `/api/workspaces` (#1616)

Der aktive Workspace kommt immer aus dem Principal (`X-Agora-Workspace`, vom Guard gegen die Mitgliedschaft geprüft), nie aus dem Pfad.

| Methode und Pfad | Wer | Wirkung |
|---|---|---|
| `GET /api/workspaces` | jeder angemeldete Nutzer, auch ohne Workspace | eigene Workspaces mit Rolle; Betreiber sehen den Default-Workspace |
| `POST /api/workspaces/bootstrap` | Supabase-Nutzer | legt beim ersten Aufruf genau einen persönlichen Workspace an (Owner), danach idempotent (`created: false`). Body optional `{"name": "..."}`. Betreiber: `400 not_applicable` |
| `GET /api/workspaces/current/members` | jedes Mitglied | Mitglieder des aktiven Workspace |
| `PUT /api/workspaces/current/members/<user_id>` | Owner, Admin | Mitglied anlegen oder Rolle ändern, Body `{"role": "owner"\|"admin"\|"member"\|"viewer"}` |
| `DELETE /api/workspaces/current/members/<user_id>` | Owner, Admin, jeder für sich selbst | Mitglied entfernen, Antwort `{"user_id": ...}` (`WorkspaceMemberRemoval`) |
| `GET /api/workspaces/current/provider-credentials` | jedes Mitglied (nur JWT) | Status der eigenen Provider-Keys ohne Key-Werte plus `supported_providers` (alle BYOK-fähigen Anbieter aus `LlmProviderRegistry.workspace_key_definitions()`, #1688) |
| `PUT`/`DELETE /api/workspaces/current/provider-credentials/<provider_id>` | Owner, Admin (nur JWT) | eigenen Key setzen (Body `{"api_key": "..."}`) oder löschen; Anbieter außerhalb von `supported_providers`: `400 invalid_provider` |

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
- `simulation_budget.py` — Budget-Preflight (`POST /api/simulation/preflight-estimate`; optional `platform` = `parallel` (Standard) | `twitter` | `reddit`, seit #1772; `400` bei anderem Wert)

`POST /api/simulation/prepare` nimmt seit #1778 das optionale Feld `contested_question` entgegen: die Streitfrage des Laufs als Aussage mit 10 bis 300 Zeichen. Ist es gesetzt, übernimmt die Simulationskonfiguration sie mit `origin="user"`, und der Konfigurations-Assistent leitet keine eigene ab. Fehlt es oder ist es leer, schlägt der Assistent eine Streitfrage vor (`origin="assistant"`) oder hält fest, dass es keine gibt (`origin="none"`). Ein Wert außerhalb der Längengrenzen oder ein Nicht-String antwortet mit `400`. Die Vorgabe steht als `metadata.contested_question` am Prepare-Run; `POST /api/runs/<id>/resume` reicht sie beim Neustart der Vorbereitung erneut durch. Weicht die übergebene Streitfrage von der persistierten ab, wird eine bereits vorbereitete Simulation erneut vorbereitet statt mit `already_prepared` zu antworten; dieselbe Aussage oder ein fehlendes Feld lassen den Kurzschluss bestehen.

Wichtige Konfliktcodes:

- aktiver Prepare → `409 simulation_prepare_in_progress`
- nicht vorbereitete Simulation → `simulation_not_prepared`
- aktive Simulation → `simulation_already_running`
- ausstehendes Persona-Review → `persona_review_required`
- aktive Report-Generierung → `409 report_generate_in_progress`

Nutzer-Stop und Infrastrukturabbruch sind unterschiedliche Zustände: ein expliziter Stop wird als `stopped` mit `termination_reason="user_stop"` geführt; stale Prozesse nach Worker-/Container-Restart können durch Startup-Reconciliation als `failed/process_restart` markiert werden.

`GET /api/simulation/<id>` projiziert seit #1713 seinen `status` zur Lesezeit: `run_state.json`'s `runner_status` (terminalisiert vom Monitor als `completed`/`failed`/`stopped`) wird nur angewendet, wenn der persistierte `SimulationState.status` noch `running` ist — vorher blieb die Antwort dauerhaft `running`, obwohl die Simulation längst beendet war. Der persistierte Zustand in `state.json` bleibt unverändert; ein bereits `failed` persistierter Status wird nicht überschrieben. Die Antwort trägt zusätzlich den Rohwert `runner_status` (`null` ohne Run-State) und `interview_env_alive` (`SimulationRunner.check_env_alive`). Vertrag: `backend/app/contracts/simulation_status_contract.py::SimulationStatusResponse`.

`POST /api/simulation/<id>/branch` akzeptiert seit #886 eine kanonische `ai_model_ref` (Provider-Connection + Modell, `BranchOverrides`-Contract, `backend/app/contracts/branch_request_contract.py`) statt nur des Legacy-Strings `llm_model`; eine unbekannte oder deaktivierte Connection antwortet mit HTTP 400, die Kombination beider Felder ebenso. `llm_model` bleibt als deprecated Key erhalten. `POST /api/runs/<id>/replay` reicht seither die volle `AiModelRef` an `create_branch` durch statt nur die `model_id`.

#### Aktionsprotokoll und Rundensummary (#1713 UI-2a)

`GET /api/simulation/<id>/actions` — cursor-paginiertes Aktionsprotokoll als `SimActionPage`.

| Query-Parameter | Typ | Default | Beschreibung |
|---|---|---|---|
| `cursor` | string | — | Opakes Cursor-Token aus `next_cursor` der Vorgänger-Antwort; ungültig/negativ → 0 |
| `limit` | int | 50 | Einträge pro Seite; wird auf 1–200 geclampd |
| `round_num` | int | — | Nur Aktionen dieser Runde |
| `agent_id` | int | — | Nur Aktionen dieses Agenten |
| `platform` | string | — | `reddit` oder `twitter` |
| `action_type` | string | — | Muss ein gültiger `SimActionType`-Wert sein; unbekannter Wert → **400 `validation_failed`** |

Antwortform (`data`-Feld der Envelope):
```json
{
  "items": [ /* SimActionRecord[] */ ],
  "next_cursor": "50"   // null wenn letzte Seite
}
```

`next_cursor` ist ein opakes Token (aktuell ein Offset-String); Clients dürfen dessen Format nicht parsen. Die früheren Felder `offset`, `count` und `actions` sind entfallen (**Breaking Change** gegenüber dem Vor-#1713-Stand).

---

`GET /api/simulation/<id>/rounds` — Aktionsbilanz je `(round_num, platform)`-Paar als `{"rounds": [RoundSummary]}`.

Keine Query-Parameter. Einträge werden nach `(round_num, platform)` aufsteigend sortiert. Altbestand mit unbekanntem `platform`-Wert wird mit `logger.warning` übersprungen statt HTTP 500 zu werfen (Degradations-Haltung analog zu `evidence_omitted`).

---

`GET /api/simulation/<id>/feed-snapshot?platform=reddit|twitter&limit=200` — Feed eines (auch beendeten) Laufs als `{"platform", "count", "posts": [PostCreatedEvent]}`, aufsteigend nach `timestamp`; bei mehr als `limit` Einträgen bleiben die neuesten. Quelle ist die OASIS-SQLite-Datei `<platform>_simulation.db`, ergänzt um das Aktionsprotokoll `<platform>/actions.jsonl`.

- Kommentare (`kind="comment"`, `parent_post_id`/`root_post_id` = Elternpost) werden für Reddit **und** Twitter geliefert. Twitter-Kommentare gibt es erst in Läufen, in denen `CREATE_COMMENT` freigeschaltet war (#1713 S5); ältere Twitter-Läufe liefern Antworten nur als Zitate/Reposts.
- `parent_comment_id` kommt aus der Spalte `comment.parent_comment_id` (nested-comments, #1713 S5). Läufe ohne diese Spalte liefern `null`.
- `round_num` wird nur gesetzt, wenn das Aktionsprotokoll die Zeile eindeutig belegt: Kommentare über `comment_id`, Reposts/Zitate über `new_post_id`, Originalposts über Autor und Text (Startposts, die später ein zweites Mal im Protokoll stehen, zählen als Runde 0). Mehrdeutige Zuordnungen, fehlende Protokolle und Protokolle mit mehreren `simulation_start`-Ereignissen liefern `null` — nie eine Schätzung.
- Twitter-Datenbanken speichern statt eines Datums den OASIS-Zeitschritt als Ganzzahl. `timestamp` ist dort der Protokollzeitpunkt der zugeordneten Aktion; Zeilen ohne belegte Zuordnung werden ausgelassen und per `logger.warning` gezählt.

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

`POST /api/simulation/prepare` nimmt seit #1779 das optionale Feld `activity_mode` entgegen: `realistic` oder `active`. Es wählt den Satz der Tagesraten für Textbeiträge je Akteursklasse, mit dem die Simulation vorbereitet wird (`time_config.activity_model`). Fehlt es oder ist es leer, gilt die Einstellung `AGORA_SIM_ACTIVITY_MODE` (Standard `realistic`). Jeder andere Wert antwortet mit `400`. Der Modus steht als `metadata.activity_mode` am Prepare-Run; `POST /api/runs/<id>/resume` reicht ihn beim Neustart der Vorbereitung erneut durch. Weicht ein ausdrücklich übergebener Modus vom persistierten ab, wird eine bereits vorbereitete Simulation erneut vorbereitet statt mit `already_prepared` zu antworten; das gilt auch für eine Simulation, die noch kein Aktivitätsmodell hat. Ohne das Feld bleibt der Kurzschluss bestehen.

`POST /api/simulation/prepare`/`/prepare/status` und `POST /api/report/generate/status` liefern seit #1174 neben dem Klartext `message` einen stabilen `message_key` (z. B. `prepare.already_completed`, `report.generated`, `report.failed`); das Frontend löst bekannte Schlüssel zentral auf, ein unbekannter Schlüssel fällt auf `message` zurück. Details: [`api-contracts.md`](api-contracts.md#status-meldungen-message_key).

#### Evidence-Endpunkt

`GET /api/report/<id>/evidence` verwendet einen Contract mit zwei Varianten:

1. erfolgreiche, validierte Evidence-Map,
2. `evidence_omitted` mit `reason=contract_violation`.

Bei einem **persistierten Altartefakt**, das die heutige Evidence-Semantik nicht mehr erfüllt, kann der direkte Evidence-Endpunkt deshalb HTTP 200 mit `evidence_omitted` liefern. Das hält den Bericht lesbar, ohne ungültige Evidence als geprüft auszugeben (#1477).

Belege aus Interview und Simulationsaktion tragen seit #1778 das optionale Feld `voice_key` (`agent:<agent_id>`), die Stimme, von der der Beleg stammt. `run_degradations` kennt seit #1778 die Komponente `simulation_positioning` (`warning`): zu wenige Stimmen beziehen in der Simulation Stellung zur Streitfrage.

#### Sprungkennungen an Belegen (#1804)

`GET /api/report/<id>/evidence` ergänzt Belege der Typen `agent_action` und `entity_summary` um optionale Sprungkennungen. Sie werden erst beim Ausliefern aus dem Beleg-Inhalt (`raw`, `producer_key`) abgeleitet, nie gespeichert; die Evidence-Map im Berichtsordner bleibt byte-identisch, und die Ableitung gilt damit auch für Altberichte. Ein nicht ableitbares Feld fehlt in der Antwort.

- `origin_post_id` (`agent_action`): Feed-Format von `GET /api/simulation/<id>/feed-snapshot`, `<platform>:<id>` bzw. `<platform>:comment:<id>` mit `platform` = `twitter` | `reddit`. Nur für Aktionen, die einen eigenen Beitrag erzeugen und dessen Kennung das Aktionsprotokoll trägt: `CREATE_POST` (`post_id`), `QUOTE_POST` und `REPOST` (`new_post_id`), `CREATE_COMMENT` (`comment_id`). `LIKE_*`, `FOLLOW` und `SEARCH_*` tragen nur die Kennung ihres Ziels und bekommen kein Feld. Widerspricht der `producer_key` der Aktion Plattform oder Aktionsart in `raw`, bleibt das Feld leer. Die Kennung stammt aus dem Aktionsprotokoll; bei Läufen, deren Protokoll nach einem Neustart nicht zur Datenbank passt, kann sie auf einen anderen Beitrag zeigen. Clients sollten deshalb vor dem Sprung prüfen, ob der Beitrag im Feed existiert und zum Belegtext passt.
- `origin_node_uuids` (`entity_summary`): Knoten-UUIDs im Wissensgraphen aus `raw.uuid`. `graph_fact` und `relationship_chain` tragen als `raw` nur den Faktentext und bekommen keine Kennung. `agent_interview` braucht keine: `voice_key` (`agent:<id>`) benennt die Persona bereits.

#### Erzeugungsherkunft einer Berichtsfassung (#1804)

`GET /api/report/<id>`, `GET /api/report/by-simulation/<simulation_id>` und `GET /api/report/list` tragen die optionalen Felder `llm_model`, `llm_provider_id` und `generation_run_id` (`ReportModel`, jeweils `null`, wenn nicht belegt). Quelle ist der jüngste Berichts-Job (`run_type=report_generate`, `entity_id=<report_id>`) der RunRegistry: `metadata.llm_model` und `metadata.llm_provider.provider_id` stammen dort aus der gelockten Route der Stufe `report_generation`, also aus dem Modell, das tatsächlich lief. `generation_run_id` ist die `run_id` dieses Jobs und der Schlüssel für `GET /api/runs/<run_id>/llm-routing`. Berichte ohne Job (Altbestand, gelöschter Lauf) und Jobs ohne Modellangabe lassen die Felder `null`; nichts wird aus Workspace-Defaults geraten, die Basis-URL des Anbieters wird nicht ausgeliefert. Die Berichts-Metadatei (`meta.json`) speichert sie nicht, und im Export (`report` im Envelope) bleiben sie `null`. `/list` liest die Registry einmal für alle Fassungen.

#### Belegdichte und Positionierungsquote (#1804)

`GET /api/report/<id>/evidence-density` liefert die je Bericht gespeicherte `evidence_density.json` (#1779), `GET /api/report/<id>/stance-analysis` die `stance_analysis.json` mit Positionierungsquote und Lagerverteilung (#1778). Beide sind rein lesend, ohne eigene Scope-Regel (wie `/evidence`), und antworten mit genau einer von drei Formen:

1. `{"success": true, "data": {…}}` — die Datei liegt vor und erfüllt den Vertrag (`EvidenceDensity` bzw. `StanceAnalysis`). `data.applicable=false` bei der Haltungsanalyse ist ein Lauf ohne Streitfrage, kein Fehler.
2. HTTP 404 (`{"success": false, "error": …}`) — der Bericht hat die Datei nicht (Altbericht aus der Zeit vor #1778/#1779).
3. HTTP 200 `{"success": true, "artifact_omitted": {"artifact", "reason": "contract_violation", "detail", "validation_errors"}}` — die Datei liegt vor, ist aber beschädigt oder vertragswidrig. Das ist sichtbar und nicht dasselbe wie „keine Daten“ (Muster von `evidence_omitted`). Die Datei wird nie verändert.

Verträge: `EvidenceDensityResponseModel` / `StanceAnalysisResponseModel` (`backend/app/contracts/report_artifact_contract.py`), Schemas `schemas/evidence-density-response.schema.json` und `schemas/stance-analysis-response.schema.json`, Zod-Spiegel `frontend/src/contracts/reportArtifactContract.ts`.

Exportpfade bleiben strenger: Wenn ein Format Evidence als geprüfte Datei ausliefern würde, wird sie weggelassen (`evidence-omitted.json`) oder der spezifische Export antwortet mit Contract-Fehler. Die alten pauschalen Aussagen „jede invalide Evidence = 422“ sind damit nicht mehr korrekt.

### Runs — `/api/runs`

Die Run-API umfasst unter anderem:

- Run-Detail
- Cancel/Stop/Resume
- Events
- Export
- Manifest
- Replay
- Usage/Budget (ohne `budget` im Start-Aufruf gilt seit #1772 ein Standardbudget aus den Einstellungen im Abschnitt `budget`: harter Tokendeckel `AGORA_SIM_DEFAULT_MAX_TOKENS`, Standard 20 Mio., plus seit #1799 optional `AGORA_SIM_DEFAULT_MAX_COST_MICROS`, `AGORA_SIM_DEFAULT_MAX_DURATION_SECONDS`, `AGORA_SIM_DEFAULT_MAX_LLM_CALLS` und die Durchsetzung `AGORA_SIM_DEFAULT_BUDGET_ENFORCEMENT` (`soft`/`hard`); `0` = kein Limit; sichtbar in `metadata.budget`)
- LLM-Routing je Run bzw. Stage

Ungültige Filterparameter von `GET /api/runs` (z. B. `limit` außerhalb 1–200, unbekannter `status`) liefern `400` mit `code: "validation_error"`, einem Text in `error` und den Pydantic-Details unter `details` (#1679).

`GET /api/runs/<run_id>/export` liefert seit #1680 nur explizit allowlistete Artefakte: `manifest.json`, `runtime_llm_routing.json`, `llm_call_events.jsonl`, `usage_summary.json`, `budget_warnings.json` sowie `stages/*_llm_route_snapshot.json` und `stages/*_ai_route_snapshot.json` (Allowlist: `backend/app/services/run_export.py::EXPORT_ALLOWED_PATTERNS`, erhoben aus dem Inventar aller Writer ins Run-Verzeichnis). Alles andere — insbesondere versehentlich ins Run-Verzeichnis geratene Dateien wie `.env` oder `secrets.json` — wird nicht ausgeliefert und stattdessen in der im ZIP enthaltenen `export-report.json` unter `skipped` (mit `reason`: `not_in_allowlist`, `symlink` oder `outside_run_dir`) sichtbar gemeldet; zusätzlich loggt der Endpoint die übersprungenen Dateien strukturiert. Symlinks und Pfade, deren realer Speicherort außerhalb des Run-Verzeichnisses liegt, werden nie exportiert. Neue Writer ins Run-Verzeichnis müssen ihr Artefakt im selben Change in die Allowlist aufnehmen, sonst bleibt es im Export sichtbar `skipped`.

Resume ist semantisch **nicht** dasselbe wie Replay. Resume setzt einen bestehenden fachlichen Vorgang fort; Replay startet einen neuen Lauf aus einem Manifest.

`POST /api/runs/<run_id>/replay` übernimmt seit #1274 (Punkt 3) `platform`, `max_rounds`, `enable_graph_memory_update` und die Graph-Memory-Update-ID 1:1 aus dem Original-Manifest (`RunManifest.simulation`), statt wie zuvor stillschweigend auf `platform="parallel"` und Runner-Defaults zurückzufallen. Übersteuerbar bleibt ausschließlich die Modell-Route (`overrides.ai_model_ref`). Ein Manifest ohne `simulation`-Feld (geschrieben vor dieser Änderung) kann nicht ehrlich 1:1 repliziert werden — der Endpoint antwortet dann mit `409 code="manifest_missing_simulation_params"` statt einen Default stillschweigend als Original auszugeben.

Ohne expliziten `overrides.ai_model_ref` seedet der Endpoint die Modell-Route seit #1686 aus der im Original-Manifest erfassten Route (`routing.stages.simulation_rounds`, bevorzugt deren `ai_route_snapshot`) statt aus den aktuellen Workspace-Defaults — sonst liefe ein vermeintlich identisches Replay unbemerkt auf einem anderen Modell, sobald sich Defaults oder Provider-Connections seit dem Original-Run geändert haben. Ist die Original-Connection nicht mehr auflösbar (z. B. gelöscht oder deaktiviert), antwortet der Endpoint mit `409 code="manifest_route_unresolvable"`, statt still auf Defaults zurückzufallen.

Der neue Replay-Run bekommt sein eigenes Draft-Manifest (`replayed_from_run_id` zeigt auf das Original), das VOR dem Start des Simulations-Subprozesses geschrieben wird (#1686) — genau wie seither auch der normale Startpfad (`POST /api/simulation/start`): sonst könnte der Monitor-Thread bei sofortigem Prozessende das Manifest finalisieren wollen, bevor der Draft überhaupt existiert, und der Run bliebe dauerhaft im Status `draft` hängen. Scheitert der Start danach doch, wird das bereits geschriebene Draft-Manifest in beiden Pfaden wieder entfernt (`ManifestCapture.discard_draft_best_effort`, gemeinsamer Helper). Das Manifest trägt ein `deviations`-Feld: eine Liste von `{field, original, replay}`-Einträgen für jede tatsächliche Abweichung der aufgelösten Replay-Route von der im Original-Manifest erfassten Route — dieser Vergleich läuft seit #1686 immer, unabhängig davon, ob ein expliziter Override gesetzt war. `inputs.simulation_config_hash` ist seit #1686 in beiden Pfaden der Hash der tatsächlich verwendeten Konfiguration (`ManifestCapture.simulation_config_hash`, gemeinsamer Helper) — beim Replay die Branch-Konfiguration nach `create_branch`, nicht mehr der 1:1 kopierte Hash des Originals.

`RunManifest.routing.stages.<stage>.ai_route_snapshot` ist seit #1274 (Punkt 2) ein striktes Schema (`AiRouteSnapshot`, Backend-Contract `backend/app/contracts/run_manifest_contract.py`) statt eines offenen Dicts — der interne `__legacy_stage_route__`-Transportkanal von `AiRoute` ist bereits aufgelöst, secret-tragende Provider-Optionen sind entfernt. Alte Manifeste mit dem vollen `AiRoute`-Dump bleiben lesbar (tolerantes Einlesen, nicht rettbare Altbestände werden `null`).

`RunManifest.seeds.random_seed` ist `null` (#1274 Punkt 1): Agora hat kein echtes RNG-Seed-Konzept, ein früherer Hash über die `simulation_id` täuschte Reproduzierbarkeit vor, die nicht bestand. `inputs.seed_document_hash`/`seed_document_filename` sind ebenfalls `null`, wenn die Quelle (Projekt-Dokument) nicht ermittelbar ist, statt des Platzhalters `"unknown"`.

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
