# Metric-Snapshot-Diagnose (S0)

**Datum:** 2026-05-01T07:40:16+02:00
**Diagnostizierte Sim-Runs:** 10

## Methodik

Skript repliziert den Pfad aus `report_agent._collect_simulation_evidence_items`:

1. `SimulationRunner.get_all_actions(sim_id)` — liest `<sim>/twitter/actions.jsonl` und `<sim>/reddit/actions.jsonl`
2. `NetworkAnalyticsService.compute_metrics(...)` — Louvain-Communities + Echo-Chamber-Index
3. Vergleich mit Action-Type-Histogramm und `_DIRECTED_ACTIONS`-Filter

## Ergebnis-Tabelle

| Sim | Status | Lines (T/R) | Actions | Directed | Agents | Metric agents/inter/cluster | Verdict |
|---|---|---|---|---|---|---|---|
| `sim_660e1a87dad5` | paused | 590/766 | 1046 | 745 | 20 | 0/0/0 | **directed_actions_but_no_agents_extracted** |
| `sim_e2dcc0797dfd` | running | 137/139 | 188 | 108 | 18 | 0/0/0 | **directed_actions_but_no_agents_extracted** |
| `sim_c03db93ddebd` | running | 237/244 | 381 | 227 | 20 | 0/0/0 | **directed_actions_but_no_agents_extracted** |
| `sim_65bfd5702ab0` | ready | 41/40 | 31 | 3 | 9 | 0/0/0 | **directed_actions_but_no_agents_extracted** |
| `sim_397e32bf8483` | stopped | 308/267 | 395 | 238 | 13 | 0/0/0 | **directed_actions_but_no_agents_extracted** |
| `sim_645585de00d9` | stopped | 44/53 | 49 | 13 | 9 | 0/0/0 | **directed_actions_but_no_agents_extracted** |
| `sim_fb7eb300ce71` | stopped | 29/7 | 10 | 0 | 5 | 0/0/0 | **broadcast_only_no_pairwise** |
| `sim_1788f01ab463` | stopped | 185/201 | 214 | 99 | 18 | 0/0/0 | **directed_actions_but_no_agents_extracted** |
| `sim_1d2298b006ed` | running | 264/565 | 533 | 274 | 11 | 0/0/0 | **directed_actions_but_no_agents_extracted** |
| `sim_03717ada1e52` | ready | 11/11 | 10 | 0 | 5 | 0/0/0 | **broadcast_only_no_pairwise** |

## Action-Type-Histogramm pro Run

### `sim_660e1a87dad5` — verdict: **directed_actions_but_no_agents_extracted**

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

### `sim_e2dcc0797dfd` — verdict: **directed_actions_but_no_agents_extracted**

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

### `sim_c03db93ddebd` — verdict: **directed_actions_but_no_agents_extracted**

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

### `sim_397e32bf8483` — verdict: **directed_actions_but_no_agents_extracted**

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

### `sim_645585de00d9` — verdict: **directed_actions_but_no_agents_extracted**

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

### `sim_1788f01ab463` — verdict: **directed_actions_but_no_agents_extracted**

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

### `sim_1d2298b006ed` — verdict: **directed_actions_but_no_agents_extracted**

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

## Hauptbefund

**8 von 10 Runs (80 %) tragen den Verdict `directed_actions_but_no_agents_extracted`.**
Damit liefert der `NetworkAnalyticsService` heute strukturell `0/0/0/0` für Polarization-Metriken — bei *jedem* echten Run mit pairwise Interactions. Das Polarization-Feature (Issue #12) ist faktisch tot, nicht nur kosmetisch falsch.

### Root-Cause: Schema-Mismatch in `_extract_target_agent`

Code-Annahme (`backend/app/services/network_analytics.py:86-109`):

```python
for key in ("target_agent_id", "followee_id", "user_id", "target_user_id", "author_id"):
    val = args.get(key)
    if val is not None: return int(val)
```

Reale OASIS-Action-Args für `LIKE_POST` (aus `sim_660e1a87dad5/twitter/actions.jsonl`):

```json
{
  "action_type": "LIKE_POST",
  "agent_id": 14,
  "agent_name": "Gesamtschule Brünninghausen",
  "action_args": {
    "post_id": 1,
    "like_id": 1,
    "post_content": "...",
    "post_author_name": "Landesregierung Nordrhein-Westfalen"
  }
}
```

→ Kein einziger der gesuchten Keys ist drin. OASIS schreibt `post_id` + `post_author_name` (String), nicht `author_id`.
→ `_extract_target_agent` returned `None`, Interaction wird verworfen.
→ `compute_metrics` baut einen leeren Graphen, Metriken sind 0.

### Was im Code ankommen muss

Das Mapping `post_id → post_author_id (numeric agent_id)` muss aus einer der OASIS-Quellen rekonstruiert werden:

1. **`reddit_simulation.db` / `twitter_simulation.db`** — SQLite-Tables haben `posts(post_id, user_id)`, das löst `post_id → user_id` exakt auf. Sauberster Weg, aber Service braucht DB-Zugriff oder vorab-aufgelöste Lookup-Tabelle.
2. **`reddit_profiles.json` / `twitter_profiles.csv` + `post_author_name` Reverse-Lookup** — Name → agent_id. Zerbrechlich bei Namens-Kollisionen, aber DB-frei.
3. **`CREATE_POST`-Actions vorab indexieren** — jeder `CREATE_POST` schreibt `agent_id` + `action_args.post_id` (zu prüfen). Daraus eine In-Memory-Map `post_id → agent_id` aufbauen, dann LIKE_POST/QUOTE_POST/REPOST/COMMENT auflösen. Kein DB-Zugriff nötig.

Variante 3 ist am einfachsten und passt zur Stateless-Service-API.

Gleiches Problem trifft `LIKE_COMMENT`/`DISLIKE_COMMENT`: dort steht `comment_id`, nicht `comment_author_id`. Brauchen ebenfalls einen Vorab-Index aus `CREATE_COMMENT`-Actions.

### Sekundärbefund: Action-Type-Mismatch

`SEARCH_USER`, `TREND`, `DO_NOTHING`, `SEARCH_POSTS` sind **nicht** in `_DIRECTED_ACTIONS` und werden korrekt ignoriert. `MUTE` und `QUOTE_POST` sind drin — gut. Keine fehlenden Types entdeckt.

`broadcast_only_no_pairwise` (2 Runs) ist semantisch ein Sub-Symptom: kleine Test-Runs mit nur 10 `CREATE_POST`-Actions und sonst nichts. Hier sind die 0er Metriken inhaltlich korrekt, müssen aber im Report mit Status-Flag statt nackten Nullen ausgewiesen werden.

## Konsequenzen für die Slice-Sequenz

Der ursprüngliche Plan unterschätzte den Befund. Reihenfolge wird geupdatet:

| Slice | Vorher | Jetzt |
|---|---|---|
| **S2-pre (NEU)** | nicht im Plan | **Schema-Fix `_extract_target_agent`**: Vorab-Index `post_id → agent_id` und `comment_id → agent_id` aus `CREATE_POST`/`CREATE_COMMENT`-Actions; Resolver in `_iter_interactions` einhängen. Akzeptanz: Diagnose-Skript zeigt für >0 Runs Verdict `metrics_consistent`. |
| **S2a** | „total_agents=0 ↔ Actions vorhanden = Inkonsistenz markieren" | bleibt: Status-Flag `no_pairwise_interactions` für die echten Broadcast-Only-Fälle, plus `snapshot_id`/`calculated_at` |
| **S2b** | Frontend „Metriken nicht verfügbar" | bleibt |

S2-pre ist der echte Werttreiber — danach hat das Polarization-Feature überhaupt erstmal Daten zum Anzeigen. S2a/S2b regelt die Edge-Cases sauber drumherum.

