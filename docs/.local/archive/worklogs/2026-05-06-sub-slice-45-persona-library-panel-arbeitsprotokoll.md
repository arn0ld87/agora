# Sub-Slice 45 — PersonaLibraryPanel Arbeitsprotokoll

**Datum:** 2026-05-06
**Refs:** #203
**Branch:** feat/task-47-sub-45-persona-library-panel

---

## Ziel

Extraktion der Persona-Library-Section aus `Step2EnvSetup.vue` in eine dedizierte Subkomponente `step2/PersonaLibraryPanel.vue`. Teil der Step2-Decomposition-Reihe (Sub-Slices 34–45, Refs #203).

---

## LOC Vorher / Nachher

- `Step2EnvSetup.vue` vorher: **1065 LOC**
- `Step2EnvSetup.vue` nachher: **1044 LOC** (−21 LOC netto; die Section hatte 32 LOC, Ersatz sind 9 LOC + 1 Import-Zeile)
- `PersonaLibraryPanel.vue` neu: **109 LOC** (Template + Script + Scoped-CSS)
- `PersonaLibraryPanel.spec.ts` neu: **223 LOC** (10 Testcases)

---

## Was extrahiert wurde

Die Library-Section (Z. 369–400 in der alten Datei):

```vue
<section v-if="phase >= 2" class="persona-library">
  ...32 LOC...
</section>
```

Der `v-if="phase >= 2"`-Guard bleibt im Eltern-Component als Conditional-Render-Guard. Die Subkomponente selbst kennt kein `phase`.

---

## Komponenten-Signatur

```typescript
interface Props {
  templates: Template[]   // personaTemplates aus usePersonaLibrary
  loading: boolean        // isLoadingPersonaLibrary
  error: string           // personaLibraryError
  usingIds: Set<string>   // usingPersonaTemplateIds
}

emit: {
  refresh: []
  use: [template: Template]
  remove: [templateId: string]
}
```

---

## i18n-Keys

Keine neuen Keys nötig. Existierende `step2.library.*`-Keys weiterverwendet:
- `step2.library.title`
- `step2.library.hint`
- `step2.library.refresh`
- `step2.library.use`
- `step2.library.empty`

---

## TDD-Ablauf

RED zuerst: Spec angelegt vor Komponente. Alle 10 Tests failed (Module not found).
GREEN: Komponente implementiert. Alle 10 Tests passed.

Besonderheit Test (8): `find('p.meta')` würde die Hint-Paragraph im Header matchen.
Lösung: `findAll('p.meta')` + gezieltes Find nach Fehlertext-Inhalt.

---

## Test-Output

```
Test Files  1 passed (1)
      Tests  10 passed (10)
   Duration  891ms
```

Voller Suite nach Extraktion:
```
Test Files  43 passed (43)
      Tests  449 passed (449)
   Duration  10.26s
```

---

## Akzeptanz-Belege

| Check | Ergebnis |
|---|---|
| LOC Step2EnvSetup.vue | 1044 < 1045 ✓ |
| rg Restspur (persona-library-head, persona-template in Step2) | leer ✓ |
| i18n-Keys step2.library.* | vorhanden in de.json ✓ |
| Schema-Drift | leer (EXIT 0) ✓ |
| npm test (full) | 449 passed ✓ |
| npm run check | EXIT 0 ✓ |
| vue-tsc --noEmit | keine TS-Fehler ✓ |
| vite build | ✓ built ✓ |
| PersonaLibraryPanel Coverage | 100% Statements, 100% Functions ✓ |
