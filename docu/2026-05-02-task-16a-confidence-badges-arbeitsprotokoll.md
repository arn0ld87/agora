# Sub-Slice 16a — ConfidenceBadge pro Section + Hover-audit_trail

Datum: 2026-05-02
Branch: feat/layer-4-task-16a-confidence-badges
Refs: #173

## Was wurde gemacht

### Neue Dateien

- `frontend/src/utils/confidenceUtils.ts` — Shared-Logik: `deriveLabel`, `aggregateSectionConfidence`, Typen `ConfidenceBucket`, `SectionConfidenceResult`, `AuditEntry`.
- `frontend/src/components/ui/ConfidenceBadge.vue` — Vue 3 SFC mit Pill-Badge (oklch-Tokens), Hover-Popover mit audit_trail-Liste, 200ms Schliess-Delay.
- `frontend/src/components/ui/__tests__/ConfidenceBadge.spec.ts` — 8 Vitest-Tests fuer deriveLabel + Badge-Klassen + Hover-Popover.

### Geaenderte Dateien

- `frontend/src/components/Step4Report.vue`:
  - Import von `ConfidenceBadge`, `deriveLabel`, `aggregateSectionConfidence`, `SectionConfidenceResult`.
  - Hilfsfunktionen `sectionConfidence`, `sectionConfidenceScore`, `sectionConfidenceLabel`, `sectionConfidenceAuditTrail` fuer typsicheres Template.
  - Section-Header-Template: `ConfidenceBadge` neben Status-Badge wenn Evidence vorhanden.
  - CSS: `.outline-badges` Flex-Wrapper, `.outline-head` auf `align-items: center`.
- `frontend/src/components/__tests__/Step4Report.spec.ts`:
  - 5 neue aggregateSectionConfidence-Tests (Arithmetik, Rundung, Determinismus, Flatten).
  - 1 Integrations-Test: 2 Sections -> 2 ConfidenceBadge-Instanzen.

## Architektur-Entscheidung

`deriveLabel` und `aggregateSectionConfidence` wurden in `confidenceUtils.ts` ausgelagert, da `<script setup>` keine ES-Module-Exports erlaubt. Beide Komponenten und alle Tests importieren direkt aus Utils.

## Test-Ergebnis

Vorher: 97 Tests (13 Dateien). Nachher: 112 Tests (14 Dateien). Alle gruen.
Lint: clean. Build: clean. Schema-Diff: clean.
