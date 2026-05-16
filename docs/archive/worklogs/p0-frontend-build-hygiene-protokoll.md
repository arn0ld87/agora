# P0-Protokoll — Frontend Build Hygiene

## Ausgangslage
Nach den Workspace- und Polling-Refactors lief `cd frontend && npm run build` zwar grün, Vite meldete aber weiterhin einen Build-Hinweis:

```text
frontend/src/store/pendingUpload.js is dynamically imported by frontend/src/views/Home.vue
but also statically imported by frontend/src/views/MainView.vue,
dynamic import will not move module into another chunk.
```

Das war kein funktionaler Fehler, aber ein unnötiger Build-Hygiene-Befund. Gleichzeitig war `pendingUpload.js` ein sehr kleines In-Memory-Modul, bei dem zusätzlicher Lazy-Load keinen realen Nutzen brachte.

## Ziel
- den letzten verbleibenden Vite-Build-Hinweis im aktuellen Frontend-Stand entfernen
- Import-Strategie für `pendingUpload.js` vereinheitlichen
- Verhalten von Home → Process unverändert lassen

## Umsetzung

### 1. Home-Import vereinheitlicht
**Datei:** `frontend/src/views/Home.vue`

Änderung:
- `setPendingUpload` wird nicht mehr per `await import('../store/pendingUpload.js')` nachgeladen
- stattdessen normaler statischer Import am Dateikopf

Warum das sauberer ist:
- `MainView.vue` nutzt dasselbe Modul bereits statisch
- dadurch entfällt die gemischte statisch/dynamisch-Import-Situation
- Vite muss kein Schein-Splitting mehr bewerten

### 2. Laufzeitverhalten bewusst unverändert gelassen
Die eigentliche Navigation blieb identisch:
- Home sammelt Dateien + Prompt
- `setPendingUpload(...)` füllt den temporären In-Memory-Store
- danach `router.push({ name: 'Process', params: { projectId: 'new' } })`

Es wurde bewusst **kein** größerer Store-Umbau vorgenommen, weil der aktuelle Ablauf stabil ist und die Warning bereits durch die vereinheitlichte Import-Strategie verschwindet.

## Verifikation
- `cd frontend && npm run lint` → **0 Fehler, 0 Warnungen**
- `cd frontend && npm run build` → **bestanden**
- `npm run check` → **bestanden**

Ergebnis:
- Frontend-Lint grün
- Frontend-Build grün
- kein verbliebener `pendingUpload`-Chunking-Hinweis mehr
- Gesamt-Quality-Gate weiterhin grün

## Ergebnis
Der aktuelle Frontend-Build ist damit sauberer als zuvor: gleiche Funktionalität, weniger Tooling-Rauschen, keine unnötige gemischte Importstrategie im Startpfad.
