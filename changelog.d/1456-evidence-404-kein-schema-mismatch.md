### Fixed

Ein noch nicht vorhandener Evidence-Endpunkt (HTTP 404, solange die Evidenzkarte serverseitig noch nicht geschrieben ist) wurde im Bericht faelschlich als "Schema-Mismatch" gemeldet, obwohl kein Zod-Fehler vorlag. `loadEvidence()` in `Step4Report.vue` unterscheidet jetzt anhand des Fehlertyps: eine geworfene `ApiError` (HTTP-/Transport-Ebene) fuehrt weiterhin in den bestehenden Retry mit Backoff und Budget, ein echter Zod-Parse-Fehler bleibt ein Schema-Mismatch.

Nachbesserung (Codex-Review PR #1456): Innerhalb der `ApiError`-Faelle ist HTTP 422 mit Code `contract_violation` (die persistierte Evidence-Map ist auch nach Migration nicht vertragskonform, siehe `backend/app/api/report.py`) kein transienter Zustand wie 404. Ein Retry wuerde denselben Vertragsverstoss zehn Minuten lang verschweigen — 422 wird deshalb wie ein Zod-Fehler behandelt: sichtbar als Schema-Mismatch, ohne Retry.
