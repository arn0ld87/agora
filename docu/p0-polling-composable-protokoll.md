# P0-Protokoll — Polling-Composable einführen

**Datum:** 2026-04-22  
**Kontext:** Follow-up auf die Kritik, dass Polling-Logik aktuell quer über Views/Komponenten verteilt ist

---

## 1. Problemstellung

Vor diesem Schritt lag Polling-Logik in mehreren Komponenten separat:

- `frontend/src/components/Step2EnvSetup.vue`
- `frontend/src/components/Step3Simulation.vue`
- `frontend/src/components/Step4Report.vue`
- darüber hinaus weitere Polling-Stellen in Views

Typische Muster waren jeweils lokal dupliziert:
- `let pollTimer = null`
- `setInterval(...)`
- `clearInterval(...)`
- Start-/Stop-Helfer pro Komponente
- Cleanup via `onUnmounted(...)`

Das funktionierte, führte aber zu:
- Copy/Paste-Polling
- größerer Fehlerfläche bei Cleanup/Unmount
- mehr Aufwand für spätere Refactors
- erhöhter Wahrscheinlichkeit für leicht unterschiedliche Polling-Verhalten zwischen Pipeline-Schritten

---

## 2. Ziel

Ein erster gemeinsamer Polling-Baustein sollte eingeführt werden, der:

1. Start/Stop/Cleanup zentral kapselt
2. Async-Polling sicher ausführt
3. Doppel-Overlaps während laufender Requests verhindert
4. sofort in den wichtigsten Langläufer-Komponenten verwendet wird

Wichtig war dabei, **keine vollständige Frontend-State-Architektur** auf einmal umzubauen.

---

## 3. Umgesetzte Änderungen

### 3.1 Neue Datei
- `frontend/src/composables/usePolling.js`

### 3.2 API des Composables
Das Composable stellt bereit:
- `start()`
- `stop()`
- `tick()`
- `isRunning`
- `isTicking`

### 3.3 Wichtige Eigenschaften
- Cleanup via `onUnmounted(stop)` zentral enthalten
- keine parallelen Overlaps bei langsamem Polling-Request
- optionales `immediate` beim Start
- optionaler `onError`-Hook

---

## 4. Migration auf erste Kernkomponenten

### 4.1 `Step2EnvSetup.vue`
Ersetzt wurden dort lokale Interval-Variablen für:
- Prepare-Status
- Realtime-Profile
- Realtime-Config

### 4.2 `Step3Simulation.vue`
Ersetzt wurden dort lokale Interval-Variablen für:
- Run-Status + Detail-Status
- Console-Log-Polling

### 4.3 `Step4Report.vue`
Ersetzt wurden dort lokale Interval-Variablen für:
- Report-Status
- Agent-Log
- Console-Log

Gerade `Step4Report.vue` ist dafür wichtig, weil Report-Generierung einer der längsten Polling-Pfade im Produkt ist.

---

## 5. Designentscheidung

Es wurde **noch kein globales Frontend-Polling-System** mit zentralem Store oder Task-Orchestrator gebaut.

Stattdessen wurde bewusst der kleinere, sichere Schritt gewählt:
- ein wiederverwendbares Composable
- sofortige Nutzung in den drei wichtigsten Step-Komponenten

Das ist architektonisch noch nicht der Endzustand aus `target-architecture.md`, aber ein klarer Übergang weg von Ad-hoc-Intervals.

---

## 6. Verifikation

### Frontend-Lint
Befehl:
```bash
cd frontend && npm run lint
```

Ergebnis:
- **0 Fehler**
- **21 Warnungen**

### Frontend-Build
Befehl:
```bash
cd frontend && npm run build
```

Ergebnis:
- **Build erfolgreich**

### Gesamtcheck
Befehl:
```bash
npm run check
```

Ergebnis:
- Backend Ruff (scoped) → **bestanden**
- Backend Tests → **67 bestanden**
- Frontend Lint → **0 Fehler, 21 Warnungen**
- Frontend Build → **bestanden**

---

## 7. Bewertung

Dieser Schritt bringt noch keine komplette Frontend-State-Konsolidierung, aber er liefert den wichtigsten P0-Hebel:

- Polling ist nicht mehr nur lokaler Copy/Paste-Code
- Langläufer sind besser aufräumbar
- Unmount-Cleanup ist konsistenter
- künftige Refactors (Report-Engine, Workspace, Async-State) bekommen eine sauberere Basis

Kurz: **kleiner Eingriff, hoher Multiplikator für spätere Arbeit**.
