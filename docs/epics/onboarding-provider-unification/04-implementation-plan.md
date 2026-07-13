# Implementation Plan

Jeder Slice beginnt mit RED-Tests, endet mit vollständiger Verifikation,
Codegraph-Delta, Dokumentations-Sync, Handover und atomarem Commit.

## Slice 0 — Forschung und Architektur

- Ziel: belegte Ausgangslage, ADRs, Migration, Tests und Tooling.
- Scope: ausschließlich Dokumentation und secret-freie Toolprüfung.
- Akzeptanz: Dateien dieses Epic-Verzeichnisses, ADR-0006 bis ADR-0008,
  Tooling-Doku und Doctor-Script; kein Produktcode.
- Rollback: Dokumentationscommit revertieren.
- Risiko: niedrig.
- Erwarteter Commit: `docs(epic): plan onboarding and provider unification`.

## Slice 1 — Kanonische Provider- und Modellverträge

- Ziel: `ProviderConnection`, `AiModel`, `AiRoute` als Pydantic-SSoT.
- Scope: Contracts, Schema-Dump, Zod-Spiegel, Adapter für bestehende
  `ProviderDescriptor`, `ModelEntry`, `LlmProfile` und Stage-Routes.
- Nicht-Ziel: UI-Redesign, Secret-Migration, CLI-Bridges.
- Migration: dual-read/new-write; keine vorhandenen Profile löschen.
- Tests: Contract-, Schema-, Adapter-, Roundtrip- und Extra-forbid-Tests.
- Akzeptanz: eine fachliche Provider-/Capability-Quelle; Detection-SSoT bleibt.
- Rollback: neue Writes deaktivieren, Legacy-Adapter weiter lesen.
- Risiko: hoch; betrifft Backend und Frontend-Verträge.
- Abhängigkeit: Phase 0 vollständig committet.

## Slice 2 — Benutzerprofil und Onboarding-Grundgerüst

- `UserProfile`, `OnboardingState`, lokale Avatar-Referenz.
- resumierbare State Machine und Guards.
- Single-User-Grenze bleibt explizit; kein Team-/Rechtesystem.
- Tests für Persistenz, Resume, MIME/Größe, Löschen und i18n.

## Slice 3 — Provider-Verbindungen

- API-Key-, Ollama-local- und Custom-HTTP-Verbindungen.
- Test/Discovery, Statusmodell und bestehender verschlüsselter Secret-Store.
- Subscription-Bridges nur nach separatem positivem Security-Spike.

## Slice 4 — Embedding-Setup und Migration

- getrennte Chat-/Embedding-Verträge.
- OpenAI, Gemini und Ollama lokal.
- kontrollierter Ollama-Download ohne Shell-String.
- versionierter Re-Embedding-Job mit Abbruch, Fortschritt und Rollback.
- kein `DROP INDEX` vor erfolgreicher Validierung.

## Slice 5 — Gemeinsamer Model-Picker und Routing

- eine zugängliche `AiModelPicker.vue`.
- alle Einsatzstellen auf denselben Vertrag und dieselbe Routing-Hierarchie.
- effektive Quelle sichtbar, keine stillen Fallbacks.
- Snapshot und Audit erweitern.

Detaillierter Sub-Plan mit 6 Sub-Slices (5.0-5.6):
[`docs/epics/onboarding-provider-unification/slice-5-subplan.md`](slice-5-subplan.md).
Architekturentscheidung: [ADR-0009](../../decisions/0009-unified-model-picker.md)
(Status: Proposed 2026-07-13).

## Slice 6 — Persona-Count-Invariante

- den Dashboard-Wert in einen Run-Vertrag überführen.
- getrennten Step-2-Cap entfernen oder eindeutig umdeuten.
- Floors zu Warnungen machen; Quoten innerhalb des Budgets.
- E2E-Werte 1, 5, 10, 30, 50, 100.

## Slice 7 — Golden-Gate-System und Informationsarchitektur

- mit `feat/design-v4-epic` abstimmen, keine Parallelkopie.
- vorhandene `tokens-v3.css`/`states.css` erweitern, keinen dritten
  Token-Namespace erzeugen.
- Tokens, Shell, Onboarding, Settings, Model-Picker.
- WCAG AA, 320 px, Tastatur, Reduced Motion.
- Seitenleistenentscheidungen `wire | implement MVP | hide | defer`.
- `/settings-classic`, zweiten Model-Picker und Mock-Routing erst nach
  Import-/Impact-Nachweis deprecaten oder entfernen.

## Slice 8+ — eigenständige MVPs

Projekte, Datensätze, Vorlagen und Monitoring jeweils als eigener PR. Kein
Bereich wird halb implementiert als fertig markiert.
