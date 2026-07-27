# Agora — Status

**Stand:** 27.07.2026  
**Geprüfte Main-Baseline:** `d5bdbada`  
**Produktversion:** `0.8.0` Technical Preview

Diese Datei beschreibt ausschließlich den verifizierten Istzustand. Strategische Release-Ziele stehen in [`ROADMAP.md`](../ROADMAP.md), konkrete Arbeitspakete in [GitHub Issues](https://github.com/arn0ld87/agora/issues), ausgelieferte Änderungen in [`CHANGELOG.md`](../CHANGELOG.md).

Historische Pläne sind keine aktiven Steuerungsquellen: [`docs/archive/planning/`](archive/planning/)

## Versionsstatus

Die Produktreife wird ab diesem Dokumentationsumbau über [`VERSION`](../VERSION) geführt.

<!-- BEGIN_AUTOGEN_VERSIONS -->
| Komponente | Pfad | Version |
|---|---|---|
| Backend | `backend/pyproject.toml` | 0.8.0 |
| Frontend | `frontend/package.json` | 0.8.0 |
| Root | `package.json` | 0.8.0 |
<!-- END_AUTOGEN_VERSIONS -->

`VERSION` ist die Produkt-SSoT. Alle Komponentenmanifeste (`backend/pyproject.toml`, `package.json`, `frontend/package.json`) und der README-Badge sind auf `VERSION=0.8.0` synchronisiert; ein Drift-Check läuft in CI (`version-drift.yml`) und lokal (`pre-push-gate.sh schemas`). Der Version-Cut-Ablauf ist in [`docs/runbooks/release-versioning.md`](runbooks/release-versioning.md) beschrieben.

## Tests

<!-- BEGIN_AUTOGEN_TESTS -->
| Kategorie | Anzahl | Methode |
|---|---|---|
| Backend Tests (collected) | 3733 | `cd backend && uv run pytest --collect-only -q` |
| Frontend Test-Files | 171 | `find frontend/src \( -name '*.spec.ts' -o -name '*.spec.js' -o -name '*.test.ts' -o -name '*.test.js' \)` |
<!-- END_AUTOGEN_TESTS -->

Hinweise:

- Zwei Redis-Integrationstests skippen ohne `TEST_REDIS_URL` kontrolliert.
- Die Frontend-Zahl zählt Testdateien, nicht einzelne Testfälle.
- Die Zahlen stammen aus dem letzten synchronisierten Status und müssen nach größeren Merges erneut erzeugt werden.

## Produktreife

Agora besitzt eine vollständige fachliche Grundpipeline:

- resumierbares Onboarding und lokales Benutzerprofil
- Provider-Verbindungen, Secret Store und Modell-Discovery
- getrennte Chat- und Embedding-Konfiguration
- Dokument-/Webseitenaufnahme und Knowledge-Graph-Build
- Persona-Erzeugung, Review und Simulation
- Run-Dashboard, Status, Stop/Pause/Resume und Live-Ereignisse
- Evidence-orientierte Reports und Exporte
- Compare-, Graph-Diff- und Observability-Grundlagen
- fortsetzbare Embedding-Migration für Entity- und Fact-Vektoren

Der Stand ist dennoch Technical Preview, weil die E2E-Kernpipeline noch nicht als verpflichtender Pull-Request-Check erzwungen wird und die verbleibenden Frontend-Altpfade weiter konsolidiert werden: Migration der v3-Inhaltskomponenten in v4-Wrapper ([#922](https://github.com/arn0ld87/agora/issues/922)). Der `/home`-Redirect auf `/dashboard` ist umgesetzt ([#915](https://github.com/arn0ld87/agora/issues/915), ADR-0010); `Home.vue` bleibt bis `1.0.0` physisch erhalten.

## E2E-Smokes

[Issue #739](https://github.com/arn0ld87/agora/issues/739) (sechs rote E2E-Smokes reparieren) ist **geschlossen** (19.07.2026). Seither laufen die sechs Kern-Smokes (Health, Upload + Graph, Minimalreport, Report-Modi, Golden-Gate Accessibility, AiModelPicker) im `e2e-smokes`-Workflow durchgehend grün: **20 von 20 aufeinanderfolgenden Läufen** über `push` und `pull_request` zwischen 21.07.2026 und 22.07.2026 (letzter Lauf auf Commit `37320dbf`) sind erfolgreich, kein einzelner Flake in dieser Serie.

Offen ist ausschließlich die Erzwingung: `main` besitzt aktuell **keine Branch-Protection** (`gh api repos/arn0ld87/agora/branches/main/protection` → 404 „Branch not protected“). Der `pull_request`-Trigger läuft mit, ist aber kein verpflichtender Merge-Check. Der Weg dahin steht in [`docs/runbooks/e2e-required-check.md`](runbooks/e2e-required-check.md).

## Quality Gates

| Gate | Status |
|---|---|
| Backend PR Smoke: Ruff + Mypy + Contract-Tests | verpflichtend |
| Frontend PR Smoke: Lint + Typecheck + Unit-Tests + Build | verpflichtend |
| Backend Full Tests + Coverage | `push:main` oder Label |
| Frontend Full Tests + Coverage | `push:main` oder Label |
| Schemas und Contract-Spiegel | vorhanden |
| E2E-Kernpipeline | 20 grüne Läufe in Folge (21.–22.07.2026, zuletzt Commit `37320dbf`); `pull_request`-Trigger aktiv; Required-Erzwingung ausstehend (`main` ohne Branch-Protection) |

Lokale Befehle:

```bash
bash scripts/pre-push-gate.sh
bash scripts/pre-push-gate.sh backend
bash scripts/pre-push-gate.sh frontend
bash scripts/pre-push-gate.sh schemas
```

## Coverage-Baseline

Die Werte sind älter als der aktuelle Codebestand und müssen für `0.9.0` neu erzeugt werden.

| Bereich | letzte Messung | Ergebnis | CI-Schwelle |
|---|---|---:|---:|
| Backend gesamt | 10.06.2026 | 66,00 % | 60 % |
| Frontend Statements | 10.05.2026 | 50,46 % | 28 % |
| Frontend Branches | 10.05.2026 | 39,56 % | 28 % |
| Frontend Functions | 10.05.2026 | 38,59 % | 28 % |
| Frontend Lines | 10.05.2026 | 52,50 % | 28 % |

Strukturelle Lücken liegen vor allem in OASIS-/Neo4j-Integrationspfaden, Canvas-/WebGL-Komponenten und großen Wizard-/View-Komponenten.

## Kanonische technische Pfade

- API-Verträge: `backend/app/contracts/`
- Frontend-Spiegel: `frontend/src/contracts/` und `schemas/`
- Provider-Erkennung: `backend/app/llm/providers/registry.py::detect_provider`
- Provider-Verbindungen: `ProviderConnection`
- kanonische Route: `AiRoute` / `LlmRoute`
- kanonische Modellauswahl: `frontend/src/components/v4/forms/AiModelPicker.vue`; seit Issue #890 auch im Step-2-Environment-Setup. Eine Auswahl ist eine `AiModelRef` und wird als `ai_model_ref` an `/prepare` gesendet; ohne Auswahl entscheidet die Backend-Präzedenz (Projektprofil vor Workspace-Default). Modellauswahl wird im Frontend nicht mehr persistiert
- aktive Embedding-Konfiguration: `embedding_service.py` und `embedding_migration.py`
- strukturierte LLM-JSON-Outputs: `LLMClient.chat_json` mit Pydantic-Schema (strict-json_schema-Pfad); rohe OpenAI-Clients für strukturierte Outputs vermeiden
- Subagent-Dispatch: Routing-Matrix in [`docs/runbooks/subagent-routing.md`](runbooks/subagent-routing.md) und [`CLAUDE.md`](../CLAUDE.md); Agentdefinitionen unter `.claude/agents/*-m3.md` (Modell `MiniMax-M3`, ab 20.07.2026)
- Evidence-Gating: ADR-0002-Hartanker

Chat-Routing und Embedding-Konfiguration bleiben getrennte Vertragswelten.

## Bekannte Konsolidierungsschuld

- die fünf klassischen Prozess-Wrapper-Views sind entfernt; ihre benannten Deep-Links bleiben als v4-Redirects kompatibel. `/agora-2026` ist als Designreferenz unter `docs/design-reference/agora-2026/` archiviert und nicht produktiv geroutet; v4-Ballast-Views sind entfernt ([PR #877](https://github.com/arn0ld87/agora/pull/877)). Verbleibend: Migration der v3-Inhaltskomponenten `Step2EnvSetup.vue`/`Step3Simulation.vue`/`Step4Report.vue` in v4-Wrapper ([#922](https://github.com/arn0ld87/agora/issues/922)). Der `/home`-Redirect auf `/dashboard` ([#915](https://github.com/arn0ld87/agora/issues/915)) ist umgesetzt
- ein React-/Lovable-Neubau ist als Prototyp umgesetzt, aber nicht als Zielentscheidung freigegeben (Details im nächsten Abschnitt)
- Legacy-LLM-Profile und Provider-Connections besitzen noch Übergangspfade
- der credential-basierte Runtime-Provider-Override (`useRuntimeLlmOptions`, `@deprecated` Slice 5.5) ist mit der connection-gebundenen `AiModelRef` unvereinbar und in Step 2 daher gegenseitig ausgeschlossen. Solange er existiert, hält `useEnvForm` weiterhin `modelOption`/`customModel` — allerdings ohne Persistenz. Die Ablösung wird in [Issue #903](https://github.com/arn0ld87/agora/issues/903) geführt
- die Browser-Keys `agora.lastModel` und `agora.lastCustomModel` haben seit Issue #890 keinen produktiven Reader oder Writer mehr; vorhandene Werte werden bewusst nicht gelöscht und bleiben wirkungslose Altlast
- einzelne Provider-Erkennungen beruhen weiterhin auf URL-/Modell-Heuristiken
- Frontend- und Backend-Provider-Vokabular sind nicht an jeder SSE-Grenze synchron

## Frontend-Next-Stand (React/Lovable)

- **Produktiv:** Vue ist die einzige ausgelieferte Frontend-Technologie. `/home` leitet seit [#915](https://github.com/arn0ld87/agora/issues/915) per ADR-0010 auf `/dashboard` um; die klassische Editorial-View `Home.vue` bleibt bis `1.0.0` physisch erhalten. Die Konsolidierung auf genau eine v4-Route je fachlicher Hauptfunktion läuft weiterhin unter [Issue #760](https://github.com/arn0ld87/agora/issues/760) und ist nicht abgeschlossen. Zudem werden die v3-Inhaltskomponenten `Step2EnvSetup.vue`/`Step3Simulation.vue`/`Step4Report.vue` noch produktiv über v4-Wrapper geroutet ([Issue #922](https://github.com/arn0ld87/agora/issues/922)).
- **Prototyp:** Ein Lovable-Projekt („Agora Runs Dashboard", angelegt 2026-07-16) existiert und wurde substanziell umgesetzt (23 Edits, TanStack-Router-SPA, 12 Routen, shadcn/ui). Es ist derzeit **nicht veröffentlicht** (`is_published: false`, keine URL) und **nicht** produktiv verdrahtet — weder Docker-Compose, GitHub-Workflows noch das Root-`package.json` referenzieren es. Der React-Code liegt vollständig außerhalb dieses Repositories. Die tatsächliche Funktionsvollständigkeit des Prototyps ist nicht codegeprüft belegt, sondern nur durch Commit-Aussagen behauptet.
- **Release-Status:** Kein Teil des freigegebenen Produktpfads vor `1.0.0`.
- **Zukunft:** Über eine spätere Migration ist keine Entscheidung getroffen.
- Beleg: [`docs/epics/frontend-next/2026-STATUS.md`](epics/frontend-next/2026-STATUS.md).

## Security und Betrieb

- Betriebsmodell: experimentelles Single-User-System, kein öffentliches SaaS
- Zugriff bevorzugt über Tailscale, VPN oder Reverse Proxy
- API-Auth über `AGORA_AUTH_TOKEN`
- SSE und Downloads über signierte Tickets
- Secrets werden nicht in Report-/Simulation-Artefakte serialisiert
- Readiness prüft Neo4j, Redis, Upload-Verzeichnis und Embedding-Konfiguration
- Dependency-Ausnahmen werden im [`dependency-risk-register.md`](dependency-risk-register.md) geführt
- Ontology-Upload (`/ontology/generate`) räumt bei Datei-I/O-Fehlern zwischen Projektanlage und Service-Übergabe das halb angelegte Projekt zuverlässig auf (Issue #899); ein scheiterndes Aufräumen wird protokolliert, ohne die Fehlerantwort zu verfälschen

Aktuelle Hardstops:

- NLTK-Advisories: 28.09.2026 gemäß ADR-0004/Risk Register
- Trivy OS-Layer: 30.08.2026

## Nächste Prioritäten

1. E2E als verpflichtenden Pull-Request-Check aktivieren (Läufe sind stabil grün, Branch-Protection auf `main` fehlt noch).
2. Vue-v4 als einziges Produktfrontend konsolidieren (Issue #760; Umsetzungskarte [#829](https://github.com/arn0ld87/agora/issues/829)).
3. Reproduzierbarkeit, Kostenbudgets und Kalibrierungsbaseline für `0.10.0` umsetzen.

Die vollständigen Release-Gates stehen in [`ROADMAP.md`](../ROADMAP.md).
