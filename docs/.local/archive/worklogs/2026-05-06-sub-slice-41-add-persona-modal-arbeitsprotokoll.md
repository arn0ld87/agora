# Sub-Slice 41 · AddPersonaModal — Arbeitsprotokoll

**Datum:** 2026-05-06  
**Refs:** #203 (Step2EnvSetup.vue Komponent-Extraktion)  
**Branch:** `feat/task-47-sub-41-add-persona-modal`

---

## Ziel

Extraktion des „Add Manual Persona"-Modals aus `Step2EnvSetup.vue` in eine eigenständige Subkomponente `step2/AddPersonaModal.vue`. Pure UI-Komponente ohne API-Aufrufe. Strings via vue-i18n. Props/Emits nach v-model-Konvention.

---

## LOC-Bilanz

| Datei | Vorher | Nachher |
|---|---|---|
| `Step2EnvSetup.vue` | 1295 | 1235 |
| `step2/AddPersonaModal.vue` | — | 272 (neu) |
| `step2/__tests__/AddPersonaModal.spec.ts` | — | 290 (neu) |

Differenz Step2EnvSetup.vue: −60 LOC (Modal-Block 69 Zeilen weg, 9 Zeilen `<AddPersonaModal …/>` + Import dazu).

---

## Was extrahiert wurde

**Template-Block Z. 674–742** (kompletter `<!-- Modal: add manual persona -->` Block) aus `Step2EnvSetup.vue`.

Komponenten-Signatur:

```typescript
interface Props {
  open: boolean
  persona: NewPersonaForm
  saving: boolean
}
emit: {
  'update:open': [value: boolean]
  'update:persona': [value: NewPersonaForm]
  submit: []
}
```

`NewPersonaForm`-Interface als exportierter Type in `AddPersonaModal.vue` (für den Spec-Import).

---

## i18n-Keys

Neue Keys unter `step2.addPersona.*` in `de.json` und `en.json`:

- `step2.addPersona.kicker`
- `step2.addPersona.title`
- `step2.addPersona.submit`
- `step2.addPersona.fields.*` (username, name, bio, profession, country, age, gender, mbti, topics, persona)
- `step2.addPersona.placeholders.*` (username, name, bio, profession, country, topics, persona)

`common.cancel` und `common.close` existierten bereits — keine Duplikate angelegt.

---

## Style-Strategie (Option 1)

Modal-relevante CSS-Klassen (`.modal`, `.modal-card`, `.modal-head`, `.kicker-mono`, `.modal-head h3`, `.form-grid`, `.form-row`, `.form-row--wide`, `.actions`, `.x`) wurden in `<style scoped>` von `AddPersonaModal.vue` **kopiert**.

`Step2EnvSetup.vue` behält diese Klassen unverändert, da der Detail-Persona-Modal (andere Komponente, gleiches `scoped`-CSS) sie weiterhin nutzt. Keine Style-Renames.

---

## TDD-Reihenfolge

1. Spec geschrieben (`AddPersonaModal.spec.ts`, 8 Tests) — RED bestätigt (Modul-Not-Found).
2. Komponente implementiert — GREEN bestätigt.

---

## Test-Output

```
Test Files  1 passed (1)
     Tests  8 passed (8)
  Duration  754ms
```

Voller Suite-Run nach Extraktion:

```
Test Files  40 passed (40)
     Tests  413 passed (413)
  Duration  11.25s
```

---

## Akzeptanz-Belege

| Check | Ergebnis |
|---|---|
| LOC Step2EnvSetup.vue < 1240 | 1235 ✓ |
| `showAddPersonaModal = false` in Step2 | leer ✓ |
| `<input v-model="newPersona.*"` in Step2 | leer ✓ |
| i18n `addPersona` in de.json + en.json | vorhanden ✓ |
| Schema-Drift | leer ✓ |
| `npm run check` (lint + test + build) | grün ✓ |
