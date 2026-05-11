# S2b — Evidence-Pool respektiert Metric-Status · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** S2b

## Scope-Anpassung

Ursprünglicher Plan: „Frontend zeigt Metriken nicht verfügbar". Codebasis-Recherche zeigt: es gibt keinen aktiven Frontend-Konsument für Polarization-Metriken (kein Vue-View, kein Composable). Die Metriken landen ausschließlich im Report-Evidence-Pool über `report_agent._collect_simulation_evidence_items`. S2b verschiebt sich logisch dorthin.

## Implementierung

`backend/app/services/report_agent.py:1033+`: wenn `metrics.status != "ok"`, **kein einzelnes Pseudo-Metric-Item** mehr generieren. Stattdessen ein einzelnes `graph_metric_status`-Evidence-Item mit klarer Aussage „Polarization-Metriken nicht verfügbar (Status: …)". Damit verschwinden die irreführenden 0/0/0/0-Belege aus dem Report, ohne den Audit-Trail vollständig zu kappen.

## Tests

13 bestehende Report-Tests grün. Volles `npm run check` grün.
