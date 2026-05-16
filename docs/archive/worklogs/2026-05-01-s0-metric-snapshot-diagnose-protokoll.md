# S0 — Metric-Snapshot-Diagnose · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** S0 (Diagnose-Slice der Evidence-Pipeline-v2-Initiative)
**Plan:** [docu/2026-05-01-evidence-pipeline-plan.md](2026-05-01-evidence-pipeline-plan.md)
**Status:** abgeschlossen

## Ziel

Reproduzieren, ob der externe Review-Befund („`total_agents=0`/`total_interactions=0` neben vorhandenen `simulation_actions`") in lokalen Sim-Runs auftritt, und Root-Cause klassifizieren — bevor S2 implementiert wird.

## Vorgehen

1. Codepfad in `report_agent._collect_simulation_evidence_items` (`backend/app/services/report_agent.py:1022`) gelesen — er ruft `SimulationRunner.get_all_actions(sim_id)` und reicht das in `NetworkAnalyticsService.compute_metrics`.
2. `SimulationRunner.get_all_actions` liest `<sim>/twitter/actions.jsonl` und `<sim>/reddit/actions.jsonl` (`backend/app/services/simulation_runner.py:1010`).
3. `NetworkAnalyticsService` (`backend/app/services/network_analytics.py`) filtert auf `_DIRECTED_ACTIONS`, ruft `_extract_target_agent` und baut den Interaktionsgraph.
4. Diagnose-Skript `backend/scripts/diagnose_metric_snapshot.py` repliziert exakt diesen Pfad, klassifiziert das Ergebnis pro Run in fünf Verdict-Buckets und schreibt einen Markdown-Bericht.
5. Skript gegen die letzten 10 Runs mit non-empty actions.jsonl ausgeführt.

## Verdict-Verteilung (10 Runs)

| Verdict | Count |
|---|---|
| `directed_actions_but_no_agents_extracted` | **8** |
| `broadcast_only_no_pairwise` | 2 |
| `metrics_consistent` | 0 |

Vollständiger Bericht: [docu/2026-05-01-metric-snapshot-diagnose.md](2026-05-01-metric-snapshot-diagnose.md).

## Hauptbefund

Der Review-Reviewer war zu mild. Es ist nicht „Snapshot-Timing" oder „CREATE_POST-Übergewicht" — es ist ein **Schema-Mismatch** in `_extract_target_agent`:

- Code sucht nach `target_agent_id`, `followee_id`, `user_id`, `target_user_id`, `author_id`.
- OASIS-Logs enthalten für `LIKE_POST` etc. nur `post_id`, `like_id`, `post_content`, `post_author_name` (String, keine ID).
- Kein einziger der gesuchten Keys ist drin → `_extract_target_agent` returned `None` → Interaction wird verworfen.
- Folge: bei *jedem* Run mit pairwise Actions wird `total_interactions=0` ausgegeben, die Polarization-Metrik (Issue #12) ist faktisch tot.

Beispiel-Run `sim_660e1a87dad5`:

- 1046 Actions geloggt, davon 745 directed (LIKE_POST, FOLLOW, QUOTE_POST, …)
- 20 Unique Agents
- Trotzdem: `total_agents=0`, `total_interactions=0`, `cluster_count=0`

## Konsequenzen

Der Plan wurde um **S2-pre** ergänzt: Schema-Fix vor Status-Flag-Hardening. Reihenfolge-Update in [docu/2026-05-01-evidence-pipeline-plan.md](2026-05-01-evidence-pipeline-plan.md) gepflegt.

Empfohlene Fix-Strategie (Variante 3 aus dem Diagnose-Bericht): In-Memory-Index aus `CREATE_POST`/`CREATE_COMMENT`-Actions aufbauen (`post_id → agent_id`, `comment_id → agent_id`), dann in `_iter_interactions` für `LIKE_POST` etc. resolven. Stateless, kein DB-Zugriff nötig.

Die `broadcast_only_no_pairwise`-Fälle (kleine Test-Runs mit nur `CREATE_POST`) bleiben — dort ist die 0er-Metrik inhaltlich korrekt, muss aber ein Status-Flag im Snapshot tragen statt nackte Nullen (S2a).

## Tests

Slice ist read-only (Diagnose-Skript, keine Code-Änderungen am Service). `npm run check`-Lauf: TODO unten.

## Geänderte/neue Dateien

- `docu/2026-05-01-evidence-pipeline-plan.md` (neu) — Master-Plan, mit S2-pre nachgezogen
- `docu/2026-05-01-metric-snapshot-diagnose.md` (neu) — Diagnose-Bericht
- `docu/2026-05-01-s0-metric-snapshot-diagnose-protokoll.md` (neu) — dieses Protokoll
- `backend/scripts/diagnose_metric_snapshot.py` (neu) — Diagnose-Skript

## Folgeaktionen

- Issue-Anlage: Epic „Evidence-Pipeline v2 + Repo-Hygiene Sweep" + Sub-Issue für S2-pre (Schema-Fix). Alex-OK abgewartet.
- S1 (XSS-Fix) parallel zu S2-pre möglich, weil unabhängig.
- S2-pre Akzeptanzkriterium: nach Implementation Diagnose-Skript erneut laufen lassen, Verdict-Verteilung muss kippen (≥6/10 `metrics_consistent`).
