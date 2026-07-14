# Agora — Entwicklungsplan

Stand: **2026-07-14**

`PLAN.md` beschreibt ausschließlich zukünftige Arbeit, Prioritäten und Reihenfolge.
Der verifizierte Istzustand steht in [`docs/STATUS.md`](docs/STATUS.md). Bereits
Ausgeliefertes gehört in [`CHANGELOG.md`](CHANGELOG.md), ADRs, Worklogs oder die
Git-Historie. Ein Entwicklungsplan ist kein Dachboden für jede Idee, die seit Mai
irgendwann einmal technisch plausibel klang.

## Leitplanken

- lokal-first und Single-User gemäß ADR-0001
- Provider-agnostische, OpenAI-kompatible Schnittstellen ohne Cloud-Lock-in
- Pydantic-v2-Verträge als Backend-SSoT, Zod und JSON-Schemas als geprüfte Spiegel
- Chat-Routing und Embedding-Konfiguration bleiben getrennte Vertragswelten
- `AiModelPicker`, `AiModelRef` und die kanonische Route sind die einzigen neuen
  Modell-/Routing-Abstraktionen
- Evidence-Gating-Hartanker aus ADR-0002 werden nicht geschwächt
- jeder Slice ist atomar, testgetrieben, dokumentiert und separat mergebar

## Prioritäten

| Priorität | Arbeit | Tracking | Ergebnis |
|---|---|---|---|
| P0 | fünf rote E2E-Smokes reparieren | [#739](https://github.com/arn0ld87/agora/issues/739) | 6/6 Smokes stabil grün |
| P0 | PR-Trigger und Required Check reaktivieren | Teil von #739 | Defekte werden vor dem Merge blockiert |
| P1 | Slice 7.6d abschließen | [#740](https://github.com/arn0ld87/agora/issues/740) | letzter Legacy-`ModelPicker` entfernt |
| P1 | Security-Hardstop `nltk` | #672 | Entscheidung/Fix bis 2026-07-30 |
| P1 | Trivy-OS-Layer-Hardstop | Risk Register | Base-Image-Fix bis 2026-08-30 |
| P2 | Persona-Count-E2E-Matrix | neuer atomarer Slice | 1/5/10/30/50/100 nachgewiesen |
| P2 | Golden-Gate Responsive/Visual QA | einzelne Regression-Slices | keine bekannten Zielbild-Abweichungen |
| P2 | Phase-F-Restpunkt Provider-Detection | [#671](https://github.com/arn0ld87/agora/issues/671) | vereinheitlicht oder bewusst dokumentiert |
| P3 | `--agora-*`-Tokenmigration | eigener Migrations-Slice | konsistente Tokens ohne Parallelbibliothek |
| P3 | Embedding-Folgen | getrennte Slices | Batch, Project-Scope und Fact-Search vervollständigt |
| P3 | Observability Slice 4 | bestehender Plan | SLOs und Alerts produktionsnah definiert |

## P0: E2E-Smokes und CI-Gate

Tracking: [Issue #739](https://github.com/arn0ld87/agora/issues/739)

Der Stack bootet im GitHub-Runner und der Health-Smoke ist grün. Die verbleibenden
Defekte werden als eigenständige Fix-Slices bearbeitet:

1. **Upload + Graph**
   - API-Erfolg bis zur UI-/Store-Verdrahtung verfolgen
   - `graphData` sichtbar und deterministisch rendern
2. **Minimalreport**
   - Outline-/Zod-Spiegel-Fehler isolieren
   - vollständigen Minimalreport bis `completed` prüfen
3. **Report-Modi**
   - `force_regenerate` und Mode-Transitionen stabilisieren
4. **Golden-Gate Accessibility**
   - konkrete Route und Regel beheben, keine A11y-Ausnahme hinzufügen
5. **AiModelPicker**
   - Route-/UI-Drift nach der kanonischen Migration beseitigen
6. **CI-Reaktivierung**
   - Workflow mehrfach stabil grün ausführen
   - `pull_request`-Trigger in eigenem Commit aktivieren
   - Required-Check-Konfiguration dokumentieren

Akzeptanz: keine Skips, keine abgeschwächten Assertions und keine pauschalen Retries
als Ersatz für Ursachenbehebung.

## P1: Slice 7.6d, Legacy-Picker entfernen

Tracking: [Issue #740](https://github.com/arn0ld87/agora/issues/740)

Reihenfolge:

1. Tests für das erwartete Verhalten von `LlmProfileManager.vue` ergänzen bzw.
   präzisieren.
2. Consumer auf `AiModelPicker` und `AiModelRef` migrieren.
3. Persistenz, Validierung, Fehlermeldungen und Profilsemantik verifizieren.
4. alle direkten und indirekten Referenzen auf `ModelPicker.vue` entfernen.
5. Legacy-Komponente, verwaiste Exporte, Styles und Tests löschen.
6. Frontend-Gate und relevante E2E-Smokes ausführen.
7. `STATUS.md` und Epic-Handover aktualisieren.

Nicht Teil dieses Slices: Tokenmigration, neue Provider, neue Routing-Verträge oder
eine weitere Komponentenbibliothek.

## P1: Security-Hardstops

Source of Truth:
[`docs/dependency-risk-register.md`](docs/dependency-risk-register.md)

- **2026-07-30:** `nltk` PYSEC-2026-597 / GHSA-p4gq-832x-fm9v, Tracking #672
- **2026-08-30:** Trivy OS-Layer CVE-2026-24049 / CVE-2026-23949

Jede Ausnahme braucht Issue, Owner, Begründung, Deadline und expliziten Hardstop.
Stillschweigendes Verlängern ist keine Risikobehandlung, sondern Kalenderkosmetik.

## P2: Onboarding- und Provider-Unification-Folgen

### Persona-Count-Invariante

Ein zentraler E2E-Nachweis muss die Werte **1, 5, 10, 30, 50 und 100** abdecken:

- Eingabe und Persistenz
- Spawn-Anzahl
- OASIS-Übergabe
- Fortschrittsanzeige
- Report-Metadaten
- Resume-Verhalten

### Embedding-Restarbeiten

Als getrennte Slices planen:

- Gemini-Batch-Embedding
- echter `scope="project"`-Filter
- vollständige Umstellung des Fact-Search-Lesepfads auf den versionierten Index

Keine Vermischung mit Chat-Provider-Routing.

### Provider-Detection

Issue #671 entscheidet, ob `embedding_service._detect_provider` an
`backend/app/llm/providers/registry.py::detect_provider` delegiert oder absichtlich
separat bleibt. Das Ergebnis muss testfixiert und dokumentiert sein.

## P2/P3: Golden-Gate-System

1. Responsive Regressionen gegen
   [`docs/ui/golden-gate-workbench.md`](docs/ui/golden-gate-workbench.md) schließen.
2. visuelle und interaktive Abweichungen als kleine, routebezogene Slices bearbeiten.
3. `--agora-*`-Tokenwechsel separat migrieren:
   - Mapping und Deprecation-Plan
   - mechanische Migration
   - visuelle Regressionstests
   - Entfernung alter Tokens

Keine parallele UI-Bibliothek neben den bestehenden produktiven Komponenten.

## Spätere MVPs

Erst nach stabilen Gates und abgeschlossenem Picker-Cut:

- Projekte
- Datensätze
- Vorlagen
- Monitoring-Oberflächen
- Observability SLOs/Alerts
- noch offene v1.0-Output-Vertragsfolgen

Jedes MVP erhält eigenes Problemstatement, ADR-Bedarf, Vertragsänderungen,
Akzeptanzkriterien und Rollback-Plan.

## Definition of Done für jeden Slice

- [ ] Scope und Out-of-Scope dokumentiert
- [ ] Tests zuerst oder gemeinsam mit dem Verhalten geändert
- [ ] relevante Backend-, Frontend- und Schema-Gates grün
- [ ] keine neuen lokalen Provider-/Routing-Heuristiken
- [ ] Migration und Rollback beschrieben, falls persistierte Daten betroffen sind
- [ ] `docs/STATUS.md` nur bei geändertem Istzustand aktualisiert
- [ ] Epic-Handover enthält die unmittelbar nächste Fortsetzung
- [ ] keine historischen Protokolle in `PLAN.md` angehängt

## Referenzen

- [`docs/STATUS.md`](docs/STATUS.md) – verifizierter Istzustand
- [`docs/epics/onboarding-provider-unification/04-implementation-plan.md`](docs/epics/onboarding-provider-unification/04-implementation-plan.md) – detaillierte Epic-Reihenfolge
- [`docs/epics/e2e-smoke-specs/README.md`](docs/epics/e2e-smoke-specs/README.md) – E2E-Befunde
- [`docs/ui/golden-gate-workbench.md`](docs/ui/golden-gate-workbench.md) – UI-Zielbild
- [`docs/dependency-risk-register.md`](docs/dependency-risk-register.md) – Security-Hardstops
- [`AGENTS.md`](AGENTS.md) – operative Agentenregeln