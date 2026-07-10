# Handover

## Stand

- Branch: `codex/onboarding-provider-unification`
- letzter Basis-Commit: `bb2b3ea`
- Datum: 2026-07-10
- Slice: 0 — Forschung und Architektur
- Teststatus: Backend grün; Frontend-Tests bestanden, Vitest Exit 1 wegen vier
  bestehenden Environment-Teardown-Rejections
- context-mode: 1.0.169, funktionsfähig, Doctor-Warnung zum Hooks-Flag
- code-review-graph: MCP funktionsfähig; stabile CLI 2.3.6 via `uvx`
- Codegraph zuletzt aktualisiert: 2026-07-10, 944 Dateien
- Delta-Review: 0 geänderte Funktionen/Klassen, 0 betroffene Flows,
  0 Testlücken; Impact-Heuristik markiert das neue Doctor-Shellscript wegen
  generischer Shell-Knoten als hoch, ohne Produktcodepfad

## Dokumentations-Sync

- README.md: geprüft, nicht betroffen — noch kein Anwenderverhalten geändert
- AGENTS.md: geprüft, nicht betroffen
- CLAUDE.md: geprüft, nicht betroffen
- PLAN.md: Epic-Eintrag erforderlich
- docs/STATUS.md: geprüft, Produktstatus unverändert
- CHANGELOG.md: bewusst unverändert — nur Planung, keine Produktänderung
- docs/tooling/agent-tools.md: erstellt

## Fertig

- Repository-, Provider-, Embedding- und Persona-Analyse.
- offizielle Provider-/CLI-Quellen geprüft.
- Zielarchitektur, Slice-, Test- und Migrationsplan.
- ADRs für Provider, Embeddings und Single-User-Profil vorbereitet.
- secret-freier Tooling-Check.

## Noch offen

- bestehender Frontend-Vitest-Teardown-Fehler.
- globaler context-mode-Hooks-Doctor-Befund als Maintenance-Schritt.
- Kollision des globalen `code-review-graph`-Executables; kein Force-Overwrite.
- Slice 1 noch nicht begonnen.

## Entscheidungen

- kein Mega-Commit; ein PR pro Slice.
- bestehende Provider-Detection-SSoT bleibt.
- Subscription-Bridges nur nach separatem positiven Security-Spike.
- Embedding-Wechsel ist versioniert und nicht destruktiv.
- Persona-Wert ist tatsächliche Gesamtzahl; Floors werden Warnungen.

## Bekannte Risiken

- Provider-/Modell-Metadaten und Routing überlappen in mehreren Verträgen.
- aktuelle Index-Dimensionsreparatur migriert Embeddings nicht.
- sichtbarer Dashboard-Persona-Wert ist derzeit dekorativ.
- kein Onboarding-Pfad vorhanden; Provider-/Model-Picker und Settings sind
  mehrfach modelliert.
- sieben zentrale Frontend-Dateien haben laut Codegraph innerhalb von zwei
  Hops einen Impact auf 126 weitere Dateien.
- Python-3.14-Baseline weicht vom dokumentierten Python-3.12-Ziel ab.

## Nächste exakt ausführbare Schritte

1. Phase-0-Dokumentation und ADRs prüfen und atomar committen.
2. Frontend-Baselinefehler als separaten Fix/Issue behandeln.
3. Slice 1 mit RED-Contract-Tests für `ProviderConnection`, `AiModel` und
   `AiRoute` beginnen.

## Relevante Dateien

- `backend/app/contracts/llm_routing_contract.py`
- `backend/app/llm/providers/registry.py`
- `backend/app/services/llm_provider_registry.py`
- `backend/app/services/model_catalog_service.py`
- `backend/app/storage/embedding_service.py`
- `backend/app/api/simulation_prepare.py`
- `backend/app/services/prepare_service.py`
- `frontend/src/components/v4/dashboard/HeroNewRun.vue`

## Befehle zur Verifikation

```bash
scripts/agent-tools-doctor.sh
cd backend && uv run pytest tests/contracts/ -v
cd backend && uv run pytest -x -q
cd frontend && npm test -- --run
```
