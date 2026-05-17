# P0-Protokoll — GraphPanel-Modularisierung

**Start dieses Teilblocks:** 2026-04-22  
**Priorität:** P0  
**Zugehöriges Backlog:** `EPIC-04 — Graph UI Modularization` aus `docu/refactoring-backlog-priorisiert.md`

---

## 1. Ausgangslage vor diesem Schritt

Nach Abschluss des Backendsplits von `backend/app/api/simulation.py` war der nächste große Frontend-Hotspot weiterhin:

- `frontend/src/components/GraphPanel.vue`

Probleme vor diesem Schritt:
- Datei war mit **1433 Zeilen** weiterhin deutlich zu groß
- Template, D3-Rendering, Detailpanel-UI, Legende und Hilfslogik lagen in **einer einzigen Datei**
- selbst kleine UI-Anpassungen hätten die D3-Renderlogik unnötig mitberührt
- ESLint meldete in `GraphPanel.vue` zwei konkrete Warnungen:
  - ungenutztes `emit`
  - ungenutzter `oldValue`-Parameter im `watch`

---

## 2. Ziel des jetzigen sicheren Teil-Schritts

Es wurde **bewusst nicht** sofort das gesamte D3-Rendering extrahiert.

Stattdessen wurde der nächste **risikoarme Modularisierungsschritt** gewählt:

1. große **Detailpanel-UI** aus `GraphPanel.vue` herauslösen
2. **Legendendarstellung** in eigene Komponente verschieben
3. kleine **Hilfsfunktionen** für Datumsformatierung und Entity-Type-Legende separieren
4. `GraphPanel.vue` dadurch stärker in Richtung **Kompositionsdatei** schieben
5. dabei bestehendes Verhalten, Props und Events unverändert lassen

---

## 3. Umgesetzter Scope

### 3.1 Neue Dateien

- `frontend/src/components/graph/GraphDetailPanel.vue`
- `frontend/src/components/graph/GraphLegend.vue`
- `frontend/src/components/graph/graphPanelUtils.js`

### 3.2 Geänderte Datei

- `frontend/src/components/GraphPanel.vue`

---

## 4. Inhalt der Extraktion

### 4.1 `GraphDetailPanel.vue`
Diese neue Komponente kapselt die komplette rechte Detailansicht für:

- Node-Details
- Relationship-Details
- Self-Loop-Gruppen
- Expand/Collapse einzelner Self-Loops
- Anzeige von Properties, Summary, Labels, Episodes und Zeitfeldern

**Weiterhin im Parent (`GraphPanel.vue`) geblieben:**
- Auswahl eines Knotens / einer Kante
- Zustand `selectedItem`
- Zustand `expandedSelfLoops`
- Event-Reaktion auf `close` und `toggle-self-loop`

**Grund für diese Schnittgrenze:**
- UI-Darstellung ist nun vom D3-Rendering getrennt
- Auswahl-/Interaktionszustand bleibt weiter zentral im GraphPanel
- Risiko eines Verhaltensbruchs bleibt gering

### 4.2 `GraphLegend.vue`
Die Legende für Entity Types wurde aus dem Panel herausgelöst.

**Nutzen:**
- `GraphPanel.vue` verliert statisches Darstellungs-Markup
- Legendendarstellung kann später leichter erweitert oder wiederverwendet werden
- Style-Isolation ist sauberer

### 4.3 `graphPanelUtils.js`
Neue Hilfsfunktionen:

- `buildEntityTypes(graphData)`
- `formatDateTime(dateStr)`

**Nutzen:**
- keine Inline-Helfer mehr im Monolith für UI-nahe Datenaufbereitung
- `GraphPanel.vue` und `GraphDetailPanel.vue` teilen sich nun dieselbe Datumsformatierung
- nächste Extraktionsschritte können auf derselben Utils-Datei aufbauen

---

## 5. Zusätzliche Cleanup-Effekte

Im Zuge der Extraktion wurden in `GraphPanel.vue` auch zwei kleine Altlasten bereinigt:

1. `defineEmits(...)` wird nicht mehr einer ungenutzten Variable zugewiesen
2. der ungenutzte `oldValue`-Parameter im Simulations-Watcher wurde entfernt

**Direkter Effekt:**
- Frontend-ESLint-Warnungen sanken von **23 auf 21**

---

## 6. Größenänderung / Strukturgewinn

### Vorher
- `frontend/src/components/GraphPanel.vue` → **1433 Zeilen**

### Nachher
- `frontend/src/components/GraphPanel.vue` → **905 Zeilen**
- `frontend/src/components/graph/GraphDetailPanel.vue` → **465 Zeilen**
- `frontend/src/components/graph/GraphLegend.vue` → **71 Zeilen**
- `frontend/src/components/graph/graphPanelUtils.js` → **49 Zeilen**

### Bewertung
Die Gesamtlogik ist natürlich nicht kleiner geworden, aber die Verantwortung wurde erstmals sauberer getrennt:

- `GraphPanel.vue` enthält jetzt weniger statisches UI-Markup
- das Detailpanel ist eigenständig pflegbar
- UI-nahe Hilfslogik ist aus dem Hauptfile herausgelöst

---

## 7. Verifikation

### 7.1 Frontend-Lint
Befehl:
```bash
cd frontend && npm run lint
```

Ergebnis:
- **0 Fehler**
- **21 Warnungen**
- gegenüber vorher: **2 Warnungen weniger**

### 7.2 Frontend-Build
Befehl:
```bash
cd frontend && npm run build
```

Ergebnis:
- **Build erfolgreich**
- Vite-Bundle erfolgreich erzeugt
- bestehender Chunking-Hinweis zu `pendingUpload.js` bleibt unverändert bestehen

### 7.3 Gesamtcheck
Befehl:
```bash
npm run check
```

Ergebnis:
- Backend Ruff (scoped) → **bestanden**
- Backend Tests → **63 bestanden**
- Frontend Lint → **0 Fehler, 21 Warnungen**
- Frontend Build → **bestanden**

---

## 8. Wichtige Designentscheidung dieses Schritts

### Nicht sofort den D3-Renderer extrahieren
Der eigentliche D3-Teil ist weiterhin der riskanteste Bereich von `GraphPanel.vue`.

Er wurde in diesem Schritt **bewusst nicht** angerührt, weil:
- D3-Simulation, Drag-Logik, Midpoint-Berechnungen und Label-Positionierung eng gekoppelt sind
- dort ein direkter Verhaltensbruch wahrscheinlicher wäre
- die jetzt gewählte UI-Extraktion zuerst die Datei verkleinert, ohne die Kern-Renderlogik anzugreifen

Das war absichtlich ein **sicherer Zwischen-Schnitt**.

---

## 9. Nächste sinnvolle Folge-Schritte für GraphPanel

Nach diesem ersten sicheren Modularisierungsschritt sind die nächsten guten Kandidaten:

1. **D3-Datenaufbereitung extrahieren**
   - Node-/Edge-Normalisierung
   - Self-Loop-Gruppierung
   - Multiedge-Krümmungsberechnung

2. **Renderer/Simulation in Composable oder Helper auslagern**
   - Setup / teardown der Force Simulation
   - Resize-Reaktion
   - Link-Label-Refs und Toggle-Handling

3. **GraphControls weiter separieren**
   - Edge-Label-Toggle
   - Toolbar-/Hint-Bereiche

4. **DTO-Normalisierung vorbereiten**
   - Frontend soll mittelfristig nicht direkt auf historisch gewachsene Rohfelder zugreifen

---

## 10. Kurzfazit

Dieser Schritt ist kein kosmetischer Umbau, sondern der **erste echte kontrollierte Frontend-Schnitt** am Graph-Hotspot:

- `GraphPanel.vue` ist deutlich kleiner geworden
- Darstellungslogik wurde von Renderlogik getrennt
- zwei ESLint-Warnungen wurden nebenbei abgebaut
- die Grundlage für den nächsten, technisch riskanteren D3-Split ist gelegt

---

## 11. Zweiter GraphPanel-Schritt — D3-Datenaufbereitung herausgelöst

Nach dem ersten UI-orientierten Schnitt wurde im nächsten Schritt die **D3-nahe Datenvorbereitung** aus `GraphPanel.vue` herausgezogen, ohne schon die eigentliche Force-Simulation anzufassen.

### 11.1 Neue Datei
- `frontend/src/components/graph/graphPanelData.js`

### 11.2 Geänderte Datei
- `frontend/src/components/GraphPanel.vue`

### 11.3 Herausgelöste Logik
Die neue Datei kapselt jetzt:
- Node-Normalisierung für das Rendering
- Aufbau der Entity-Type-Farbzuordnung
- Filterung ungültiger Kanten ohne passende Nodes
- Self-Loop-Gruppierung
- Multiedge-Zählung pro Node-Paar
- Krümmungsberechnung für Mehrfachkanten
- Zusammenbau des finalen Render-Modells `{ nodes, edges, getColor }`

### 11.4 Bewusste Abgrenzung
**Nicht** ausgelagert wurden in diesem Schritt:
- `d3.forceSimulation(...)`
- Zoom-Setup
- Drag-Handling
- Pfad- und Midpoint-Berechnung der bereits simulierten Kanten

**Grund:**
Diese Bereiche hängen enger am tatsächlichen SVG-/D3-Lebenszyklus. Die Datenaufbereitung war der nächste sichere Schnitt, weil sie rein funktional ist und sich ohne Verhaltensänderung extrahieren ließ.

### 11.5 Messbarer Effekt
- `frontend/src/components/GraphPanel.vue` wurde weiter reduziert:
  - vorher nach Schritt 1: **905 Zeilen**
  - nach Schritt 2: **785 Zeilen**
- ESLint-Warnungsstand blieb stabil bei **21 Warnungen**
- das D3-Rendering blieb vollständig funktionsgleich im Parent

### 11.6 Verifikation

#### Frontend-Lint
Befehl:
```bash
cd frontend && npm run lint
```
Ergebnis:
- **0 Fehler**
- **21 Warnungen**

#### Frontend-Build
Befehl:
```bash
cd frontend && npm run build
```
Ergebnis:
- **Build erfolgreich**

#### Gesamtcheck
Befehl:
```bash
npm run check
```
Ergebnis:
- Backend Ruff (scoped) → **bestanden**
- Backend Tests → **63 bestanden**
- Frontend Lint → **0 Fehler, 21 Warnungen**
- Frontend Build → **bestanden**

### 11.7 Bedeutung für die nächsten Schritte
Mit diesem zweiten Schnitt ist `GraphPanel.vue` jetzt nicht mehr nur UI-seitig kleiner, sondern auch bei der **Datenmodellierung** entlastet.

Die nächsten sinnvollen Kandidaten sind nun deutlich klarer:
1. Link-Path- und Midpoint-Geometrie extrahieren
2. Force-Simulation / SVG-Renderer kapseln
3. Controls / Hint-Bereiche weiter separieren

---

## 12. Dritter GraphPanel-Schritt — Link-Geometrie herausgelöst

Im nächsten sicheren Schritt wurde die **reine Link-Geometrie** aus `GraphPanel.vue` extrahiert.

### 12.1 Neue Datei
- `frontend/src/components/graph/graphPanelGeometry.js`

### 12.2 Geänderte Datei
- `frontend/src/components/GraphPanel.vue`

### 12.3 Herausgelöste Logik
Die neue Datei kapselt jetzt:
- SVG-Path-Berechnung für normale Kanten
- SVG-Path-Berechnung für Self-Loops
- Midpoint-Berechnung für gerade Kanten
- Midpoint-Berechnung für gekrümmte Kanten
- gemeinsame Kontrollpunkt-Berechnung für Quadratic-Bezier-Kurven

### 12.4 Warum dieser Schnitt sicher war
Dieser Teil ist **funktional und deterministisch**:
- keine Seiteneffekte
- keine D3-Lifecycle-Steuerung
- keine DOM-Selektion
- keine Watcher / Refs / Simulation-Steuerung

Damit war der Geometrie-Schnitt deutlich risikoärmer als eine direkte Extraktion des kompletten Renderers.

### 12.5 Messbarer Effekt
- `frontend/src/components/GraphPanel.vue` wurde weiter reduziert:
  - nach Schritt 2: **785 Zeilen**
  - nach Schritt 3: **714 Zeilen**
- Lint-Warnungsstand blieb stabil bei **21 Warnungen**

### 12.6 Verifikation

#### Frontend-Lint
Befehl:
```bash
cd frontend && npm run lint
```
Ergebnis:
- **0 Fehler**
- **21 Warnungen**

#### Frontend-Build
Befehl:
```bash
cd frontend && npm run build
```
Ergebnis:
- **Build erfolgreich**

#### Gesamtcheck
Befehl:
```bash
npm run check
```
Ergebnis:
- Backend Ruff (scoped) → **bestanden**
- Backend Tests → **63 bestanden**
- Frontend Lint → **0 Fehler, 21 Warnungen**
- Frontend Build → **bestanden**

### 12.7 Neuer nächster Kandidat
Nach UI, Datenaufbereitung und Geometrie bleibt jetzt als nächster größerer Brocken vor allem:
1. Force-Simulation / SVG-Renderer kapseln
2. Link-/Node-Selection-Highlighting strukturieren
3. Controls / Hint-Bereiche separat ziehen
