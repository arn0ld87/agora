# Agora — Status

**Stand:** 18.07.2026  
**Geprüfte Main-Baseline:** `b068852`  
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
| Backend Tests (collected) | 3395 | `cd backend && uv run pytest --collect-only -q` |
| Frontend Test-Files | 168 | `find frontend/src \( -name '*.spec.ts' -o -name '*.spec.js' -o -name '*.test.ts' -o -name '*.test.js' \)` |
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

Der Stand ist dennoch Technical Preview, weil die Kernpipeline im E2E-Gate noch nicht vollständig grün ist und Altpfade in Frontend, Provider-Profilen und Dokumentation weiter konsolidiert werden.

## E2E-Smokes

Der Stack bootet im GitHub-Runner. Der Health-Smoke ist grün. Alle fünf Kern-Smokes sind lokal grün (Sub-Slices 1–5/5).

| Smoke | Status | Hauptbefund |
|---|---|---|
| Health | grün | Stack, Auth und Provider-Seeding funktionieren |
| Upload + Graph | grün (lokal, Sub-Slice 3/5) | Onboarding-Guard blockierte `/process/<id>`, nicht die State-Verkettung; Fix per Onboarding-Dismiss vor `page.goto` |
| Minimalreport | grün (lokal, Sub-Slice 2/5) | Onboarding-Guard blockierte `/report/<id>`; Fix per Onboarding-Dismiss + Outline-Sync aus dem Report-Contract (PR #771) |
| Report-Modi | grün (lokal, Sub-Slice 4/5) | Fehlende Persona-Fixture ließ den Report-Contract vor der Generierung mit `INCOMPLETE` abbrechen; der Spec seedet jetzt deterministisch den Persona-Floor |
| Golden-Gate Accessibility | grün (lokal, Sub-Slice 5/5) | Tertiär- und Statusfarben auf WCAG AA gehärtet, Form-Controls beschriftet und axe erst nach dem Route-Fade ausgeführt |
| AiModelPicker | grün (lokal, Sub-Slice 1/5) | mock-models-Seed-URL via `AGORA_E2E_MOCK_MODELS_BASE` lokal überschreibbar; CI-Verhalten unverändert (PR #769) |

Tracking: [Issue #739](https://github.com/arn0ld87/agora/issues/739)

Der `pull_request`-Trigger des E2E-Workflows bleibt deaktiviert, bis alle sechs Smokes mehrfach stabil grün sind. Danach muss der Workflow als Required Check aktiviert werden.

## Quality Gates

| Gate | Status |
|---|---|
| Backend PR Smoke: Ruff + Mypy + Contract-Tests | verpflichtend |
| Frontend PR Smoke: Lint + Typecheck + Unit-Tests + Build | verpflichtend |
| Backend Full Tests + Coverage | `push:main` oder Label |
| Frontend Full Tests + Coverage | `push:main` oder Label |
| Schemas und Contract-Spiegel | vorhanden |
| E2E-Kernpipeline | 4/6 lokal grün (Health + Sub-Slices 1–3/5), noch nicht verpflichtend |

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
- kanonische Modellauswahl: `frontend/src/components/AiModelPicker.vue`
- aktive Embedding-Konfiguration: `embedding_service.py` und `embedding_migration.py`
- Evidence-Gating: ADR-0002-Hartanker

Chat-Routing und Embedding-Konfiguration bleiben getrennte Vertragswelten.

## Bekannte Konsolidierungsschuld

- klassische Prozess-Views, v4-Views und `/agora-2026` existieren parallel
- ein React-/Lovable-Neubau ist beschrieben, aber nicht als Zielentscheidung freigegeben
- Legacy-LLM-Profile und Provider-Connections besitzen noch Übergangspfade
- einzelne Provider-Erkennungen beruhen weiterhin auf URL-/Modell-Heuristiken
- Frontend- und Backend-Provider-Vokabular sind nicht an jeder SSE-Grenze synchron
- `requirements.txt`, `pyproject.toml` und `uv.lock` sind nicht vollständig konsistent

## Security und Betrieb

- Betriebsmodell: experimentelles Single-User-System, kein öffentliches SaaS
- Zugriff bevorzugt über Tailscale, VPN oder Reverse Proxy
- API-Auth über `AGORA_AUTH_TOKEN`
- SSE und Downloads über signierte Tickets
- Secrets werden nicht in Report-/Simulation-Artefakte serialisiert
- Readiness prüft Neo4j, Redis, Upload-Verzeichnis und Embedding-Konfiguration
- Dependency-Ausnahmen werden im [`dependency-risk-register.md`](dependency-risk-register.md) geführt

Aktuelle Hardstops:

- NLTK-Advisories: 28.09.2026 gemäß ADR-0004/Risk Register
- Trivy OS-Layer: 30.08.2026

## Nächste Prioritäten

1. Sechs E2E-Smokes stabil grün machen und als PR-Gate aktivieren.
2. Vue-v4, Provider-/Routing-SSoT und Dependency-SSoT für `0.9.0` konsolidieren.
3. Reproduzierbarkeit, Kostenbudgets und Kalibrierungsbaseline für `0.10.0` umsetzen.

Die vollständigen Release-Gates stehen in [`ROADMAP.md`](../ROADMAP.md).
