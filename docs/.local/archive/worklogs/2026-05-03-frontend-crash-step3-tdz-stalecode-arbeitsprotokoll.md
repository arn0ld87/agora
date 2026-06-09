# Arbeitsprotokoll: Frontend-Crash Step3Simulation.vue — TDZ + Stale-Code

Datum: 2026-05-03
Agent: Claude Code (Opus)

---

## 1. Bug-Report

Beim Starten einer Simulation (nach Persona-Erstellung) erscheint nur der Hintergrund.
Keine GUI baut sich auf, der Run taucht nicht im Run Center auf.
Safari-Konsole zeigt weisse Seite + JS-Error.

---

## 2. Root-Cause-Analyse

### 2.1 Fehlermeldung (Safari)
```
ReferenceError: Cannot access 'consoleLogs' before initialization.
```
Location: `chunk-JHSZJ4FP.js` (kompilierte Vue-Setup-Funktion).

### 2.2 Code-Defekt
In `frontend/src/components/Step3Simulation.vue` stand die `watch(...)`-Anweisung **vor** der Destrukturierung von `useIncrementalLogPolling`:

```vue
// BUGGY (alte Reihenfolge)
watch(() => consoleLogs.value.length, ...)   // consoleLogs = TDZ
...
const { lines: consoleLogs } = useIncrementalLogPolling(...)
```

Vue 3 `<script setup>` kompiliert Top-Level-Code synchron in die `setup()`-Funktion.
`let`/`const` sind zwar gehoistet, aber im Temporal Dead Zone (TDZ) bis zur Deklarationszeile.
Der `watch()`-Getter wird bei Registrierung sofort synchron ausgewertet → greift auf `consoleLogs` zu → TDZ-Error.

### 2.3 Fix
Reihenfolge vertauscht: `useIncrementalLogPolling` **vor** `watch()`:

```vue
// KORREKT (neue Reihenfolge)
const { lines: consoleLogs, ... } = useIncrementalLogPolling({...})
watch(() => consoleLogs.value.length, ...)
```

Zeile 155 (Init) → Zeile 164 (Watcher).

### 2.4 Lokale Verifikation
- `npm run check` (frontend): 141 Tests passed, Build green.
- Source-Datei auf Disk: korrekte Reihenfolge bestätigt.

---

## 3. Deployment-Problem (Stale Compiled Code)

Trotz korrekter Source-Datei zeigte Safari nach dem Fix weiterhin den alten Fehler.
Analyse der kompilierten JS-Ausgabe in Safari DevTools bewies:
Der Browser führte **das alte Kompilat** aus (Watcher vor Init).

**Ursache:** Vite Dev-Server / Docker-Volume hat die Dateiänderung nicht in das zur Laufzeit ausgelieferte JS übernommen.

**Lösung:**
1. `docker compose restart agora` (Container-Neustart erzwingt Rebuild).
2. Safari: `Cmd + Option + E` (Cache leeren) → `Cmd + Shift + R` (hartes Reload).

---

## 4. Upstream-Check (Context7 + GitHub)

Auf expliziten Wunsch wurde Context7 nach Vue/Vite-HMR-Stale-Code-Bugs abgefragt.
Ergebnis: Kein bekannte Upstream-Bug für dieses Verhalten.
Die TDZ-Fehlermeldung ist korrektes JS/TS-Verhalten, kein Vue-Defekt.
Vite-HMR-Probleme in der Doku werden primär auf falsches Import-Casing oder zirkuläre Abhängigkeiten zurückgeführt.

---

## 5. Aktionen

| # | Aktion | Status |
|---|---|---|
| 1 | TDZ-Bug identifiziert (Safari-Konsole + Source-Analyse) | Done |
| 2 | Code-Reorder in `Step3Simulation.vue` angewendet | Done |
| 3 | Lokaler Build + Test verifiziert (`npm run check`) | Done |
| 4 | Context7-Upstream-Check (Vue Core, Vite) | Done |
| 5 | Docker-Container `agora` neugestartet | Done |
| 6 | Safari-Cache-Clear + Hard-Reload an User übergeben | Done (Reload erst nach Container-Restart wirksam) |
| 7 | Followup-Sub-Slice: Component-Mount-Smoketest für Step3Simulation.vue | Open |

---

## 6. Lessons Learned

- In `<script setup>` darf keine Variable (auch Destrukturierungen) vor ihrer Deklaration konsumiert werden — auch nicht in `watch()`-Gettern, die bei Registrierung sofort laufen.
- Nach Frontend-Fixes in Docker-Umgebungen immer Container-Neustart + Browser-Cache-Clear durchführen, bevor man den Fix als fehlgeschlagen bewertet. Bestätigt im Live-Test 2026-05-03: Reload allein reichte nicht, erst nach `docker compose restart agora` war der Fix wirksam.

---

## 7. Folgearbeit

- **Test-Lücke:** `npm run check` hat den TDZ-Bug nicht gefangen, weil nur das Composable selbst getestet wird, nicht das Setup-Mount der Komponente. Ein Component-Mount-Smoketest (`@vue/test-utils` + `mount()` ohne Daten) hätte den ReferenceError zur Build-Zeit erkannt. Folge-Sub-Slice (Aktion 7) anlegen und in PLAN.md/Issue-Tracker einreihen.
