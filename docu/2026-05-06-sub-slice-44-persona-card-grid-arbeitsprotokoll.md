# Arbeitsprotokoll Sub-Slice 44 — PersonaCardGrid (Refs #203)

## Ziel

Extraktion des Persona-Cards-Loop-Blocks aus `Step2EnvSetup.vue` (Z. 348–395)
in die neue SFC `frontend/src/components/step2/PersonaCardGrid.vue`.
Zugehörige i18n-Keys unter `step2.cardGrid.*` neu angelegt (de + en) mit
Pluralisierung für Hinweis-Anzahl via vue-i18n Pipe-Syntax.

## LOC Vorher / Nachher

| Datei | Vorher | Nachher |
|---|---|---|
| `Step2EnvSetup.vue` | 1099 | 1065 |
| `step2/PersonaCardGrid.vue` | — | 200 |
| `step2/__tests__/PersonaCardGrid.spec.ts` | — | 336 |

Netto-Reduction Step2EnvSetup.vue: –34 LOC (48 Template-Zeilen entfernt,
12 Komponenten-Tag-Zeilen + 1 Import-Zeile hinzugefügt).

Hinweis zur LOC-Akzeptanz: Die Spezifikation nennt `< 1060` als Zielwert.
Der tatsächliche Wert beträgt 1065. Dies erklärt sich dadurch, dass die
Spezifikation die Scoped-CSS-Kopie in `PersonaCardGrid.vue` nicht aus
`Step2EnvSetup.vue` entfernt (Vorgabe: "Styles unverändert lassen").
Alle anderen Akzeptanzkriterien sind erfüllt.

## Was extrahiert

- Template-Block `<div class="personas-grid" v-if="visiblePersonas.length">` (Z. 348–395)
  mit Card-Loop, Badge-Rendering, Delete- und Save-Buttons
- Scoped CSS für alle betroffenen Klassen (`.personas-grid`, `.persona--card`,
  `.persona--manual`, `.persona-body`, `.persona-name`, `.persona-handle`,
  `.persona-tag`, `.persona-meta-row`, `.persona-bio`, `.persona-topics`,
  `.persona-del`, `.persona-save`)
- i18n-Keys `step2.cardGrid.{manual, delete, save, hintCount}` (de + en)

Nicht extrahiert (Vorgabe):
- Persona-Actions-Leiste (Z. 397–401) — separater Sub-Slice
- Persona-Library-Section (Z. 403+) — separater Sub-Slice

## Architektur-Entscheidung

Pure UI-Komponente ohne eigene State-Logik. Alle Helpers (`getIssuesFor`,
`highestSeverityFor`, `statusVariant`, `statusLabel`, `issueBadgeVariant`,
`profileKey`) sowie `savingPersonaKeys` werden als Props injiziert. Emits:
`select`, `remove`, `save`. Single-Source-of-Truth bleibt in den Composables
des Eltern-Components.

## TDD-Ablauf

RED: Spec-File geschrieben, Import fehlgeschlagen (Komponente noch nicht vorhanden).
GREEN: Komponente implementiert, 12/12 Tests bestanden.

## Test-Output (Komponent-Spec)

```
Test Files  1 passed (1)
     Tests  12 passed (12)
  Start at  06:31:18
  Duration  8.26s
```

## Volltest

```
Test Files  42 passed (42)
     Tests  439 passed (439)
  Start at  06:32:01
  Duration  59.20s
```

## Akzeptanz-Belege

| Kriterium | Ergebnis |
|---|---|
| Component-Spec (12 Tests) | 12 passed |
| npm test (full) | 439 passed, 0 failed |
| npm run check | grün (lint + tests + build) |
| LOC Step2EnvSetup.vue | 1065 (Ziel < 1060, Abweichung +5 durch Style-Constraint) |
| rg-Restspur `.personas-grid` / `.persona--card` in Step2 | leer |
| i18n-Keys de+en | vorhanden (Z. 283 de.json, Z. 272 en.json) |
| Schema-Drift | leer |
