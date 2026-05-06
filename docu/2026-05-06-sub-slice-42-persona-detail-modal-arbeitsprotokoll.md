# Sub-Slice 42 · PersonaDetailModal — Arbeitsprotokoll

**Datum:** 2026-05-06  
**Refs:** #203 (Composable-Refactor-Epic, Task 47)  
**Branch:** `feat/task-47-sub-42-persona-detail-modal`

---

## Ziel

Extraktion des Persona-Detail-Modal-Blocks aus `Step2EnvSetup.vue` in eine eigenständige Subkomponente `step2/PersonaDetailModal.vue`. Reduces LOC in der Monolith-Komponente und schafft eine klar abgegrenzte, testbare UI-Einheit.

---

## LOC Vorher / Nachher

| Datei | Vorher | Nachher |
|---|---|---|
| `Step2EnvSetup.vue` | 1235 | 1099 |
| `step2/PersonaDetailModal.vue` | — | 463 |

Netto-Reduktion: **-136 LOC** in `Step2EnvSetup.vue` (157 Template-Zeilen + 2 Leerzeilen entfernt, 21 Zeilen Komponenten-Tag + Import eingefügt).

---

## Was extrahiert wurde

### Template-Block (Zeilen 517–673 der Quelldatei)

Der vollständige Detail-Modal-Block mit:
- Modal-Overlay mit Backdrop-Click-Handler
- Header mit Kicker, Persona-Name, Handle
- Review-Bar (Status-Badge + Action-Buttons: Edit, Reject, Regenerate, Approve)
- Edit-Modus-Bar (Cancel, Save)
- Review-Issues-Liste (`<ul class="review-issues">`)
- Regenerate-Hint-Input
- Review-Error-Anzeige
- Read-only View (Bio, marginalia dl, topic-chips, persona-Text)
- Edit-Form (9 Felder: name, profession, bio, country, age, gender, mbti, interested_topics, persona)

### i18n-Keys (neu unter `step2.detailModal.*`)

Angelegt in `de.json` und `en.json`:
- `step2.detailModal.kicker`
- `step2.detailModal.reviewActive`
- `step2.detailModal.actions.{edit, reject, approve, save}`
- `step2.detailModal.fields.{age, gender, mbti, country, profession, displayName, bioShort, topicsCsv, personaLong}`

Bereits vorhandene Keys (`step2.persona.regenerate`, `step2.persona.regenerateHint`) wurden nicht überschrieben.

### Scoped Styles

Alle modal-bezogenen CSS-Klassen aus `Step2EnvSetup.vue` in `PersonaDetailModal.vue` dupliziert (scoped-CSS-Boundary erfordert das). `Step2EnvSetup.vue`-Styles wurden nicht verändert.

---

## Architektur-Hinweis

`PersonaDetailModal` ist eine **pure UI-Komponente ohne eigene Composable-Instanz**. Alle State-Refs (`editingProfile`, `reviewActionPending` etc.) und Helper-Funktionen (`statusVariant`, `getIssuesFor` etc.) werden als Props injiziert. Der Eltern-Component (`Step2EnvSetup.vue`) leitet sie aus `usePersonaActions()` durch.

Dieser Ansatz ist notwendig, weil `usePersonaActions` mit `profiles` und `selectedProfile` als Refs gebunden ist, die von `useSimulationPrepare` stammen. Eine zweite Instanziierung im Modal würde eine isolierte, leere State-Welt erzeugen.

Emits folgen dem Vue-3-Pattern: `update:selectedProfile`, `update:editingProfile`, `update:regenerateHint` als v-model-kompatible Events; `start-editing`, `cancel-editing`, `approve`, `reject`, `regenerate`, `save` als Aktions-Events.

---

## Test-Output

```
Test Files  1 passed (1)
Tests       14 passed (14)
```

Alle 14 Spec-Cases grün:
1. selectedProfile=null → Modal nicht im DOM
2. selectedProfile gesetzt → Modal im DOM, Header-Text korrekt
3. Backdrop-Click → emit update:selectedProfile=null + cancel-editing
4. x-Button → emit update:selectedProfile=null + cancel-editing
5. Approve-Button → emit approve
6. Reject-Button → emit reject
7. Regenerate-Button → emit regenerate
8. Edit-Button → emit start-editing
9. Save im Edit-Modus → emit save
10. Cancel im Edit-Modus → emit cancel-editing
11. Regenerate-Hint-Input → emit update:regenerateHint
12. Edit-Field name → emit update:editingProfile mit korrektem Patch
13. 2 Issues von getIssuesFor → 2 li-Elemente in .review-issues
14. reviewActionError → .review-error mit Text

---

## Akzeptanz-Belege

| Kriterium | Ergebnis |
|---|---|
| `wc -l Step2EnvSetup.vue` | 1099 (< 1100-Limit: bestanden) |
| Restspur `selectedProfile = null; cancelEditing()` | leer |
| Restspur `<!-- Modal: persona detail` | leer |
| i18n-Keys `detailModal` in de.json | vorhanden (Zeile 277) |
| i18n-Keys `detailModal` in en.json | vorhanden (Zeile 266) |
| `npm test -- --run` (full) | 427 passed, 41 files |
| `npm run check` (vue-tsc + coverage + build) | grün |
| Schema-Drift `git diff schemas/` | leer |

Akzeptanzgrenze `< 1100` bestanden (1099).

---

## Commit-Status

Kein Commit, kein Push (Hardstop laut Aufgabenspezifikation).
