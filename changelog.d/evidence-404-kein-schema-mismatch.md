### Fixed

Ein noch nicht vorhandener Evidence-Endpunkt (HTTP 404, solange die Evidenzkarte serverseitig noch nicht geschrieben ist) wurde im Bericht faelschlich als "Schema-Mismatch" gemeldet, obwohl kein Zod-Fehler vorlag. `loadEvidence()` in `Step4Report.vue` unterscheidet jetzt anhand des Fehlertyps: eine geworfene `ApiError` (HTTP-/Transport-Ebene) fuehrt weiterhin in den bestehenden Retry mit Backoff und Budget, ein echter Zod-Parse-Fehler bleibt ein Schema-Mismatch.
