# Agora weiterentwickeln — konkreter Entwicklungsplan

## Kurzbefund

Agora ist bereits mehr als ein Mockup: Das Repo beschreibt eine lokale Multi-Agenten-Simulation mit GraphRAG, Neo4j, Ollama/OASIS, Persona-Erzeugung, Simulation, ReportAgent und Interaction-Phase. Das hochgeladene ZIP und der Canva-Link liefern dazu ein Design-System mit dunklem Editorial-/Workbench-Stil, Tokens, Komponenten, Workspace-Screens und Pipeline-Mockups.

Empfehlung: Nicht sofort neue KI-Spielereien ankleben. Erst die vorhandene Pipeline produktreif machen: klare Runs, reproduzierbare Ergebnisse, Persona-Review, Report-Qualität, Export und eine UI, die wie ein ernsthaftes Analysewerkzeug wirkt.

---

## Zielbild v0.7

**Agora v0.7 sollte werden:**

> Ein lokal-first Analyse-Workbench, der aus Dokumenten nachvollziehbare Szenario-Simulationen erzeugt, Personas prüfbar macht, Runs reproduzierbar speichert und Reports mit Evidenz, Metriken und Export liefert.

### Produktversprechen

- Dokument rein
- Graph bauen
- Personas prüfen
- Simulation laufen lassen
- Dynamik analysieren
- Report mit Evidenz exportieren

---

## Wichtigste Weiterentwicklung

## 1. Design-System aus ZIP/Canva ins Frontend übernehmen

### Ziel

Das Design darf nicht als hübsches Nebenprojekt herumliegen. Es muss als produktives UI-System ins Vue-Frontend.

### Umsetzung

```text
frontend/src/styles/
├── agora-tokens.css
├── agora-components.css
├── agora-layout.css
└── agora-utilities.css
```

### Tasks

- `agora-tokens.css` aus dem ZIP bereinigen und als Source-of-Truth übernehmen
- bestehende CSS-Farben im Vue-Frontend gegen Tokens ersetzen
- Button-, Badge-, Panel-, Input- und Toast-Stile zentralisieren
- Workspace-Shell optisch an Canvas angleichen
- Dark-First beibehalten

### Akzeptanzkriterien

- keine hart codierten Hauptfarben mehr in Views
- alle Pipeline-Views nutzen denselben visuellen Stil
- Statusfarben nur für Status, nicht als Deko-Konfetti
- Orange bleibt primäre Action-Farbe
- Plasma/Cyan bleibt Auswahl-, Info- und Graph-Akzent

---

## 2. Persona Review & Approval als nächstes großes Feature

### Warum

Die Simulation steht und fällt mit den Personas. Wenn Personas schlecht, redundant oder halluziniert sind, ist der Report danach nur schön formatierter Unsinn. Also genau das, was das Internet sowieso täglich produziert.

### Funktion

Nach Environment Setup kommt ein Review-Schritt:

- Persona-Liste anzeigen
- Persona-Qualität bewerten
- Persona bearbeiten
- Persona löschen
- Persona regenerieren
- Persona speichern
- Persona erst nach Freigabe in Simulation übernehmen

### UI-Komponenten

```text
frontend/src/features/personas/
├── PersonaReviewView.vue
├── PersonaCard.vue
├── PersonaTable.vue
├── PersonaEditorDrawer.vue
├── PersonaQualityBadge.vue
└── usePersonaReview.js
```

### Backend-Idee

```text
backend/app/services/personas/
├── persona_review_service.py
├── persona_quality_service.py
└── persona_repository.py
```

### Qualitätsmetriken

| Metrik | Zweck |
|---|---|
| Rollen-Diversität | verhindert 20 gleiche Durchschnittsbürger |
| Haltungskontrast | macht Konflikte sichtbar |
| Entity-Bezug | prüft Bezug zum Dokumentgraphen |
| Aktivitätsprofil | verhindert unrealistische Agentenverteilung |
| Risiko-Flag | markiert extreme/unklare Personas |

---

## 3. Run Dashboard bauen

### Ziel

Agora braucht eine zentrale Run-Übersicht. Sonst klickt man sich durch alte Simulationen wie durch einen Keller voller unbeschrifteter Netzteile.

### Features

- alle Runs anzeigen
- Status: created, preparing, ready, running, paused, completed, failed
- Dauer, Modell, Persona-Anzahl, Dokument, Graph-ID
- Aktionen: öffnen, fortsetzen, duplizieren, löschen, exportieren
- Fehlerdetails anzeigen
- letzter Report verlinken

### Frontend-Struktur

```text
frontend/src/features/runs/
├── RunDashboardView.vue
├── RunTable.vue
├── RunStatusBadge.vue
├── RunActionsMenu.vue
├── RunDetailDrawer.vue
└── useRuns.js
```

### Backend-Endpunkte

```http
GET    /api/runs
GET    /api/runs/<run_id>
POST   /api/runs/<run_id>/resume
POST   /api/runs/<run_id>/duplicate
DELETE /api/runs/<run_id>
GET    /api/runs/<run_id>/artifacts
```

---

## 4. Evidence & Confidence Layer

### Ziel

Jede Report-Aussage sollte nachvollziehbar sein.

### Neue Report-Struktur

```json
{
  "claim": "Akteursgruppe X polarisiert die Diskussion stark.",
  "confidence": 0.78,
  "evidence": [
    {
      "type": "graph_metric",
      "source": "simulation_metrics",
      "value": "echo_chamber_index=0.64"
    },
    {
      "type": "agent_quote",
      "agent_id": "persona_12",
      "round": 4
    }
  ]
}
```

### UI

- Reportabschnitt bekommt Confidence-Badge
- Klick auf Aussage öffnet Evidence-Drawer
- Evidence zeigt Graph-Metriken, Agentenposts, Zitate und Rundennummern
- Unsichere Aussagen werden sichtbar markiert

---

## 5. Branch Compare produktiv machen

### Ziel

Szenarien vergleichbar machen:

- Baseline vs. Gegenstrategie
- Modell A vs. Modell B
- Persona-Set A vs. Persona-Set B
- mit Web-Kontext vs. ohne Web-Kontext

### Vergleichsmetriken

| Bereich | Metrik |
|---|---|
| Netzwerk | Communities, Bridge Agents, Zentralität |
| Stimmung | Polarisierung, Zustimmung, Ablehnung |
| Dynamik | Aktivität pro Runde, Eskalationspunkte |
| Report | Unterschiedliche Top-Claims |
| Personas | welche Gruppen kippen oder dominieren |

### UI

```text
BranchCompareView
├── BranchSelector
├── MetricDiffCards
├── GraphDiffPanel
├── PersonaShiftTable
└── ReportDeltaPanel
```

---

## 6. Export Center

### Ziel

Agora muss Ergebnisse sauber rausgeben können.

### Exportformate

| Format | Zweck |
|---|---|
| Markdown | Blog, Dokumentation, GitHub |
| PDF | Weitergabe an Nicht-Techniker |
| JSON | maschinenlesbares Archiv |
| CSV | Metriken weiterverarbeiten |
| GraphML | Graphanalyse in anderen Tools |
| PNG/SVG | Graph-Snapshots |

### Backend

```text
backend/app/services/export/
├── export_service.py
├── markdown_exporter.py
├── json_exporter.py
├── csv_exporter.py
└── graph_exporter.py
```

---

## 7. Technische Härtung

### API Contracts

Einheitliche Responses:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "code": "OK"
}
```

Fehler:

```json
{
  "success": false,
  "data": null,
  "error": {
    "message": "Simulation not found",
    "details": {}
  },
  "code": "SIMULATION_NOT_FOUND"
}
```

### Tests

- Backend: pytest für Services, Repositories, API-Smoke-Tests
- Frontend: Vitest für Composables
- Contract-Tests: API Response Shapes
- E2E später mit Playwright

### Security

- `AGORA_AUTH_TOKEN` nicht optional für nicht-lokale Bindings
- CORS restriktiv lassen
- Secrets nie in Simulation-Artefakte schreiben
- Uploads limitieren
- Dateitypen whitelisten
- Graph-Queries kapseln

---

## Empfohlene Reihenfolge

## Sprint 1 — Design-System produktiv übernehmen

1. Tokens ins Frontend übernehmen
2. zentrale Button/Badge/Input/Panel-Stile bauen
3. Workspace-Shell optisch angleichen
4. alte harte Farben entfernen
5. Build/Lint laufen lassen

## Sprint 2 — Persona Review

1. Persona-Review-API ergänzen
2. Persona-Tabelle/Card bauen
3. Editor-Drawer bauen
4. Approve/Reject/Regenerate Flow
5. Simulation erst nach Freigabe starten

## Sprint 3 — Run Dashboard

1. Runs API ergänzen
2. RunDashboardView bauen
3. RunActions integrieren
4. Fehlerdetails sichtbar machen
5. Resume/Duplicate vorbereiten

## Sprint 4 — Evidence Reports

1. Report-Claim-Modell definieren
2. Evidence-Speicherung ergänzen
3. Confidence-Berechnung initial einführen
4. Report UI erweitern
5. Markdown/JSON Export bauen

## Sprint 5 — Compare & Export

1. Branch Compare API
2. Compare UI
3. Export Center
4. Graph-Snapshot-Export
5. Doku aktualisieren

---

## Claude/Codex Prompt — direkte Umsetzung

```text
Du arbeitest im Repo arn0ld87/agora.

Ziel:
Entwickle Agora weiter von v0.6.1 Alpha zu einer produktreiferen v0.7 Workbench.

Kontext:
- Backend: Flask, Python 3.11, uv, Neo4j, Ollama/OpenAI-kompatibel, OASIS/CAMEL
- Frontend: Vue 3, Vite, D3, vue-i18n, vue-router
- Root-Qualitätsbefehl: npm run check
- Design-Richtung: dark-first, editorial/technical, cream foreground, near-black background, orange primary accent, cyan/plasma secondary graph/info accent

Arbeitsweise:
1. Lies README.md, AGENTS.md, CLAUDE.md und docs/refactoring-backlog-priorisiert.md.
2. Führe keine großen Feature-Sprünge ohne Tests aus.
3. Mache kleine PR-Slices.
4. Aktualisiere Doku, wenn Verhalten oder Struktur geändert wird.
5. Nach jeder Änderung muss npm run check grün sein.

PR 1 — Design-System Integration:
- Überführe die Agora Design Tokens in frontend/src/styles/agora-tokens.css.
- Erstelle zentrale CSS-Dateien für Komponenten und Layout.
- Ersetze harte Hauptfarben in bestehenden Views durch CSS-Variablen.
- Keine visuelle Komplettneugestaltung, sondern Grundlage schaffen.

PR 2 — Persona Review Foundation:
- Ergänze Backend-Service und API für Persona Review.
- Baue Frontend-Struktur unter frontend/src/features/personas/.
- Implementiere Anzeigen, Bearbeiten, Löschen und Freigeben von Personas.
- Simulation darf nur mit approved Personas gestartet werden, sofern Review aktiv ist.

PR 3 — Run Dashboard:
- Ergänze /api/runs und /api/runs/<id>.
- Baue RunDashboardView mit Status, Modell, Datum, Persona-Anzahl und Aktionen.
- Bestehende Simulationen müssen weiterhin funktionieren.

PR 4 — Evidence Report MVP:
- Definiere ein einfaches Evidence-Modell für Report-Claims.
- Ergänze Confidence-Badges im Report UI.
- Exportiere Report als Markdown und JSON.

Qualitätsregeln:
- Kein Secret in Artefakten.
- Keine neue Datei unnötig monolithisch werden lassen.
- API Responses konsistent halten.
- Bestehende Tests nicht schwächen.
- Neue Logik testen.
```

---

## GitHub Issues zum Anlegen

### Issue 1

```md
# Design-System aus Agora Canvas ins Vue-Frontend übernehmen

## Ziel
Die vorhandenen Agora Design Tokens und Komponentenstile sollen als produktive CSS-Grundlage ins Frontend übernommen werden.

## Tasks
- [ ] `frontend/src/styles/agora-tokens.css` anlegen
- [ ] Button/Badge/Input/Panel-Basisstile zentralisieren
- [ ] Workspace-Shell optisch angleichen
- [ ] harte Hauptfarben aus Views entfernen
- [ ] `npm run check` ausführen

## Akzeptanzkriterien
- Alle Pipeline-Views nutzen dieselben Tokens
- Orange ist primäre Action-Farbe
- Plasma/Cyan ist Info-/Graph-Akzent
- Keine Regression im Build
```

### Issue 2

```md
# Persona Review & Approval Flow

## Ziel
Generierte Personas sollen vor der Simulation prüfbar, editierbar und freigebbar sein.

## Tasks
- [ ] Persona Review Service im Backend ergänzen
- [ ] API für approve/reject/regenerate/edit ergänzen
- [ ] Persona Review UI bauen
- [ ] Persona Quality Badges ergänzen
- [ ] Start der Simulation an Approval koppeln

## Akzeptanzkriterien
- Personas können vor dem Run geprüft werden
- einzelne Personas können bearbeitet oder gelöscht werden
- Simulation startet nur mit freigegebenem Set
```

### Issue 3

```md
# Run Dashboard für Simulationen

## Ziel
Nutzer sollen alle Simulation Runs zentral sehen, öffnen und verwalten können.

## Tasks
- [ ] `/api/runs` ergänzen
- [ ] `/api/runs/<id>` ergänzen
- [ ] RunDashboardView bauen
- [ ] Status-Badges und Aktionen ergänzen
- [ ] Fehlerdetails sichtbar machen

## Akzeptanzkriterien
- alle Runs erscheinen tabellarisch
- Status und Kerndaten sind sichtbar
- abgeschlossene/fehlgeschlagene Runs sind nachvollziehbar
```

### Issue 4

```md
# Evidence & Confidence Layer für Reports

## Ziel
Report-Aussagen sollen mit Evidenz und Confidence Score nachvollziehbar werden.

## Tasks
- [ ] Claim/Evidence-Datenmodell definieren
- [ ] Evidence aus Graph-Metriken und Agentenaktionen sammeln
- [ ] Confidence-Badge im Report UI anzeigen
- [ ] Evidence Drawer bauen
- [ ] Markdown/JSON Export erweitern

## Akzeptanzkriterien
- Report-Claims haben optional Evidence
- Confidence ist sichtbar
- Nutzer kann nachvollziehen, worauf Aussagen beruhen
```
