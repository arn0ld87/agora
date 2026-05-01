# Metric-Snapshot-Diagnose (S0 + S2-pre)

**Datum:** 2026-05-01T08:05:19+02:00
**Diagnostizierte Sim-Runs:** 10

## Status nach S2-pre

| Verdict | Vor S2-pre | Nach S2-pre |
|---|---:|---:|
| `metrics_consistent` | 0 | **7** |
| `broadcast_only_no_pairwise` | 2 | 2 |
| `directed_actions_but_no_agents_extracted` | 8 | 1 |

Akzeptanzkriterium von Issue #104 (≥6/10 `metrics_consistent`) **erfüllt** mit 7/10. Die zwei `broadcast_only_no_pairwise`-Runs sind echte Test-Fixtures mit ausschließlich `CREATE_POST`-Actions; deren 0er-Metrik wird in S2a über einen Status-Flag transparent gemacht.

Der eine verbliebene `directed_actions_but_no_agents_extracted`-Run (`sim_65bfd5702ab0`) ist ein **Edge-Case ohne Bug-Charakter**: insgesamt nur 3 directed Actions, davon 1 `FOLLOW` ohne `target_user_name` (OASIS hat den Namen ausnahmsweise nicht mit-geloggt) und 1 `LIKE_COMMENT` als Self-Loop (Eva Feußner liked ihren eigenen Kommentar). Beide werden korrekt verworfen. Zukünftiger Mini-Slice könnte das Verdict-Mapping in `diagnose_metric_snapshot.py` verfeinern (`directed_actions_filtered_to_empty` als eigene Kategorie für Self-Loops + nicht-resolvebare Targets), nicht S2-pre-blockierend.

## Hauptbefund (S0, Pre-Fix)

**8 von 10 Runs (80 %) trugen vor S2-pre den Verdict `directed_actions_but_no_agents_extracted`.**
Der `NetworkAnalyticsService` lieferte strukturell `0/0/0/0` für Polarization-Metriken — bei *jedem* Run mit pairwise Interactions. Das Polarization-Feature (Issue #12) war faktisch tot, nicht kosmetisch falsch.

### Root-Cause (Pre-Fix)

Der Code suchte in `action_args` nach numerischen Keys:

```python
for key in ("target_agent_id", "followee_id", "user_id", "target_user_id", "author_id"):
    val = args.get(key)
    if val is not None: return int(val)
```

Reale OASIS-Action-Args für `LIKE_POST` (aus `sim_660e1a87dad5/twitter/actions.jsonl`):

```json
{
  "action_args": {
    "post_id": 1,
    "like_id": 1,
    "post_content": "...",
    "post_author_name": "Landesregierung Nordrhein-Westfalen"
  }
}
```

Kein einziger gesuchter Key drin. OASIS loggt `post_id` + `post_author_name` (String), nicht `author_id` → `_extract_target_agent` returned `None` → Interaction wurde verworfen → leerer Graph → 0/0/0/0.

## Fix (S2-pre, commit-folgender Slice)

Implementiert wurde **Variante 3 mit Twist**: Reverse-Lookup `agent_name → agent_id` aus den Actions selbst (jede Action trägt `agent_id` + `agent_name`), statt einer `post_id → agent_id`-Map. Begründung: `CREATE_POST` loggt im OASIS-Output **keine `post_id`**, eine ID-basierte Map wäre nicht aufbaubar gewesen. Die Strings (`post_author_name`, `comment_author_name`, `target_user_name`, `original_author_name`) sind aber bei jeder directed Action mit-geloggt — kollisionsfrei, solange Agent-Namen unique sind (OASIS-Profile-Generation-Default).

Zusätzlich: `comment_id → agent_id`-Index aus `CREATE_COMMENT`-Actions, damit `LIKE_COMMENT`/`DISLIKE_COMMENT` auch dann auflösen, wenn `comment_author_name` ausnahmsweise fehlt.

Bestehende Tests (`followee_id`/`author_id`-basiert) wurden NICHT angefasst: die alten ID-Keys bleiben als erste Lookup-Tier erhalten und sichern Rückwärtskompatibilität.

### Sekundärbefund (gilt unverändert)

`SEARCH_USER`, `TREND`, `DO_NOTHING`, `SEARCH_POSTS` sind nicht in `_DIRECTED_ACTIONS` und werden korrekt ignoriert. `MUTE` ist in `_DIRECTED_ACTIONS`, hat aber `action_args = {}` — wird durch das fehlende Target nun ebenfalls korrekt verworfen.

## Methodik

Skript repliziert den Pfad aus `report_agent._collect_simulation_evidence_items`:

1. `SimulationRunner.get_all_actions(sim_id)` — liest `<sim>/twitter/actions.jsonl` und `<sim>/reddit/actions.jsonl`
2. `NetworkAnalyticsService.compute_metrics(...)` — Louvain-Communities + Echo-Chamber-Index
3. Vergleich mit Action-Type-Histogramm und `_DIRECTED_ACTIONS`-Filter

## Ergebnis-Tabelle

| Sim | Status | Lines (T/R) | Actions | Directed | Agents | Metric agents/inter/cluster | Verdict |
|---|---|---|---|---|---|---|---|
| `sim_660e1a87dad5` | paused | 590/766 | 1046 | 745 | 20 | 20/361/3 | **metrics_consistent** |
| `sim_e2dcc0797dfd` | running | 137/139 | 188 | 108 | 18 | 17/46/3 | **metrics_consistent** |
| `sim_c03db93ddebd` | running | 237/244 | 381 | 227 | 20 | 20/112/4 | **metrics_consistent** |
| `sim_65bfd5702ab0` | ready | 41/40 | 31 | 3 | 9 | 0/0/0 | **directed_actions_but_no_agents_extracted** |
| `sim_397e32bf8483` | stopped | 308/267 | 395 | 238 | 13 | 13/93/3 | **metrics_consistent** |
| `sim_645585de00d9` | stopped | 44/53 | 49 | 13 | 9 | 5/6/2 | **metrics_consistent** |
| `sim_fb7eb300ce71` | stopped | 29/7 | 10 | 0 | 5 | 0/0/0 | **broadcast_only_no_pairwise** |
| `sim_1788f01ab463` | stopped | 185/201 | 214 | 99 | 18 | 11/36/3 | **metrics_consistent** |
| `sim_1d2298b006ed` | running | 264/565 | 533 | 274 | 11 | 11/111/3 | **metrics_consistent** |
| `sim_03717ada1e52` | ready | 11/11 | 10 | 0 | 5 | 0/0/0 | **broadcast_only_no_pairwise** |

## Action-Type-Histogramm pro Run

### `sim_660e1a87dad5` — verdict: **metrics_consistent**

| Type | Count | In _DIRECTED_ACTIONS? |
|---|---|---|
| `CREATE_COMMENT` | 323 | ✅ |
| `CREATE_POST` | 300 | ❌ |
| `QUOTE_POST` | 144 | ✅ |
| `LIKE_POST` | 119 | ✅ |
| `LIKE_COMMENT` | 79 | ✅ |
| `FOLLOW` | 44 | ✅ |
| `REPOST` | 36 | ✅ |
| `SEARCH_USER` | 1 | ❌ |

### `sim_e2dcc0797dfd` — verdict: **metrics_consistent**

| Type | Count | In _DIRECTED_ACTIONS? |
|---|---|---|
| `CREATE_POST` | 50 | ❌ |
| `LIKE_POST` | 26 | ✅ |
| `CREATE_COMMENT` | 25 | ✅ |
| `QUOTE_POST` | 20 | ✅ |
| `LIKE_COMMENT` | 16 | ✅ |
| `DO_NOTHING` | 16 | ❌ |
| `FOLLOW` | 14 | ✅ |
| `SEARCH_POSTS` | 8 | ❌ |
| `DISLIKE_POST` | 4 | ✅ |
| `SEARCH_USER` | 4 | ❌ |
| `TREND` | 2 | ❌ |
| `REPOST` | 2 | ✅ |
| `MUTE` | 1 | ✅ |

### `sim_c03db93ddebd` — verdict: **metrics_consistent**

| Type | Count | In _DIRECTED_ACTIONS? |
|---|---|---|
| `CREATE_POST` | 99 | ❌ |
| `CREATE_COMMENT` | 58 | ✅ |
| `QUOTE_POST` | 52 | ✅ |
| `LIKE_POST` | 40 | ✅ |
| `FOLLOW` | 33 | ✅ |
| `LIKE_COMMENT` | 28 | ✅ |
| `DO_NOTHING` | 27 | ❌ |
| `SEARCH_USER` | 16 | ❌ |
| `DISLIKE_POST` | 8 | ✅ |
| `SEARCH_POSTS` | 8 | ❌ |
| `REPOST` | 8 | ✅ |
| `TREND` | 4 | ❌ |

### `sim_65bfd5702ab0` — verdict: **directed_actions_but_no_agents_extracted**

| Type | Count | In _DIRECTED_ACTIONS? |
|---|---|---|
| `CREATE_POST` | 26 | ❌ |
| `FOLLOW` | 1 | ✅ |
| `LIKE_COMMENT` | 1 | ✅ |
| `CREATE_COMMENT` | 1 | ✅ |
| `SEARCH_USER` | 1 | ❌ |
| `SEARCH_POSTS` | 1 | ❌ |

### `sim_397e32bf8483` — verdict: **metrics_consistent**

| Type | Count | In _DIRECTED_ACTIONS? |
|---|---|---|
| `CREATE_POST` | 80 | ❌ |
| `CREATE_COMMENT` | 60 | ✅ |
| `LIKE_POST` | 50 | ✅ |
| `DO_NOTHING` | 44 | ❌ |
| `QUOTE_POST` | 36 | ✅ |
| `LIKE_COMMENT` | 31 | ✅ |
| `FOLLOW` | 27 | ✅ |
| `REPOST` | 24 | ✅ |
| `SEARCH_POSTS` | 20 | ❌ |
| `SEARCH_USER` | 13 | ❌ |
| `DISLIKE_POST` | 7 | ✅ |
| `DISLIKE_COMMENT` | 2 | ✅ |
| `MUTE` | 1 | ✅ |

### `sim_645585de00d9` — verdict: **metrics_consistent**

| Type | Count | In _DIRECTED_ACTIONS? |
|---|---|---|
| `CREATE_POST` | 36 | ❌ |
| `LIKE_POST` | 5 | ✅ |
| `CREATE_COMMENT` | 5 | ✅ |
| `LIKE_COMMENT` | 2 | ✅ |
| `QUOTE_POST` | 1 | ✅ |

### `sim_fb7eb300ce71` — verdict: **broadcast_only_no_pairwise**

| Type | Count | In _DIRECTED_ACTIONS? |
|---|---|---|
| `CREATE_POST` | 10 | ❌ |

### `sim_1788f01ab463` — verdict: **metrics_consistent**

| Type | Count | In _DIRECTED_ACTIONS? |
|---|---|---|
| `CREATE_POST` | 74 | ❌ |
| `CREATE_COMMENT` | 33 | ✅ |
| `LIKE_POST` | 25 | ✅ |
| `FOLLOW` | 24 | ✅ |
| `DO_NOTHING` | 22 | ❌ |
| `SEARCH_POSTS` | 11 | ❌ |
| `LIKE_COMMENT` | 8 | ✅ |
| `DISLIKE_POST` | 5 | ✅ |
| `TREND` | 4 | ❌ |
| `SEARCH_USER` | 4 | ❌ |
| `DISLIKE_COMMENT` | 2 | ✅ |
| `QUOTE_POST` | 1 | ✅ |
| `MUTE` | 1 | ✅ |

### `sim_1d2298b006ed` — verdict: **metrics_consistent**

| Type | Count | In _DIRECTED_ACTIONS? |
|---|---|---|
| `CREATE_COMMENT` | 158 | ✅ |
| `CREATE_POST` | 150 | ❌ |
| `SEARCH_USER` | 84 | ❌ |
| `LIKE_POST` | 75 | ✅ |
| `LIKE_COMMENT` | 41 | ✅ |
| `DO_NOTHING` | 13 | ❌ |
| `SEARCH_POSTS` | 8 | ❌ |
| `TREND` | 4 | ❌ |

### `sim_03717ada1e52` — verdict: **broadcast_only_no_pairwise**

| Type | Count | In _DIRECTED_ACTIONS? |
|---|---|---|
| `CREATE_POST` | 10 | ❌ |

## Verdict-Kategorien

- **`no_actions_logged`** — actions.jsonl leer/fehlend. Sim wurde nicht oder unvollständig durchgelaufen.
- **`broadcast_only_no_pairwise`** — actions.jsonl gefüllt, aber nur `CREATE_POST`/`CREATE_COMMENT`-Broadcasts ohne pairwise Interactions wie `LIKE_POST`/`FOLLOW`. Metriken sind technisch korrekt 0, aber semantisch eine Lüge im Report-Export.
- **`directed_actions_but_no_agents_extracted`** — Directed Actions vorhanden, aber `_extract_target_agent` findet keine Target-IDs. Schema-Mismatch.
- **`directed_actions_filtered_to_empty`** — Directed Actions vorhanden mit Targets, aber alle werden später gefiltert (z. B. self-loops). Sollte selten sein.
- **`metrics_consistent`** — Metriken passen zu Actions, kein Bug.

## Konsequenzen für S2

Die Diagnose-Verteilung bestimmt, was S2a (Snapshot-Hardening) konkret tun muss:

- Bei vielen `broadcast_only_no_pairwise` → S2a sollte einen **Status-Flag** im Snapshot setzen (`status: "no_pairwise_interactions"`) statt 0/0/0/0 als Metrik auszugeben. UI in S2b zeigt dann Metriken-nicht-verfuegbar.
- Bei `no_actions_logged` → ähnlich, Status `no_actions`.
- Bei `directed_actions_but_no_agents_extracted` → echter Bug in `_extract_target_agent`, separate Untersuchung.

