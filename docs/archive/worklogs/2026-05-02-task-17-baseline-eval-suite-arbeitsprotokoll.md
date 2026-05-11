# Sub-Slice 17 — Baseline-Eval-Suite + Snapshots + Voice-Lint hart

Datum: 2026-05-02
Branch: feat/layer-5-task-17-baseline-eval-suite
Issue: Closes #174
Layer: 5 (Eval/Baseline)

## Was wurde gemacht

### check_evidence_quality.py — zwei neue Metriken

`evaluate()` berechnet nun zusaetzlich:

- `dedup_rate`: Anteil der Sections, die im `audit_trail` eines ihrer Claims
  einen `section_dedup`-Marker tragen (aus Sub-Slice 13, Cosine-Dedup).
- `concentration_index`: max(count_pro_source) / total im `global_evidence`-Pool.
  Wert nahe 1.0 signalisiert Single-Source-Dominanz.

Beide Metriken sind Beobachtungs-Keys, kein Hard-Gate. Die Print-Zeile in
`main()` gibt beide zusaetzlich aus.

### Fixtures (tests/eval/fixtures/)

Drei valide `EvidenceMapModel`-Fixtures mit `schema_version: 2`:

- `clean_small.json` — 3 Sections, 6 Claims, 100 % Coverage + Support, kein Dedup.
- `medium_with_dedup.json` — 4 Sections, 8 Claims, 1 Section mit section_dedup-Marker
  (Section 2, cosine=0.93), gemischte Confidence-Labels.
- `orphan_heavy.json` — 2 Sections, 8 Claims, 4 orphane Claims (leere evidence[]),
  global_evidence aus 2 Sources (neo4j-graph dominiert, concentration_index=0.8).

### expected_metrics.json

Snapshot-Werte deterministisch per einmaligem Ausfuehren von `evaluate()` berechnet
und gerundet (3 Dezimalstellen). Drift -> `test_metrics_match_snapshot` failt mit
Schluessel-Diff.

### test_eval_baselines.py

7 Test-Cases (3x Pydantic-Validation + 3x Snapshot-Metriken + 1x Key-Check):
- `test_fixture_validates_against_pydantic` — alle 3 Fixtures muessen EvidenceMapModel.model_validate bestehen.
- `test_metrics_match_snapshot` — Metrik-Werte gegen expected_metrics.json pinnen.
- `test_evaluate_output_keys` — alle 6 Pflicht-Keys vorhanden.

### Voice-Lint CI hart

`.github/workflows/contract-gates.yml` Job `voice-lint`: `--soft` entfernt.
Layer 2 (Sub-Slice 09+11) hat alle verbotenen Phrasen aus den Produktions-Dateien
entfernt — der Check laeuft sauber durch.

## Verifikation

- `pytest tests/eval/ -x -v` → 7 passed
- `check_evidence_quality.py --fixtures tests/eval/fixtures --soft` → dedup_rate= + concentration_index= im Output
- `check_voice.py` (ohne --soft) → Exit 0, 0 Treffer
- `pytest -x -q` Volltest → gruen
- `ruff check app/ tests/ scripts/` → clean
- `git diff --exit-code schemas/` → leer (kein Pydantic geaendert)
