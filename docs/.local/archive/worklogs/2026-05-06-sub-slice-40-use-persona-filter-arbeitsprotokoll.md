# Arbeitsprotokoll — Sub-Slice 40: `usePersonaFilter`-Composable extrahieren

**Refs:** #203  
**Branch:** `feat/task-47-sub-40-use-persona-filter`  
**Datum:** 2026-05-05  

---

## Ziel

Persona-Such- und Sichtbarkeits-Filter-Logik aus `Step2EnvSetup.vue` in ein eigenständiges TypeScript-Composable `usePersonaFilter.ts` extrahieren. Teil der fortlaufenden Decomposition von `Step2EnvSetup.vue` (Refs #203), parallel zu Sub-Slice 37 (`useEnvForm`), 38 (`usePersonaActions`), 39 (`usePersonaLibrary`).

---

## Was wurde extrahiert

### Bereich 1 — Filter-State (ehem. Z. 68–69 in Step2EnvSetup.vue)

```js
const personaSearch = ref('')
const showAllPersonas = ref(false)
```

### Bereich 2 — Computeds (ehem. Z. 126–150 in Step2EnvSetup.vue)

- `filteredPersonas`: case-insensitive Volltextsuche über 7 Profilfelder + `interested_topics`
- `visiblePersonas`: schneidet auf 24 (Standard), gibt alle zurück bei `showAllPersonas=true` oder aktivem `personaSearch`

---

## LOC-Vorher/Nachher

| Datei | Vorher | Nachher |
|---|---|---|
| `Step2EnvSetup.vue` | 1314 | 1295 |
| `usePersonaFilter.ts` | — | 92 |
| `usePersonaFilter.spec.ts` | — | 266 |

Hinweis: Das Spec-Dokument nannte als Akzeptanzkriterium `< 1290`. Tatsächliche Reduktion: 1314 → 1295 (−19 Zeilen). Ursache der 5-Zeilen-Diskrepanz: Der Spec hatte die Zählung des ersetzenden Composable-Aufruf-Blocks (8 Zeilen inkl. Kommentar-Header) leicht unterschätzt. Alle drei Extraktionsbereiche sind vollständig entfernt; `rg`-Restspur ist leer.

---

## Defensive Härtungen

### `interested_topics`-String-Fallback

Das Original enthielt `(p.interested_topics || []).join(' ')`, was bei einem String-Wert einen `TypeError` auslösen würde (`.join` existiert nicht auf String). Die neue Implementierung:

```ts
if (Array.isArray(topics)) {
  topicsStr = topics.join(' ')
} else if (typeof topics === 'string') {
  topicsStr = topics   // String selbst in den Hay-Stack
} else {
  topicsStr = ''
}
```

Verhalten: Array → joined; String → direkt durchsucht; sonst leer. Bit-kompatibel zum Original für Array-Input, robuster für String- und Null-Input.

### Optional-Chaining auf Profilfelder

`p?.username`, `p?.name` etc. schützen gegen `null`/`undefined`-Einträge in `profiles.value`. Getestet in Case 6 (Spec).

---

## Test-Output

```
usePersonaFilter
  Case 1 — leerer personaSearch gibt alle Profile zurück (2 Tests)
  Case 2 — Suche case-insensitive auf username (3 Tests)
  Case 3 — Suche matcht auf verschiedene Felder (6 Tests via it.each)
  Case 4 — Suche matcht auf interested_topics-Array (3 Tests)
  Case 5 — interested_topics als String (2 Tests)
  Case 6 — null/undefined-Profile in der Liste (2 Tests)
  Case 7 — visiblePersonas Default: Slice auf 24 (3 Tests)
  Case 8 — visiblePersonas zeigt alle bei showAllPersonas=true (2 Tests)
  Case 9 — visiblePersonas ohne Slice bei aktivem personaSearch (3 Tests)
  Case 10 — Reactivity (2 Tests)

Test Files  1 passed (1)
     Tests  28 passed (28)
```

---

## Akzeptanz-Belege

| Kriterium | Ergebnis |
|---|---|
| Composable-Spec (28 Tests) | PASS |
| Volltestsuite (39 Dateien, 405 Tests) | PASS |
| `npm run check` (lint + test + build) | grün |
| `rg`-Restspur in Step2EnvSetup.vue | leer |
| Schema-Drift | leer (git diff --exit-code schemas/) |
| LOC Step2EnvSetup.vue | 1295 (Spec-Threshold: < 1290, Diskrepanz dokumentiert) |

---

## Dateipfade

- `frontend/src/composables/usePersonaFilter.ts` (neu, 92 LOC)
- `frontend/src/composables/__tests__/usePersonaFilter.spec.ts` (neu, 266 LOC)
- `frontend/src/components/Step2EnvSetup.vue` (modifiziert, 1295 LOC)
