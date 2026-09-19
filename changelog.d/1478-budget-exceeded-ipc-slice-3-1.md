# Slice 3.1 — BudgetExceededError im ParallelIPCHandler

## Problem

Der `ParallelIPCHandler` (Default-Parallelrunner für Twitter+Reddit) fing
`BudgetExceededError` im generischen `except Exception` statt strukturiert.
Dadurch konnte ein hartes Report-Budget, das während eines Interviews in einer
Plattform erreicht wurde, durch die `success_count`-Aggregation der zweiten
Plattform verschluckt werden — der Run endete `completed` statt
`stopped`/`termination_reason=budget_*`.

Zusätzlich fehlte das `budget_exceeded`-Feld in der IPC-Response, sodass der
Client (`interview_client._reraise_if_budget_exceeded`) den Abbruch nicht als
`BudgetExceededError` re-raisen konnte.

## Lösung

1. **`send_response`** um optionales `budget_exceeded: Dict[dimension, observed, threshold]` ergänzt (kompatibel zu `sim_runtime.ipc.IPCHandler`).

2. **`_interview_single_platform`** fängt `BudgetExceededError` **explizit** vor dem generischen `except` und gibt strukturierten Fehler mit `budget_exceeded`-Dict zurück.

3. **`handle_interview` (beide Plattformen):** Budget-Abbruch wird **vor** der `success_count`-Aggregation erkannt — erster `budget_exceeded` gewinnt, Response trägt strukturiertes Feld, Rückgabe `False`.

4. **`handle_batch_interview`** analog: `BudgetExceededError` explizit gefangen, `budget_exceeded` in Response, `False`.

5. **Client-seitig** (`interview_client._reraise_if_budget_exceeded`) unverändert: liest `response.budget_exceeded` und wirft wieder `BudgetExceededError` — Run endet korrekt `stopped`/`budget_*` (via `mark_budget_abort`).

## Tests

Neue Regressionstests in `tests/scripts/test_run_parallel_ipc_attribution.py`:

- (a) Einzelplattform BudgetExceeded → Response-Feld + `ok=False`
- (b) Gemischter Beide-Plattformen-Fall: Budget hat Vorrang vor `success_count`
- (c) Batch-Interview BudgetExceeded → strukturierte Response
- (d) Batch beide Plattformen: erste Dimension gewinnt
- (e) Client-Re-Raise über den echten Weg: geschriebenes Response-JSON →
  `IPCResponse.from_dict` → `_reraise_if_budget_exceeded` → `BudgetExceededError`.
  Der Test bricht damit auch bei reiner Feldnamen-Drift zwischen Runner und
  Client-Deserialisierung.

## Referenzen

- Vorbild: `scripts/sim_runtime/ipc.py:151-170,241-251`
- Repo-Regel: `BudgetExceededError` wird nie in eine Fallback-Antwort umgewandelt
- Follow-up zu #1478 (Codex P1, Runde 7)