# Agora / MiroFish-Offline — Feature Roadmap

**Stand:** 2026-04-22  
**Basisdokumente:**
- `docu/2026-04-22-refactoring-produkt-audit.md`
- `docu/refactoring-backlog-priorisiert.md`

---

## 1. Ziel der Roadmap

Diese Roadmap priorisiert die wichtigsten **produktseitigen Erweiterungen** von Agora und verbindet sie mit den im Audit identifizierten **technischen Voraussetzungen**. Sie beantwortet nicht nur die Frage *„Was bauen wir als Nächstes?“*, sondern auch *„Wann ist ein Feature sinnvoll?“* und *„Woran messen wir den Erfolg?“*.

Leitgedanke:

> **Erst die größten Struktur- und Qualitätsrisiken entschärfen, dann die stärksten Analyse- und Operations-Features ausrollen.**

Damit wird verhindert, dass neue Funktionen auf einer zu fragilen technischen Basis entstehen.

---

## 2. Vision

Agora soll sich von einem lokal nutzbaren Simulations- und Report-Prototypen zu einem **verlässlichen Analyse-Workbench-System** entwickeln, mit dem Teams:

1. Dokumente in belastbare Wissensgraphen überführen,
2. darauf basierend realistische Simulationsszenarien erzeugen,
3. Varianten und Branches vergleichbar auswerten,
4. Reports mit nachvollziehbarer Evidenz erstellen,
5. und den gesamten Ablauf operativ transparent steuern können.

### Zielbild in einem Satz

**Ein lokales, nachvollziehbares und steuerbares End-to-End-System für Graph-basierte Multi-Agenten-Simulation, Vergleich und Auswertung.**

---

## 3. Strategische Leitplanken

Damit die Roadmap nicht in unkoordiniertem Feature-Wachstum endet, gelten folgende Prinzipien:

1. **Architektur vor Beschleunigung**  
   Größere neue Features werden erst dann skaliert, wenn P0/P1-Refactorings die wichtigsten Hotspots entschärft haben.

2. **Operations und Vergleich zuerst**  
   Die größten kurzfristigen Produkthebel sind Transparenz über Läufe und die Vergleichbarkeit von Szenarien.

3. **Vertrauen durch Nachvollziehbarkeit**  
   Features rund um Evidence, Confidence und Diagnostik erhöhen die Nutzbarkeit stärker als reine UI-Kosmetik.

4. **Wiederverwendbare Datenmodelle statt Sonderfälle**  
   Neue Features sollen auf standardisierten Run-, Simulation-, Report- und Graph-DTOs aufsetzen.

5. **Messbarkeit vor Ausbau**  
   Jedes größere Feature bekommt klare KPIs und Go/No-Go-Kriterien.

---

## 4. Roadmap-Logik und Reihenfolge

Die Reihenfolge folgt bewusst nicht nur Business-Wunschlisten, sondern den technischen Abhängigkeiten aus Audit und Backlog.

### Reihenfolge auf hoher Ebene

1. **Enablement / Stabilisierung**
   - Quality Foundation
   - API-Splitting
   - Workspace-/Graph-/Polling-Konsolidierung
   - erste Test- und Contract-Basis

2. **Operative Transparenz und Vergleichbarkeit**
   - Run Dashboard
   - Scenario Branch Compare
   - Persona Review & Approval
   - Health & Setup Diagnostics

3. **Analytische Vertiefung**
   - Interview Presets / Research Templates
   - Export Center
   - Replay / Reproduce Run

4. **Vertrauen und Echtzeitfähigkeit**
   - Graph Diff vor/nach Simulation
   - Report Confidence / Evidence Score
   - SSE/WebSocket Live Updates

---

## 5. Zeithorizonte

## Horizont 0 — Voraussetzungen schaffen (0–6 Wochen)

Dieser Horizont ist kein reiner Feature-Block, sondern die **Freigabephase für belastbare Produktentwicklung**.

### Fokus
- CI, Linting, erste Tests
- `simulation.py` aufspalten
- Workspace-Layout konsolidieren
- `GraphPanel.vue` modularisieren
- Polling zentralisieren
- Kernzustände und Response-Modelle stabilisieren

### Erwarteter Nutzen
- geringeres Regressionsrisiko
- schnellere spätere Feature-Umsetzung
- weniger technische Unsicherheit bei Dashboard-/Compare-/Review-Features

### Freigaberelevanz
Ohne Horizont 0 sollten nur kleine, risikoarme Produktverbesserungen umgesetzt werden.

---

## Horizont 1 — Kern-Mehrwert ausbauen (6–12 Wochen)

In diesem Horizont werden die **stärksten produktseitigen Mehrwerte** umgesetzt.

### Geplante Features
1. Run Dashboard / Operations Center
2. Scenario Branch Compare
3. Persona Review & Approval Flow
4. Health & Setup Diagnostics im UI

### Ziel
Agora soll in dieser Phase von einer funktionalen Pipeline zu einem **steuerbaren und vergleichbaren Analysewerkzeug** werden.

---

## Horizont 2 — Analyse-Workbench professionalisieren (3–6 Monate)

Nach den Kernfeatures folgt der Ausbau in Richtung **Analytik, Reproduzierbarkeit und Team-Nutzbarkeit**.

### Geplante Features
1. Interview Presets / Research Templates
2. Export Center
3. Job Replay / Reproduce Run
4. Prompt Presets je Pipeline-Stufe

### Ziel
Mehr Wiederverwendbarkeit, bessere Ergebnisweitergabe und weniger manuelle Analystenarbeit.

---

## Horizont 3 — Vertrauens- und Echtzeit-Layer (6+ Monate)

Dieser Horizont ergänzt das System um Funktionen, die vor allem Produktreife, Tiefe und Live-Nutzbarkeit steigern.

### Geplante Features
1. Graph Diff vor/nach Simulation
2. Report Confidence / Evidence Score
3. SSE/WebSocket Live Updates

### Ziel
Agora soll hier zu einer noch besser nachvollziehbaren, live beobachtbaren und analytisch tieferen Plattform werden.

---

## 6. Priorisierte Feature-Liste

## Priorität A — zuerst nach der Stabilisierung

### 1. Run Dashboard / Operations Center
**Kurzbeschreibung**  
Zentrale Übersicht über Graph-Builds, Prepare-Jobs, Simulationsläufe und Report-Erstellung inklusive Status, Dauer, Fehlerbild und Artefaktzugriff.

**Nutzen**
- hohe operative Transparenz
- weniger Suchaufwand bei Fehlern und langen Läufen
- bessere UX für Mehrschrittprozesse
- ideale Grundlage für Restart/Resume-Workflows

**Aufwand:** Mittel bis hoch  
**Abhängigkeiten:** Zentralisierte Async-/Polling-Logik, stabilere Runs-API, konsistente Statusmodelle  
**Empfohlener Zeitpunkt:** direkt nach P0

---

### 2. Scenario Branch Compare
**Kurzbeschreibung**  
Vergleich zweier oder mehrerer Branches bzw. Simulationsvarianten nach Konfiguration, Aktivität, Themen, Reports und Ergebniskennzahlen.

**Nutzen**
- macht vorhandenes Branching erst wirklich produktiv nutzbar
- erhöht den Analysewert deutlich
- unterstützt Was-wäre-wenn-Fragen und Experimentdesign

**Aufwand:** Hoch  
**Abhängigkeiten:** saubere Simulationsdomäne, stabile Compare-Metriken, standardisierte DTOs  
**Empfohlener Zeitpunkt:** direkt nach Run Dashboard

---

### 3. Persona Review & Approval Flow
**Kurzbeschreibung**  
UI-gestützter Freigabeprozess für generierte Personas vor Start einer Simulation, inklusive Review, Ablehnung, Regeneration und Kontextvergleich.

**Nutzen**
- verbessert die Eingangsqualität der Simulation
- reduziert Halluzinationen und generische Profile
- erhöht Nutzerkontrolle an einer kritischen Stelle der Pipeline

**Aufwand:** Mittel  
**Abhängigkeiten:** modularere Prepare-/Persona-Domäne, bessere UI-Zerlegung  
**Empfohlener Zeitpunkt:** parallel oder direkt nach Branch Compare

---

### 4. Health & Setup Diagnostics im UI
**Kurzbeschreibung**  
Systemdiagnosen für Neo4j, LLM-Erreichbarkeit, Modellkonfiguration, Auth, Disk/Volume-Pfade und Kernvoraussetzungen.

**Nutzen**
- senkt Support- und Debugging-Aufwand
- reduziert Fehlstarts
- besonders wertvoll im lokalen/offline-nahen Setup

**Aufwand:** Mittel  
**Abhängigkeiten:** klare Health-Endpunkte, standardisierte Fehlerobjekte  
**Empfohlener Zeitpunkt:** früh in Horizont 1

---

## Priorität B — danach

### 5. Interview Presets / Research Templates
**Kurzbeschreibung**  
Vordefinierte Interview- und Analysevorlagen für Zustimmung, Emotionen, Risiko, Gegenargumente, Segment- und Plattformvergleiche.

**Nutzen**
- macht Step 5 von einem Demo-Feature zu einem wiederholbaren Analysewerkzeug
- spart Zeit bei häufigen Untersuchungsfragen
- fördert methodische Konsistenz

**Aufwand:** Mittel  
**Abhängigkeiten:** stabilere Interview-APIs und UI-Komponenten  
**Empfohlener Zeitpunkt:** Horizont 2

---

### 6. Export Center
**Kurzbeschreibung**  
Zentraler Export von Reports, Personas, Timelines, Aktionen und Graph-Artefakten in Formaten wie Markdown, HTML, PDF, CSV, JSON oder GraphML.

**Nutzen**
- verbessert Weitergabe und Anschlussfähigkeit an andere Tools
- steigert praktischen Nutzen für Analyse- und Reporting-Workflows
- verringert manuelle Datenaufbereitung

**Aufwand:** Mittel bis hoch  
**Abhängigkeiten:** saubere Artefaktstrukturen, konsistente DTOs  
**Empfohlener Zeitpunkt:** Horizont 2

---

### 7. Job Replay / Reproduce Run
**Kurzbeschreibung**  
Erneutes Ausführen eines vorhandenen Laufs mit gleicher oder leicht modifizierter Konfiguration, z. B. mit anderem Modell oder geänderten Prompts.

**Nutzen**
- erhöht Reproduzierbarkeit
- nützlich für Experimente, Benchmarking und Fehleranalyse
- stärkt den Analysecharakter des Produkts

**Aufwand:** Mittel bis hoch  
**Abhängigkeiten:** stabiles Run-Manifest, Dashboard, saubere Persistenz  
**Empfohlener Zeitpunkt:** nach Run Dashboard und Export Center

---

### 8. Prompt Presets je Pipeline-Stufe
**Kurzbeschreibung**  
Verwaltbare Prompt-Profile für Ontology, Persona, SimulationConfig, Report und Interview.

**Nutzen**
- schnellere Wiederverwendung bewährter Setups
- besserer Fit für unterschiedliche Anwendungsfälle
- Grundlage für methodische Variantenvergleiche

**Aufwand:** Mittel  
**Abhängigkeiten:** standardisierte Konfigurationsmodelle, Reproduce-Mechanismen  
**Empfohlener Zeitpunkt:** später in Horizont 2

---

## Priorität C — strategisch nach Reifegrad

### 9. Graph Diff vor/nach Simulation
**Kurzbeschreibung**  
Sichtbar machen, welche Knoten, Kanten oder Cluster sich durch die Simulation verändert haben.

**Nutzen**
- hoher analytischer Mehrwert
- schafft Sichtbarkeit über tatsächliche Wissensveränderung
- unterstützt die Bewertung von Simulationseffekten

**Aufwand:** Hoch  
**Abhängigkeiten:** stabile Graph-DTOs, Compare-Modelle, gute Persistenzbasis  
**Empfohlener Zeitpunkt:** Horizont 3

---

### 10. Report Confidence / Evidence Score
**Kurzbeschreibung**  
Bewertung von Report-Abschnitten nach Evidenzdichte, Claim-Abdeckung und Tool-gestützter Beleglage.

**Nutzen**
- steigert Vertrauen in Reports
- macht Unsicherheit expliziter
- verbessert die Qualitätssicherung der Auswertung

**Aufwand:** Mittel bis hoch  
**Abhängigkeiten:** modularisierte Report-Engine, expliziter Evidence-Layer  
**Empfohlener Zeitpunkt:** zusammen mit oder nach Graph Diff

---

### 11. SSE/WebSocket Live Updates
**Kurzbeschreibung**  
Schrittweiser Ersatz von Polling durch serverseitige Events oder WebSockets für Logs, Status und Fortschritt.

**Nutzen**
- bessere Live-UX
- weniger unnötige Requests
- robuster bei langen Läufen

**Aufwand:** Hoch  
**Abhängigkeiten:** zunächst zentrales Polling und konsistente Async-Modelle, dann Event-Strategie  
**Empfohlener Zeitpunkt:** erst nach Stabilisierung der bestehenden Status- und Run-Modelle

---

## 7. Nutzen-/Aufwand-Matrix

| Feature | Nutzen | Aufwand | Priorität | Begründung |
|---|---:|---:|---:|---|
| Run Dashboard / Operations Center | Sehr hoch | M–L | A | sofort sichtbarer Mehrwert, starke operative Entlastung |
| Scenario Branch Compare | Sehr hoch | L | A | macht bestehendes Branching strategisch wertvoll |
| Persona Review & Approval Flow | Hoch | M | A | verbessert Input-Qualität und Kontrolle vor Simulation |
| Health & Setup Diagnostics | Hoch | M | A | reduziert Fehlstarts und Supportaufwand |
| Interview Presets / Research Templates | Mittel–hoch | M | B | erhöht Wiederverwendbarkeit und Analysequalität |
| Export Center | Hoch | M–L | B | steigert praktischen Nutzen außerhalb der App |
| Job Replay / Reproduce Run | Hoch | M–L | B | wichtig für Experimente und Reproduzierbarkeit |
| Prompt Presets je Pipeline-Stufe | Mittel | M | B | nützlich, aber erst nach stabilen Konfigurationsmodellen |
| Graph Diff vor/nach Simulation | Hoch | L | C | analytisch stark, aber technisch anspruchsvoll |
| Report Confidence / Evidence Score | Hoch | M–L | C | vertrauensbildend, braucht modularen Evidence-Layer |
| SSE/WebSocket Live Updates | Mittel | L | C | UX-Verbesserung, aber nicht vor Kernwert-Features |

---

## 8. Risiken und Gegenmaßnahmen

## Risiko 1 — Neue Features vergrößern bestehende Hotspots
**Beschreibung:** Ohne vorherige Entflechtung würden Dashboard, Compare oder Review direkt auf monolithische APIs und UI-Komponenten aufgesetzt.  
**Gegenmaßnahme:** Feature-Start an Abschluss von P0 koppeln.

## Risiko 2 — Uneinheitliche Zustandsmodelle verfälschen Vergleichs- und Run-Daten
**Beschreibung:** Branch Compare und Dashboard hängen stark von sauberen Run-, Simulation- und Statusdaten ab.  
**Gegenmaßnahme:** Run- und Simulation-State vor produktivem Ausbau konsolidieren.

## Risiko 3 — UI-Komplexität wächst schneller als Wartbarkeit
**Beschreibung:** Neue Panels und Kontrollansichten können die bestehenden XXL-Komponenten weiter aufblasen.  
**Gegenmaßnahme:** Workspace-Layout, Feature-Komponenten und Composables zuerst etablieren.

## Risiko 4 — Fehlende Messbarkeit führt zu Feature-Bias
**Beschreibung:** Features könnten nach subjektiver Attraktivität statt nach Nutzungswert priorisiert werden.  
**Gegenmaßnahme:** Vor Umsetzung je Feature KPI und Erfolgskriterium definieren.

## Risiko 5 — Live-Features werden zu früh angegangen
**Beschreibung:** SSE/WebSocket vor stabilen Async-Verträgen würde bestehende Unsauberkeiten verschärfen.  
**Gegenmaßnahme:** erst Polling zentralisieren, dann Eventing evaluieren.

---

## 9. KPIs

## Übergreifende Produkt-KPIs

1. **Zeit bis zum ersten belastbaren Ergebnis**  
   Vom Upload bis zu einem verwertbaren Report oder Vergleich.

2. **Anteil erfolgreich abgeschlossener End-to-End-Läufe**  
   Upload → Graph → Prepare → Simulation → Report ohne manuelle Eingriffe.

3. **Anteil wiederverwendeter Analysen**  
   Nutzung von Branches, Presets, Replay oder Exporten.

4. **Fehleraufwand pro Lauf**  
   Anzahl manueller Diagnose- oder Recovery-Schritte.

5. **Nutzungsintensität der Kernfeatures**  
   Dashboard-Aufrufe, Compare-Nutzung, Persona-Freigaben, Exporte.

## Feature-spezifische KPIs

| Feature | Primäre KPIs |
|---|---|
| Run Dashboard | Anteil der Läufe, die aus der Dashboard-Ansicht gesteuert werden; Zeit bis zur Fehlerlokalisierung; Nutzung von Resume/Restart |
| Scenario Branch Compare | Anzahl durchgeführter Vergleiche pro Projekt; Anteil der Projekte mit mindestens einem Vergleich; Zeit bis zur Variantenentscheidung |
| Persona Review & Approval | Anteil freigegebener vs. regenerierter Personas; Abbruchquote vor Start; reduzierte Nachkorrekturen nach Simulationsstart |
| Health & Setup Diagnostics | reduzierte Zahl technischer Fehlstarts; Zeit bis zur Problemdiagnose; Anteil erkannter Konfigurationsprobleme vor Laufstart |
| Interview Presets | Anteil Interviews mit Presets; Wiederholungsrate je Template; kürzere Zeit bis zur Auswertung |
| Export Center | Exportquote je Report/Run; genutzte Exportformate; Anteil von Projekten mit extern weiterverwendeten Artefakten |
| Replay / Reproduce Run | Anzahl reproduzierter Läufe; Vergleichsläufe pro Projekt; reduzierte Zeit für Wiederholungsexperimente |
| Prompt Presets | Anzahl gespeicherter/angewandter Presets; Nutzung pro Pipeline-Stufe |
| Graph Diff | Anteil von Vergleichen mit Diff-Nutzung; Zeit bis zur Identifikation relevanter Graphänderungen |
| Confidence / Evidence Score | Anteil Report-Abschnitte mit Score; niedrig bewertete Abschnitte mit manueller Nacharbeit; Vertrauen in Report-Ausgaben |
| SSE/WebSocket | niedrigere Request-Zahl pro aktivem Lauf; geringere UI-Latenz bei Statuswechseln |

---

## 10. Go/No-Go-Kriterien

## Go/No-Go für Horizont 1

**Go, wenn:**
- CI und Basis-Tests aktiv sind
- `simulation.py` deutlich entlastet oder in Split-Umsetzung ist
- Polling-Grundlogik zentralisiert ist
- gemeinsame Workspace-/Feature-Struktur vorhanden ist
- Kern-Statusmodelle nicht mehr offensichtlich redundant auseinanderlaufen

**No-Go, wenn:**
- zentrale Statusquellen weiterhin widersprüchlich sind
- neue Features nur durch weitere Vergrößerung von Monsterdateien umsetzbar wären
- Fehlersignale in UI und API noch zu uneinheitlich sind

---

## Go/No-Go für Run Dashboard

**Go, wenn:**
- Runs-API konsistente Statuswerte liefert
- Artefakte sauber auffindbar sind
- Resume/Restart technisch klar von normalen Runs getrennt modelliert werden können

**No-Go, wenn:**
- RunRegistry und Dateisystemstatus häufig auseinanderlaufen
- UI nur mit weiterer Duplizierung von Polling-/Statuslogik gebaut werden könnte

---

## Go/No-Go für Scenario Branch Compare

**Go, wenn:**
- Simulationskonfigurationen stabil versioniert sind
- Branches zuverlässig identifizierbar und vergleichbar sind
- Kernmetriken fachlich definiert sind

**No-Go, wenn:**
- Branches semantisch uneinheitlich gespeichert sind
- Reports, Runs und Simulationen keine belastbaren Vergleichs-IDs teilen

---

## Go/No-Go für Persona Review & Approval

**Go, wenn:**
- Persona-Generierung und Overrides klar gekapselt sind
- Review-Entscheidungen gespeichert und nachvollziehbar gemacht werden können

**No-Go, wenn:**
- Prepare-Flow weiterhin zu stark in Monolithen steckt
- genehmigte vs. regenerierte Persona-Stände nicht sauber versionierbar sind

---

## Go/No-Go für Horizont 2

**Go, wenn:**
- Run Dashboard und Compare produktiv stabil nutzbar sind
- standardisierte Export-/Artefaktmodelle vorliegen
- Kernverträge zwischen Backend und Frontend hinreichend stabil sind

**No-Go, wenn:**
- Reproduzierbarkeit noch nicht über Run-Manifeste und saubere Konfigurationsstände unterstützt wird
- Exporte pro Feature ad hoc statt systematisch gebaut werden müssten

---

## Go/No-Go für Horizont 3

**Go, wenn:**
- Graph- und Report-Datenmodelle explizit und stabil sind
- Evidence-/Compare-/State-Layer belastbar funktionieren
- Live-Updates technisch auf klaren Event-Verträgen aufsetzen können

**No-Go, wenn:**
- Graph Diff und Confidence nur mit heuristischen Sonderfällen statt konsistenten Modellen machbar wären
- Polling-Probleme noch nicht sauber gelöst sind

---

## 11. Empfohlene Umsetzungsreihenfolge

## Phase A — Freischalten der Roadmap
1. Quality Foundation
2. Tests für Kernzustände und Repositories
3. Simulation API Decomposition
4. Workspace Consolidation
5. Graph UI Modularization
6. Unified Polling and Async State

## Phase B — Höchster kurzfristiger Produktnutzen
1. Health & Setup Diagnostics
2. Run Dashboard / Operations Center
3. Scenario Branch Compare
4. Persona Review & Approval Flow

## Phase C — Ausbau zur Analyse-Workbench
1. Interview Presets / Research Templates
2. Export Center
3. Job Replay / Reproduce Run
4. Prompt Presets je Pipeline-Stufe

## Phase D — Reife- und Vertrauenslayer
1. Graph Diff vor/nach Simulation
2. Report Confidence / Evidence Score
3. SSE/WebSocket Live Updates

---

## 12. Empfehlung zur Priorisierung

Wenn nur wenig Kapazität verfügbar ist, sollte die Roadmap in genau dieser Reihenfolge reduziert werden:

1. **Run Dashboard / Operations Center**  
2. **Scenario Branch Compare**  
3. **Persona Review & Approval Flow**  
4. **Health & Setup Diagnostics**  
5. **Interview Presets / Research Templates**

Diese fünf Punkte liefern zusammen den größten realen Nutzwert für Steuerbarkeit, Analysequalität und Alltagstauglichkeit.

---

## 13. Zusammenfassung

Die Produktstrategie für Agora sollte nicht auf möglichst viele neue Features zielen, sondern auf **gezielte Erweiterungen mit hoher Hebelwirkung auf einer stabilisierten Basis**.

Die klare Priorität lautet:

1. **Technische Freigabe schaffen**
2. **Operations sichtbar machen**
3. **Szenarien vergleichbar machen**
4. **Eingangsqualität und Wiederverwendbarkeit verbessern**
5. **Vertrauen und Echtzeitfähigkeit später ergänzen**

Der wichtigste Leitsatz für die nächsten Monate bleibt:

> **Zuerst Stabilität und Vergleichbarkeit, dann Tiefe und Echtzeit.**
