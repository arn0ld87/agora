# S4a — Evidence-Binder Service · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** S4a

## Implementierung

Neuer Service `backend/app/services/evidence_binder.py`:

- `bind_evidence_to_claim(claim_text, candidates, embed, threshold=0.65, top_k=5)` — Cosine-Similarity zwischen Claim und Kandidat-Text (snippet/value/raw.content), filtert Items unter Threshold, sortiert nach Score, kürzt auf top_k.
- `_candidate_text(item)` extrahiert die textuell aussagekräftigsten Felder.
- `_cosine(a, b)` ohne numpy (DOT/Norm).
- Embedder per DI als `Callable[[str], Sequence[float]]` — Tests verwenden deterministischen Vocab-Fake, Production reicht `EmbeddingService.embed` durch.

## Tests (5 neu, alle grün)

- `test_returns_empty_for_no_claim_or_candidates`
- `test_filters_below_threshold_and_sorts_descending`
- `test_top_k_truncates`
- `test_uses_raw_content_when_snippet_missing`
- `test_does_not_mutate_input_candidates`

508 Backend-Tests grün, 40 Frontend, Build clean.

## Folgeaktion

S4b verdrahtet den Binder im `report_agent._build_claims_for_section` und führt `schema_version: 2` ein.
