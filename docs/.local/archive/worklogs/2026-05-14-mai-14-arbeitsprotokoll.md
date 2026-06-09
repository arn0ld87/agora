# MAI-14 — Confidence-Contradiction-Penalty: Arbeitsprotokoll

Datum: 2026-05-14
Branch: `feat/mai-14-contradiction-penalty`
Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-14/`

## Ziel

`confidence_calculator.py` erkennt widersprüchliche Sentiment-Vektoren in
Evidence-Items und zieht automatisch 0.2 vom Confidence-Score ab.

## Analyse-Ergebnis (Pre-Flight)

- `sentiment_score` fehlte in `EvidenceItemModel` (Zeile 101 in `report_contract.py`).
- `detect_contradiction_penalty` in `evidence_binder.py` prüft bereits Stance-Flags
  und Boolean-Felder — MAI-14 ergänzt die Sentiment-Score-basierte Heuristik
  orthogonal dazu in `confidence_calculator.py`.
- Signatur `compute_confidence() -> (score, label)` wird an 10+ Call-Sites als
  2-Tupel entpackt — keine Breaking-Change-Signaturänderung möglich.
  Lösung: neue Funktion `compute_claim_confidence()` mit `(score, label, applied_penalties)`.

## Implementierte Änderungen

### 1. `backend/app/contracts/report_contract.py`

`EvidenceItemModel` um `sentiment_score: Optional[float] = Field(default=None, ge=-1.0, le=1.0)`
ergänzt (nach `match_score`, vor `source_kind`). Kein Touch an `ReportClaimModel` (MAI-02-Scope).

### 2. `backend/app/services/confidence_calculator.py`

- Konstanten: `_CONTRADICTION_PENALTY_AMOUNT = 0.2`, `_CONTRADICTION_STD_THRESHOLD = 0.6`,
  `_CONTRADICTION_RANGE_LOW = -0.3`, `_CONTRADICTION_RANGE_HIGH = +0.3`.
- `_has_contradiction(sentiment_scores: List[float]) -> bool`:
  Populationsstandardabweichung > 0.6 ODER (min < -0.3 AND max > +0.3).
- `_extract_sentiment_scores(evidence: List[Dict]) -> List[float]`:
  Filtert valide `sentiment_score`-Werte aus Evidence-Dicts.
- `compute_confidence()` (bestehend): Ruft `_has_contradiction` intern auf und addiert
  den Sentiment-Penalty (0.2) zum extern übergebenen `contradiction_penalty`.
  Signatur unverändert: `(score, label)`.
- `compute_claim_confidence()` (neu): Wrapper mit `(score, label, applied_penalties)`.
  Trägt `"contradiction_penalty"` in `applied_penalties` ein wenn angewendet.

### 3. `backend/tests/test_confidence_calculator.py`

10 neue Tests (4 für `_has_contradiction`, 5 für `compute_claim_confidence`, 1 Integration):

- `test_has_contradiction_stddev` — std > 0.6 erkannt
- `test_has_contradiction_range` — min<-0.3 + max>+0.3 erkannt
- `test_has_contradiction_aligned` — konsistente Sentiments kein Widerspruch
- `test_has_contradiction_single` — 1 Score → False
- `test_contradiction_penalty_via_stddev` — compute_claim_confidence Penalty aktiv
- `test_contradiction_penalty_via_range` — compute_claim_confidence Penalty aktiv
- `test_no_penalty_when_aligned` — keine Penalty bei konsistenten Sentiments
- `test_single_evidence_no_contradiction` — 1 Item → keine Penalty
- `test_missing_sentiment_ignored` — Items ohne sentiment_score übersprungen
- `test_compute_confidence_auto_sentiment_penalty` — compute_confidence zieht Penalty ab

## Test-Ergebnisse

```
tests/test_confidence_calculator.py: 17 passed
Gesamt (ohne pre-existing API-key-Tests): 1969 passed, 9 skipped
```

Die pre-existing Fehler in `test_graph_endpoints.py` und `test_report_modes.py`
sind `LLM_API_KEY not configured`-Fehler ohne MAI-14-Bezug — in CI mit gesetztem
Key grün.

## Schema-Drift

`EvidenceItemModel.sentiment_score` ist neu → `evidence-map.schema.json` und
`report-contract.schema.json` bekamen je 15 neue Zeilen (Property-Definition +
`nullable`-Flag). Dump reproduzierbar: `--check` gibt Exit 0.

### Snapshot-Diff-Erläuterung

Kein Eval-Snapshot-Update notwendig. Die bestehenden Fixture-Files in
`tests/eval/snapshots/` tragen keine `sentiment_score`-Felder in ihren
Evidence-Items, daher schlägt `_has_contradiction` bei keiner bestehenden
Fixture an. Alle 28 Eval-Tests blieben grün ohne `--snapshot-update`.

## Lint / Types

```
ruff check app/ tests/: All checks passed!
mypy app: Success: no issues found in 151 source files
```

## Gaps / Offene Punkte

- MAI-03 (Hypothesis-Verdrahtung): Wenn MAI-03 widersprüchliche Claims in
  Hypotheses routet und dabei `sentiment_score`-Felder setzt, greift der
  Contradiction-Penalty automatisch — keine weitere Anpassung nötig.
- `applied_penalties` in `compute_claim_confidence` wird aktuell nicht in den
  `audit_trail` des Report-Agents geschrieben. `detect_contradiction_penalty`
  aus `evidence_binder.py` übernimmt das für den Stance-basierten Pfad bereits.
  Sentiment-basierter Pfad könnte in einem Folge-Slice angebunden werden.
