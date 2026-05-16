# Slice 4: Evidence & Confidence MVP

## Ziel

Report-Aussagen sind nachvollziehbarer, weil Claims strukturierte Evidence und einen Confidence-Score bekommen.

## Umsetzung

1. `backend/app/services/report_agent.py`
   - Claim-/Evidence-Modell mit `confidence_score`, `confidence_label`, `evidence` und abwärtskompatiblem `evidence_items` ergänzt.
   - Evidence aus Report-Toolaufrufen, Simulation-Metriken und Agentenaktionen gesammelt.
   - Evidence-Map mit `schema_version` und `global_evidence` erweitert.
2. `frontend/src/components/Step4Report.vue`
   - Evidence Inspector kann alte und neue Claim-Formate anzeigen.
   - Confidence-Badge zeigt Score und Label.
   - Evidence-Einträge zeigen Typ, Quelle und Snippet.
3. `backend/tests/test_report_manager.py`
   - Tests für Claim-Shape, Metrik-/Action-Evidence und Evidence-Persistenz ergänzt.

## Kompatibilität

- Bestehende Reports mit `evidence_items` und textuellem `confidence`-Wert bleiben renderbar.
- Neue Evidence-Maps liefern zusätzlich `confidence_score` und `evidence`.
- `confidence` bleibt als Label erhalten, damit bestehende Consumer nicht brechen.

## Prüfung

Ausgeführt:

```bash
cd backend && uv run pytest tests/test_report_manager.py
cd frontend && npm run build
```
