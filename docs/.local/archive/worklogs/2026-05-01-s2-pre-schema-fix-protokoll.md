# S2-pre — Schema-Fix `_extract_target_agent` · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** S2-pre (Evidence-Pipeline-v2-Initiative)
**Plan:** [docu/2026-05-01-evidence-pipeline-plan.md](2026-05-01-evidence-pipeline-plan.md)
**Issues:** [#104](https://github.com/arn0ld87/agora/issues/104) (Sub-Issue), [#103](https://github.com/arn0ld87/agora/issues/103) (Epic)
**Status:** abgeschlossen

## Ziel

Den in S0 entdeckten Schema-Mismatch in `NetworkAnalyticsService._extract_target_agent` schließen: Code suchte numerische Keys (`author_id`, `followee_id`, …), OASIS loggte Strings (`*_author_name`, `target_user_name`). Folge: 8/10 produktive Sim-Runs lieferten `0/0/0/0`-Polarization-Metriken.

## Vorgehen

1. Reale OASIS-Action-Args für alle directed Action-Types aus `sim_660e1a87dad5/{twitter,reddit}/actions.jsonl` extrahiert. Schema-Tabelle in Issue #104 dokumentiert.
2. Drei Lookup-Tier in `_extract_target_agent` implementiert:
   - **Tier 1** — alte numerische ID-Keys (Rückwärtskompatibilität für bestehende Tests).
   - **Tier 2** — `comment_id → agent_id`-Index aus `CREATE_COMMENT`-Actions, für `LIKE_COMMENT`/`DISLIKE_COMMENT`.
   - **Tier 3** — `agent_name → agent_id`-Reverse-Lookup aus den Actions selbst, für `*_author_name`/`target_user_name`-Strings.
3. Neue Helper `_build_lookup_indexes(actions)` — single-pass, deterministisch (erste Beobachtung gewinnt bei Namens-Kollisionen).
4. `_iter_interactions` materialisiert die Action-Liste, baut beide Indexe vorab, dann iteriert.

## Implementierung

`backend/app/services/network_analytics.py`:

- Neue Konstante `_TARGET_NAME_KEYS` mit den OASIS-Strings.
- `_extract_target_agent` bekommt zwei optionale Parameter `name_to_id` und `comment_to_author`. Tier-Reihenfolge: legacy-IDs → comment-id-resolve → name-resolve.
- Neue Module-Funktion `_build_lookup_indexes(actions) -> (Dict[str,int], Dict[int,int])`.
- `_iter_interactions` ruft `_build_lookup_indexes` einmal pro `compute_metrics`-Call.

## Tests

`backend/tests/test_network_analytics.py` um 7 neue Cases erweitert (alle grün):

- `test_like_post_resolved_via_post_author_name`
- `test_follow_resolved_via_target_user_name`
- `test_repost_and_quote_post_resolved_via_original_author_name`
- `test_like_comment_resolved_via_comment_id_index`
- `test_mute_without_target_is_ignored`
- `test_unknown_author_name_skipped_not_crashing`
- `test_full_oasis_run_mixed_directed_actions`

Bestehende 7 Cases unverändert grün — `followee_id`/`author_id`-Pfad bleibt funktional.

## Akzeptanzkriterien

| Kriterium | Status |
|---|---|
| Diagnose-Skript: ≥6/10 Runs `metrics_consistent` | ✅ **7/10** |
| Bestehende Unit-Tests grün | ✅ 7/7 |
| Neue Unit-Tests mit OASIS-Schema | ✅ 7/7 |
| `npm run check` grün | ✅ 495 Backend + 40 Frontend |
| Self-Loops bleiben gefiltert | ✅ |
| Actions ohne Target ignoriert (MUTE, unknown name) | ✅ |

## Diagnose-Vergleich Vorher / Nachher

| Verdict | Vor S2-pre | Nach S2-pre |
|---|---:|---:|
| `metrics_consistent` | 0 | **7** |
| `broadcast_only_no_pairwise` | 2 | 2 |
| `directed_actions_but_no_agents_extracted` | 8 | 1 |

`sim_660e1a87dad5`: 745 directed Actions, vorher Metrik 0/0/0, jetzt **20 agents / 361 interactions / 3 cluster**.

Der einzige verbliebene `directed_actions_but_no_agents_extracted` (`sim_65bfd5702ab0`) ist ein Edge-Case ohne Bug-Charakter: 1 FOLLOW ohne `target_user_name` (OASIS-Quirk), 1 LIKE_COMMENT als Self-Loop. Beide werden korrekt verworfen. Verdict-Klassifizierung im Diagnose-Skript könnte verfeinert werden (`directed_actions_filtered_to_empty` als eigene Kategorie), nicht S2-pre-blockierend.

## Geänderte/neue Dateien

- `backend/app/services/network_analytics.py` — Schema-Fix
- `backend/tests/test_network_analytics.py` — +7 Tests
- `docu/2026-05-01-metric-snapshot-diagnose.md` — Vorher/Nachher-Sektion + Fix-Doku
- `docu/2026-05-01-s2-pre-schema-fix-protokoll.md` (neu, dieses Protokoll)

## Folgeaktionen

- **S2a (nächster Slice)** — Status-Flag `no_pairwise_interactions` für Broadcast-Only-Runs, plus `snapshot_id`/`calculated_at` im Metrics-Output.
- **S2b** — Frontend zeigt „Metriken nicht verfügbar" bei Status-Flag.
- Optionaler Mini-Slice: Verdict-Mapping in `diagnose_metric_snapshot.py` verfeinern (Self-Loop / no-target-name als eigene Kategorie).
