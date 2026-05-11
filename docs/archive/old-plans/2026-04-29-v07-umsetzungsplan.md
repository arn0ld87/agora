# Agora v0.7 Umsetzungsplan

**Ziel:** Agora von v0.6.1 Alpha zu einer stabileren lokalen Analyse-Workbench weiterentwickeln: nachvollziehbare Runs, prüfbare Personas, belastbare Reports und konsistentes UI.

**Leitplanken:**
- Kleine PR-Slices statt Big-Bang-Umbau.
- Bestehende Strukturen erweitern, nicht doppelt neu bauen.
- Nach jedem Slice `npm run check`.
- Doku aktualisieren, wenn Verhalten, Datenmodell oder Bedienung sichtbar anders wird.

## Slice 0: Inventur

**Ziel:** Bestehende Implementierung gegen `docs/agora_weiterentwicklung.md` mappen.

**Prüfen:**
- `frontend/src/assets/styles/tokens.css`
- `frontend/src/assets/styles/global.css`
- `frontend/src/components/ui/`
- `frontend/src/layouts/`
- `frontend/src/api/runs.ts`
- `backend/app/api/runs.py`
- `backend/app/utils/api_responses.py`
- `backend/app/services/persona_library.py`
- Simulation-Artefakte unter `backend/app/services/artifact_store.py`

**Ergebnis:** Kurze Notiz in der jeweiligen PR-Beschreibung, welche Teile schon existieren und welche ergänzt wurden.

## Slice 1: Design-System konsolidieren

**Ziel:** Vorhandene Agora-Tokens produktiv nutzen und harte Hauptfarben im Frontend reduzieren.

**Vorgehen:**
1. `frontend/src/assets/styles/tokens.css` als Source-of-Truth bestätigen oder bereinigen.
2. Globale Layout- und Utility-Klassen in `frontend/src/assets/styles/global.css` konsolidieren.
3. UI-Basis-Komponenten `Btn`, `Badge`, `Field`, `Card`, `Select` auf Tokens prüfen.
4. Views und Layouts nach harten Farbwerten scannen.
5. Nur Hauptfarben ersetzen, keine visuelle Komplettneugestaltung.

**Akzeptanzkriterien:**
- Keine neuen hart codierten Hauptfarben.
- Orange bleibt primäre Action-Farbe.
- Plasma/Cyan bleibt Info-/Graph-Akzent.
- Pipeline-Views wirken konsistenter.
- `npm run lint:frontend`, `npm run build` und anschließend `npm run check` sind grün.

## Slice 2: Persona Review Foundation

**Ziel:** Generierte Personas vor Simulationsstart prüfbar, editierbar und freigebbar machen.

**Backend:**
- Service für Review-Status, Bearbeitung, Löschen, Approve/Reject.
- Persistenz über vorhandene Simulation-Artefakte.
- Quality-MVP: Dubletten, fehlende Kernfelder, Entity-Bezug, Rollen-Diversität.
- Start der Simulation an Approval koppeln, wenn Review aktiv ist.

**Frontend:**
- Persona-Liste oder Tabelle.
- Editor-Drawer.
- Quality-Badges.
- Approve/Reject-Aktionen.

**Tests:**
- Service-Tests für Persistenz und Statusübergänge.
- API-Tests für Fehlerfälle.
- Frontend-Composable-Tests, falls neue Logik entsteht.

## Slice 3: Run Dashboard

**Ziel:** Bestehende Runs zentral sichtbar und nachvollziehbar machen.

**Backend:**
- Bestehende `/api/runs`-API erweitern, nicht ersetzen.
- Details, Fehlerzustände und Artefaktlinks sauber ausgeben.
- Delete/Duplicate/Resume nur implementieren, wenn Semantik geklärt und testbar ist.

**Frontend:**
- Dashboard-View mit Status, Datum, Modell, Dokument, Graph-ID, Persona-Anzahl.
- Detail-Drawer für Fehler und Artefakte.
- Aktionen zuerst read-only/öffnen; mutierende Aktionen danach.

**Tests:**
- API-Tests für Liste, Filter, Detail, Not-found.
- Frontend-Build und Lint.

## Slice 4: Evidence & Confidence MVP

**Ziel:** Report-Aussagen nachvollziehbar machen.

**Datenmodell:**

```json
{
  "claim": "Akteursgruppe X polarisiert die Diskussion stark.",
  "confidence": 0.78,
  "evidence": [
    {
      "type": "graph_metric",
      "source": "simulation_metrics",
      "value": "echo_chamber_index=0.64"
    }
  ]
}
```

**Vorgehen:**
1. Abwärtskompatibles Claim/Evidence-Modell definieren.
2. Evidence aus vorhandenen Metriken und Agentenaktionen sammeln.
3. Report UI um Confidence-Badge und Evidence-Drawer erweitern.
4. JSON- und Markdown-Export ergänzen.

**Tests:**
- Report-Modell-Tests.
- Export-Tests.
- UI-Build.

## Slice 5: Export Center

**Ziel:** Ergebnisse sauber weitergeben.

**Reihenfolge:**
1. JSON und Markdown stabilisieren.
2. CSV für Metriken.
3. GraphML für Graphanalyse.
4. PNG/SVG erst nach Prüfung der aktuellen Graph-Komponente.
5. PDF zuletzt, weil Layout- und Rendering-Aufwand höher ist.

## Slice 6: Branch Compare

**Ziel:** Szenarien vergleichbar machen.

**Voraussetzungen:**
- Runs sind stabil gespeichert.
- Reports haben strukturierte Claims.
- Metriken sind versioniert abrufbar.

**MVP:**
- Zwei Runs auswählen.
- Metrik-Diff anzeigen.
- Top-Claims vergleichen.
- Persona-Verschiebungen anzeigen.

## Offene Architekturentscheidungen

- Ob Persona Review default-on oder opt-in startet.
- Ob Run-Mutationen sofort physisch löschen oder erst archivieren.
- Ob API-Response-Envelopes vor oder während Persona/Run-Features vereinheitlicht werden.
- Ob Export-Artefakte persistiert oder on-demand erzeugt werden.
