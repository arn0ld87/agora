# S3b — Claim-Atomisierung · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** S3b

## Implementierung

`ReportAgent` bekommt zwei neue Helper:

- `_atomize_claim_chunk(chunk)` — splittet Mehrsatz-Chunks in atomare Sätze. Regex mit Lookbehind `[a-zäöüß][.!?]\s+[A-ZÄÖÜ]`, damit Datums-/Zahlen-Punkte (`am 22. Mai`) und Initialen nicht als Satzende gelten.
- `_is_atomic_claim(text)` — verlangt mindestens 5 Wörter und entweder Satzende-Zeichen oder ein finite-Verb-Hint (`ist`, `wird`, `soll`, `beschloss`, `kritisiert`, …).

`_build_claims_for_section` wendet S3a-Strukturfilter und S3b-Atom-Filter sequenziell an. Fallback: wenn der Atom-Filter alle Sätze killt, behält der Chunk einen Eintrag, damit legitime Single-Sentence-Sections nicht vollständig verschwinden.

## Tests (3 neu, 1 verschärft)

- `test_atomize_claim_chunk_splits_multisentence`
- `test_is_atomic_claim_filters_short_and_unverbose`
- `test_build_claims_for_section_drops_headers` (verschärft, jetzt 2 Claims aus 4 chunks)

503 Backend-Tests grün.
