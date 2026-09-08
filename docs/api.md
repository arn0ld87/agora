# HTTP-API — Agora Backend

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Backend:** `0.9.5`

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

### Onboarding & Profil

Mounts unter `/api/onboarding` und `/api/profile`.

- Onboarding-Status und Schritte
- Profil- und Avatarverwaltung

### Graph — `/api/graph`

Module:

- `graph_projects.py` — Projekt-/Graph-Metadaten und Reset/Delete
- `graph_build.py` — Graph-Build und Ontologie-Generierung
- `graph_data.py` — Graphdaten, Snapshots, Diff, Export und Task-Sichten

Langlaufende Graph-Jobs werden über die Run-/Task-Infrastruktur sichtbar gemacht. Restart-/SIGTERM-Semantik für daemonisierte Graph-Build-Threads ist als Teil von #1472 noch nicht vollständig gelöst.

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

Nutzer-Stop und Infrastrukturabbruch sind unterschiedliche Zustände: ein expliziter Stop wird als `stopped` mit `termination_reason="user_stop"` geführt; stale Prozesse nach Worker-/Container-Restart können durch Startup-Reconciliation als `failed/process_restart` markiert werden.

### Report — `/api/report`

Wichtige Bereiche:

- Generierung und Fortschritt
- Report-Liste/Detail/Sections
- Evidence-Map sowie Section-/Claim-Evidence
- Markdown/JSON/CSV/ZIP-Export
- Agent-/Console-Logs
- Report-Chat und Report-Tools

#### Reportstatus

`COMPLETED` und `INCOMPLETE` sind fachlich verschieden. Ein nutzbarer Teilreport kann `INCOMPLETE` sein und trotzdem ausgeliefert werden. Cancel-, Section-Failure-, Requirement- und Fallback-Outline-Degradierungen dürfen nicht durch einen generischen „completed“-Status verschluckt werden (#1479).

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

Kanonische Provider-Matrix: `backend/app/services/llm_provider_registry.py`.

Transportklassen:

- `http`
- `local` (lokaler HTTP-Dienst, z. B. Ollama)
- `cli` (z. B. `codex_cli`, Session-Auth, keine Base-URL)

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

`/api/status` gibt bei internen Provider-/Disk-/Neo4j-Fehlern keine rohen `str(exception)`-Details mehr an den Client weiter; maschinenlesbare Codes werden geloggt/gespiegelt (#1459).

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
