# Agora — Status (Single Source of Truth)

Stand: **2026-07-14**, `main` @ `771fbe10`, Version **v1.0.0**.

Diese Datei beschreibt den verifizierten Istzustand. Versions- und Testzahlen
werden ausschließlich über `scripts/sync-status.sh` zwischen den markierten
Blöcken gepflegt. Zukunftspläne gehören in `PLAN.md`, ausgelieferte Änderungen
in `CHANGELOG.md` und die unmittelbar nächste Fortsetzung in das jeweilige
Epic-`HANDOVER.md`.

## Versionen

<!-- BEGIN_AUTOGEN_VERSIONS -->
| Komponente | Pfad | Version |
|---|---|---|
| Backend | `backend/pyproject.toml` | 1.0.0 |
| Frontend | `frontend/package.json` | 1.0.0 |
| Root | `package.json` | 1.0.0 |
<!-- END_AUTOGEN_VERSIONS -->

## Tests

<!-- BEGIN_AUTOGEN_TESTS -->
| Kategorie | Anzahl | Methode |
|---|---|---|
| Backend Tests (collected) | 3335 | `cd backend && uv run pytest --collect-only -q` |
| Frontend Test-Files | 163 | `find frontend/src \( -name '*.spec.ts' -o -name '*.spec.js' -o -name '*.test.ts' -o -name '*.test.js' \)` |
<!-- END_AUTOGEN_TESTS -->

Hinweise:

- Zwei Redis-Integrationstests skippen ohne `TEST_REDIS_URL` kontrolliert und
  sind in der Backend-Summe als collected enthalten.
- Die Frontend-Zahl zählt Testdateien, nicht einzelne Testfälle.
- `scripts/pre-push-gate.sh` unterstützt die Scopes `backend`, `frontend` und
  `schemas`. Der zuvor fehlende `run_schemas`-Pfad wurde in PR #734 repariert;
  der Scope prüft 46 Schemas und den STATUS-Sync.
- Zwei unter Parallelbetrieb flaky Router-/Accessibility-Specs wurden in PR
  #733 ohne Skip oder abgeschwächte Assertions stabilisiert. Das vollständige
  Frontend-Pre-Push-Gate lief danach grün.

## Aktive Entwicklungswelle: Onboarding und Provider-Unification

Source of Truth für Scope und Reihenfolge:
[`docs/epics/onboarding-provider-unification/04-implementation-plan.md`](epics/onboarding-provider-unification/04-implementation-plan.md).

| Slice | Inhalt | Verifizierter Status |
|---|---|---|
| 0 | Research, ADRs, Test-/Migrationsplan, Agent-Tooling | abgeschlossen |
| 1 | Kanonische Provider-, Modell- und Route-Verträge | gemergt, Pydantic-v2-SSoT + Zod-/Schema-Spiegel |
| 2 | Benutzerprofil und resumierbares Onboarding | gemergt |
| 3 | Provider-Verbindungen, Discovery und Secret-Store-Anbindung | gemergt |
| 4 | Getrenntes Embedding-Setup und sichere Re-Embedding-Migration | 4.1–4.4 auf `main`; Entity- und Fact-Phase resume-fähig |
| 5 | Gemeinsamer `AiModelPicker` und Routing | Kern abgeschlossen; kanonische Route, Snapshot und Audit verdrahtet |
| 6 | Persona-Count-End-to-End-Invariante | Codepfad vorhanden; vollständige E2E-Matrix 1/5/10/30/50/100 noch nicht zentral nachgewiesen |
| 7 | Golden-Gate-System und Informationsarchitektur | weitgehend auf `main`; Restarbeiten unten |
| 8+ | Projekte, Datensätze, Vorlagen und Monitoring | als getrennte MVP-Slices offen |

Bewusst offene Embedding-Folgen:

- Gemini-Batch-Embedding,
- echter `scope="project"`-Filter,
- vollständige Umstellung des Fact-Search-Lesepfads auf den neuen Index.

## Slice 7 — aktueller Stand

Bereits auf `main`:

- 7.1 Token-/State-Fundament,
- 7.3 Golden-Gate-Gates, Drawer-/Sidebar-Accessibility und Routing-Correctness
  (PR #723),
- 7.4a Settings-Parität und Redirect von `/settings-classic` (PR #721),
- 7.5 Onboarding-Surface (PR #725),
- 7.6a–7.6d kanonischer `AiModelPicker`, Consumer-Migration,
  `StageLLMRoute`-Entfernung und Legacy-Route-Storage-Cut (PRs #726–#728);
  7.6d migriert `LlmProfileManager.vue` auf den connection-basierten Picker
  und entfernt den letzten produktiven `ModelPicker.vue` (PR #742),
- 7.7 Entfernung des verwaisten v3-Pickers und der Mock-Routing-Karten
  (PR #720),
- Verifizierte Picker-Migrationsmatrix und konkreter 7.6d-Plan (PR #732),
- Golden-Gate-Workbench-Zielspezifikation unter
  [`docs/ui/golden-gate-workbench.md`](ui/golden-gate-workbench.md) (PR #735).

Noch offen:

1. Responsive-/visuelle Regressionen vollständig schließen.
3. Den geplanten `--agora-*`-Tokenwechsel als eigenes migrationspflichtiges
   Slice umsetzen; keine parallele Komponentenbibliothek erzeugen.

## E2E-Smokes

Der Stack bootet seit PR #731 erstmals zuverlässig im GitHub-Runner. Der
Health-Smoke ist grün; fünf bereits zuvor vorhandene Specs erreichen jetzt den
eigentlichen Test und sind rot. Die Defekte sind unter
[`docs/epics/e2e-smoke-specs/README.md`](epics/e2e-smoke-specs/README.md)
aufgeschlüsselt.

| Smoke | Status | Hauptbefund |
|---|---|---|
| Health | grün | Stack, Auth und Provider-Seeding funktionieren |
| Upload + Graph | rot | API erfolgreich, UI-/Store-Verdrahtung rendert `graphData` nicht |
| Minimalreport | rot | Report completed, Outline fehlt oder scheitert am Zod-Spiegel |
| Report-Modi | rot | `force_regenerate`/Mode-Pfad erreicht nicht stabil `completed` |
| Golden-Gate Accessibility | rot | mindestens eine Route verletzt ein striktes A11y-Gate |
| AiModelPicker | rot | Route-/UI-Drift nach der Picker-Migration |

`.github/workflows/e2e-smokes.yml` läuft derzeit auf `push` nach `main`,
`workflow_dispatch` und täglich um 03:00 UTC. Der `pull_request`-Trigger bleibt
bewusst aus, bis alle fünf roten Specs stabil grün sind; danach muss er als
eigener CI-PR wieder aktiviert und als Required Check konfiguriert werden.

## Quality Gates

| Gate | Befehl | Status |
|---|---|---|
| Backend | `bash scripts/pre-push-gate.sh backend` | grün auf den jüngsten Doku-/Fix-PRs |
| Frontend | `bash scripts/pre-push-gate.sh frontend` | nach PR #733 vollständig grün |
| Schemas | `bash scripts/pre-push-gate.sh schemas` | grün, 46 Schemas + STATUS-Sync |
| Backend Types | `cd backend && uv run mypy app` | blockierend in CI |
| Backend Lint | `cd backend && uv run ruff check .` | blockierend |
| Frontend Types | `cd frontend && npm run typecheck` | blockierend in CI |
| Frontend Lint | `cd frontend && npm run lint` | blockierend |
| E2E-Smokes | `.github/workflows/e2e-smokes.yml` | 1/6 grün; noch kein PR-Gate |

## Coverage

Die Messwerte sind älter als der aktuelle Codebestand und müssen vor dem
nächsten Release neu erzeugt werden. Sie bleiben bis dahin als letzte belegte
Baseline erhalten.

| Bereich | letzte Messung | Ergebnis | aktive CI-Schwelle |
|---|---|---:|---:|
| Backend gesamt | 2026-06-10 | 66,00 % | 60 % |
| Frontend Statements | 2026-05-10 | 50,46 % | 28 % |
| Frontend Branches | 2026-05-10 | 39,56 % | 28 % |
| Frontend Functions | 2026-05-10 | 38,59 % | 28 % |
| Frontend Lines | 2026-05-10 | 52,50 % | 28 % |

Strukturelle Lücken bleiben vor allem in OASIS-/Neo4j-Integrationspfaden,
Canvas-/WebGL-Komponenten und großen Wizard-/View-Komponenten. Coverage-Ziele
dürfen nicht durch engere Include-Globs oder globale Skips künstlich erfüllt
werden.

## Architektur-Layer

| Layer | Inhalt | Status |
|---|---|---|
| 0 | Pydantic-Verträge und Zod-/JSON-Schema-Spiegel | grün |
| 1 | Backend-Hardening | grün |
| 2 | DACH-Voice und Glossar | grün |
| 3 | Reader-Honesty | grün |
| 4 | Frontend strict-Zod | grün |
| 5 | Eval-/Baseline-Suite | grün |
| 6 | Frontend-TypeScript-Migration | grün |
| 7–8 | Graph, Runs, Persona- und Report-Review | teilweise |
| 9 | Produktion, Proxy, Auth und Runtime-Image | grün mit dokumentierten Release-Gates |
| 10 | Supply Chain und Security-Watchlist | grün mit offenen Hardstops |

## Sicherheit und Hardstops

- Auth-Zielbild: experimentelles Single-User-System gemäß ADR-0001; nicht
  ungeschützt ins öffentliche Internet stellen.
- Provider-Detection-SSoT:
  `backend/app/llm/providers/registry.py::detect_provider`.
- Phase-F-Restpunkt: Issue #671 zur bewussten Vereinheitlichung oder
  Dokumentation der Embedding-Provider-Erkennung.
- `nltk` PYSEC-2026-597 / GHSA-p4gq-832x-fm9v: Hardstop **2026-07-30**,
  Tracking #672.
- Trivy OS-Layer CVE-2026-24049 / CVE-2026-23949: Hardstop **2026-08-30**.

## Nächste drei Prioritäten

1. Die fünf roten E2E-Smokes einzeln reparieren und anschließend den
   `pull_request`-Trigger wieder aktivieren.
2. Dokumentationsdrift in `AGENTS.md`, Epic-`HANDOVER.md` und
   `docs/tooling/agent-tools.md` gegen diesen Stand synchronisieren.

## Bekannte Dokumentationsschuld

- `AGENTS.md` bezeichnete 7.6c zuletzt noch als laufenden PR.
- `docs/tooling/agent-tools.md` wurde zuletzt am 2026-07-10 geprüft und enthält
  ältere Graph-/Doctor-Werte.
- Ältere konzeptionelle Abschnitte in `PLAN.md` beschreiben nicht mehr die
  produktive Provider-/Routing-Architektur und sollten in `docs/archive/`
  verschoben werden.
- Historische Implementierungsdetails gehören in `CHANGELOG.md`, ADRs,
  Worklogs und Git-Historie, nicht als unendliches Protokoll in dieser Datei.

## Aktualisierungs-Protokoll

- **2026-07-14:** P0-Routing-Fix bewahrt die tatsächlich ausgeführte kanonische
  `AiRoute` für Audit, Snapshot und Resume (PR #730).
- **2026-07-14:** E2E-Stack-Boot repariert; Health-Smoke erstmals grün, fünf
  echte Spec-Defekte sichtbar und als eigenes Epic dokumentiert (PRs #731,
  #735).
- **2026-07-14:** Picker-Iststand und echter 7.6d-Restumfang gegen Code
  verifiziert (PR #732).
- **2026-07-14:** Parallel-flaky Frontend-Specs stabilisiert, vollständiges
  Frontend-Gate grün (PR #733).
- **2026-07-14:** Fehlender schemas-Scope im Pre-Push-Gate repariert
  (PR #734).
- **2026-07-14:** Golden-Gate-Zielspezifikation ergänzt und Slice-7-Stand in
  `PLAN.md` korrigiert (PRs #735, #736).
- **2026-07-14:** Agentenregeln, Roadmap und Tooling synchronisiert (PR #741).
- **2026-07-14:** Slice 7.6d abgeschlossen — `LlmProfileManager.vue` auf den
  connection-basierten `AiModelPicker` migriert, letzter produktiver legacy
  `ModelPicker.vue` entfernt (PR #742, Issue #740).
