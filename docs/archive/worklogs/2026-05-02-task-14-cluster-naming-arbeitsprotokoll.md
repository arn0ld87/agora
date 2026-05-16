# Task 14 — Cluster-Naming deterministisch (Sub-Slice 14)

**Datum:** 2026-05-02
**Branch:** feat/layer-3-task-14-cluster-naming-deterministic
**Issue:** Closes #171

## Was wurde geaendert

### `backend/app/services/network_analytics.py`

- `import re` ergaenzt (fehlte bisher).
- `_CLUSTER_LABEL_STOPWORDS: frozenset[str]` — Modul-Konstante mit deutschen und englischen
  Function-Words plus Persona-Generator-Floskeln.
- `_derive_cluster_label(member_ids, actions, stopwords, cluster_id)` — neue freie Funktion.
  TF-Top-3 aus den Text-Feldern (`post_content`, `comment_content`, `content`, `text`) der
  Member-Agents. Sortier-Key `(count desc, alpha asc)` fuer stabilen Tie-Break. Fallback
  `cluster-{id}` wenn keine verwertbaren Tokens vorhanden.
- `ClusterDef` — neues Feld `label: str = ""` (Default leer fuer Backwards-Compat). `to_dict()`
  exponiert das Feld.
- `_analyse(interactions, action_dicts=None)` — erweiterter Parameter; Labels werden nach
  Louvain-Community-Bau gesetzt.
- `compute_metrics(...)` — ruft `_analyse(interactions, actions)` auf.
- `__all__` um `_CLUSTER_LABEL_STOPWORDS` und `_derive_cluster_label` erweitert.

### `backend/app/api/simulation_metrics.py`

- CSV-Export `view=clusters`: neue `label`-Spalte zwischen `size` und `agent_ids`.

## Tests

- `backend/tests/services/test_cluster_naming.py` (neu) — 9 Unit-Tests fuer `_derive_cluster_label`:
  Fallback, Frequenz-Ranking, Tie-Break, Stopword-Filter, Determinismus, Token-Mindestlaenge,
  Feld-Inspektion, Stopwords-Set-Inhalt.
- `backend/tests/test_network_analytics.py` — 2 neue Integration-Tests:
  `test_cluster_label_set_when_post_content_present`, `test_cluster_label_in_to_dict`.
- `backend/tests/test_simulation_metrics_export.py` — bestehender `test_export_clusters_csv`
  auf neue Header-Reihenfolge `["cluster_id", "size", "label", "agent_ids"]` angepasst.

## Ergebnis

- 1244 passed, 9 skipped (davon 7 docker-compose + 2 Redis-Integration).
- `ruff check app/ tests/` — sauber.
- `git diff schemas/` — leer (keine Pydantic-Modelle angefasst).
