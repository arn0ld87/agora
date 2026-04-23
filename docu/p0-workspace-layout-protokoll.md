# P0-Protokoll — Workspace-Layout-Grundlage

**Datum:** 2026-04-23

---

## 1. Ziel

Nach dem Abschluss von Polling-Composable, GraphPanel-Split und JSON-Härtung war der nächste sinnvolle Frontend-Schritt die Einführung einer **gemeinsamen Workspace-Shell**.

Dabei wurde bewusst nicht sofort die gesamte App auf einmal umgebaut.

Der erste sichere Schnitt war:
- Layout-Primitives anlegen
- bestehende Workspace-nahe Views schrittweise darauf umstellen
- Verhalten und Routing unverändert lassen

---

## 2. Neue Dateien

- `frontend/src/layouts/WorkspaceLayout.vue`
- `frontend/src/layouts/WorkspaceHeader.vue`
- `frontend/src/layouts/WorkspaceSplit.vue`

---

## 3. Erster migrierter View

### `frontend/src/views/MainView.vue`

`MainView.vue` war ein guter erster Kandidat, weil dort bereits eine relativ klare Shell-Struktur existierte:
- Header / Top-Navigation
- zentrale View-Umschaltung
- Statusbereich
- linker/rechter Arbeitsbereich

Diese Shell-Verantwortung wurde jetzt auf die neuen Layout-Komponenten verteilt.

---

## 4. Zweiter migrierter View

### `frontend/src/views/SimulationRunView.vue`

Nach `MainView.vue` wurde als nächster Schritt `SimulationRunView.vue` auf dieselbe Shell umgestellt.

Auch dort war die Struktur klar genug für einen risikoarmen Umbau:
- Brand / Header
- View-Switcher
- Laufstatus + Quick-Pause
- Graph links / Workbench rechts

Damit teilen jetzt bereits zwei zentrale Arbeitsviews denselben Workspace-Rahmen.

---

## 5. Umgesetzte Schnittgrenzen

### 5.1 `WorkspaceLayout.vue`
Verantwortlich für:
- volle Workspace-Höhe
- vertikale Gesamtstruktur
- Header-Slot + Content-Slot

### 5.2 `WorkspaceHeader.vue`
Verantwortlich für:
- dreiteiligen Header-Rahmen
- Brand-Slot
- Center-Slot
- Status-Slot
- responsive Grundstruktur

### 5.3 `WorkspaceSplit.vue`
Verantwortlich für:
- zweispaltige Arbeitsfläche
- linkes/rechtes Panel
- Übergänge für Breite/Opacity
- Slot-basierte Befüllung

### 5.4 Migrierte Views behalten weiterhin
- echte fachliche State-Logik
- Graph-/Step-Komponenten
- View-Umschaltung
- Projekt-/Graph-/Task-Orchestrierung
- Simulationsstatus / Pause-Handling

---

## 6. Warum dieser Schritt sinnvoll war

Der Umbau ist klein, aber strukturell wichtig:
- Workspace-Shell ist nicht länger nur implizit in einem einzelnen View verborgen
- neue Views können dieselben Layout-Bausteine wiederverwenden
- spätere Umstellung weiterer Screens (`Process.vue`, ggf. `SimulationView.vue`, `ReportView.vue`) wird einfacher
- der Eingriff bleibt risikoarm, weil die eigentliche Fachlogik in den migrierten Views unangetastet blieb

---

## 7. Verifikation

### Frontend-Lint
Befehl:
```bash
cd frontend && npm run lint
```

Ergebnis:
- **0 Fehler, 0 Warnungen**

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
- Backend Tests → **70 bestanden**
- Frontend Lint → **0 Fehler, 0 Warnungen**
- Frontend Build → **bestanden**

---

## 8. Dritter Workspace-Schritt — Mode-Switcher extrahiert

Nach der Migration von `MainView.vue` und `SimulationRunView.vue` blieb eine offensichtliche Duplizierung im Header bestehen: derselbe View-Mode-Switcher (`graph` / `split` / `workbench`) wurde in beiden Views separat gepflegt.

### 8.1 Neue Datei
- `frontend/src/layouts/WorkspaceModeSwitch.vue`

### 8.2 Geänderte Dateien
- `frontend/src/views/MainView.vue`
- `frontend/src/views/SimulationRunView.vue`

### 8.3 Nutzen
- gemeinsames UI-Verhalten für Workspace-Modi
- weniger Header-Duplikat in den migrierten Views
- künftige Workspace-Screens können denselben Umschalter direkt wiederverwenden

### 8.4 Verifikation
- `cd frontend && npm run lint` → **0 Fehler, 0 Warnungen**
- `cd frontend && npm run build` → **bestanden**

## 9. Nächster sinnvoller Schritt

Nach diesem Shell-Cleanup sind die nächsten Kandidaten:
- `SimulationView.vue` oder `ReportView.vue` auf dieselbe Workspace-Shell umziehen
- gemeinsame Status-/Header-Bausteine weiter normalisieren
- anschließend weitere Shell-/Header-Duplizierung abbauen
