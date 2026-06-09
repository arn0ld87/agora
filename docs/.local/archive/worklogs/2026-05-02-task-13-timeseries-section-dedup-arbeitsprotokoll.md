# Arbeitsprotokoll Sub-Slice 13 — Time-Series-Sampling + Section-Dedup

**Datum:** 2026-05-02
**Branch:** feat/layer-3-task-13-timeseries-sampling-section-dedup
**Issue:** Closes #170
**Layer:** 3 (Reader Honesty)

## Was

Zwei strukturelle Reader-Honesty-Luecken im Section-Builder geschlossen:

1. **Burst-Verzerrung (Time-Series-Sampling):** `_collect_simulation_evidence_items`
   zog bisher `action_dicts[:8]` — also die ersten 8 Actions in nativer Sortierung.
   Bei 1000 Posts ein willkuerliches Anfangsfenster. Ersetzt durch
   `_sample_actions_timeseries`: stratified Sample ueber `round_num` (Fallback:
   `created_at`, dann Index-Position), 8 gleichgrosse Bins, aus jedem Bin das
   chronologisch erste Item. Deterministisch. Kein Sampling-Marker bei <=8 Actions
   (kein Verhaltensbruch fuer bestehende Tests).

2. **Section-Duplikate:** `_save_evidence_section` prueft jetzt vor dem Append,
   ob der neue Section-Inhalt fast identisch zu einer bereits gespeicherten Section
   ist. Methode `_section_dedup_check`: Embedder verfuegbar → cosine-Similarity
   (Schwelle 0.92), sonst Jaccard auf normalisierten Tokens (Schwelle 0.85).
   Bei Match: Audit-Trail-Eintrag in `claims[0]["audit_trail"]` mit
   `source="section_dedup"`. Section wird NICHT gedroppt — Frontend entscheidet.

## Warum

Reader Honesty: Simulationsberichte sollen keine verzerrten Zeitfenster-Ausschnitte
oder unmarkierte Duplikat-Sections an den Leser weitergeben. Layer 3 hat diesen Scope
explizit definiert.

## Wie

### Geaenderte Dateien

- `backend/app/services/report_agent.py`
  - Z. 228-270: neuer `@staticmethod _sample_actions_timeseries`
  - Z. 323: `action_dicts[:8]` → `self._sample_actions_timeseries(action_dicts, k=8)`
  - Z. 673-741: neuer `_section_dedup_check` (cosine + Jaccard-Fallback)
  - Z. 762-776: Dedup-Check vor Append in `_save_evidence_section`

### Neue Dateien

- `backend/tests/services/test_report_agent_sampling.py` (6 Tests)
- `backend/tests/services/test_report_agent_section_dedup.py` (5 Tests)

### Nicht geaendert

- Pydantic-Modelle: schemas/ sauber, kein Drift.
- `_build_claims_for_section`: unangetastet.
- Frontend: kein Edit.

## Vorbestehende Repo-Schulden (nicht in diesem Slice behoben)

- `tests/test_ontology_generator.py`: LLM_API_KEY-Setup-Bug, seit mehreren Slices
  ignoriert via `--ignore`.
- `tests/test_report_manager.py`: confidence-label-Pin seit Sub-Slice 08 gedriftet,
  ebenfalls via `--ignore` ausgeklammert.

## Testergebnis

- Neue Tests (sampling + dedup + provenance + contracts): 49 passed
- Volltest (--ignore zwei bekannte Schulden): 992 passed, 9 skipped, 0 failures
- Ruff: clean
- Schema-Drift: keiner
