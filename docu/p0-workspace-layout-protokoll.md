# P0-Protokoll — Workspace-Layout-Grundlage

**Datum:** 2026-04-23

---

## 1. Ziel

Nach dem Abschluss von Polling-Composable, GraphPanel-Split und JSON-Härtung war der nächste sinnvolle Frontend-Schritt die Einführung einer **gemeinsamen Workspace-Shell**.

Dabei wurde bewusst nicht sofort die gesamte App auf einmal umgebaut.

Der erste sichere Schnitt war:
- Layout-Primitives anlegen
- **einen** bestehenden View darauf umstellen
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

## 4. Umgesetzte Schnittgrenzen

### 4.1 `WorkspaceLayout.vue`
Verantwortlich für:
- volle Workspace-Höhe
- vertikale Gesamtstruktur
- Header-Slot + Content-Slot

### 4.2 `WorkspaceHeader.vue`
Verantwortlich für:
- dreiteiligen Header-Rahmen
- Brand-Slot
- Center-Slot
- Status-Slot
- responsive Grundstruktur

### 4.3 `WorkspaceSplit.vue`
Verantwortlich für:
- zweispaltige Arbeitsfläche
- linkes/rechtes Panel
- Übergänge für Breite/Opacity
- Slot-basierte Befüllung

### 4.4 `MainView.vue`
Behält weiterhin:
- echte fachliche State-Logik
- Graph-/Step-Komponenten
- Umschalten zwischen `graph` / `split` / `workbench`
- Projekt-/Graph-/Task-Orchestrierung

---

## 5. Warum dieser Schritt sinnvoll war

Der Umbau ist klein, aber strukturell wichtig:
- Workspace-Shell ist nicht länger nur implizit in einem View verborgen
- neue Views können künftig dieselben Layout-Bausteine wiederverwenden
- spätere Umstellung weiterer Screens (`Process.vue`, `SimulationRunView.vue`, ggf. `ReportView.vue`) wird einfacher
- der Eingriff bleibt risikoarm, weil nur ein einzelner View migriert wurde

---

## 6. Verifikation

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

---

## 7. Nächster sinnvoller Schritt

Nach diesem Grundschnitt ist der nächste Kandidat klar:
- `Process.vue` oder `SimulationRunView.vue` auf dieselbe Workspace-Shell umziehen
- danach weitere Shell-/Header-Duplizierung abbauen
