# Tool-Pipeline

> Laden bei grossflaechiger Codebase-Analyse. Reihenfolge bestimmt Token-Effizienz.

## Analyse-Reihenfolge

1. **code-review-graph** — Struktur, Impact, Abhaengigkeiten
2. **ctx_batch_execute** — grosse Read-only-Abfragen parallel
3. **ctx_execute / ctx_execute_file** — Daten filtern/aggregieren ohne Kontext-Verbrauch
4. **Direkte Dateiwerkzeuge** — nur fuer gezielte Bearbeitung und Verifikation

Secrets, Tokens, Browserprofile und private Host-Dateien gehoeren nie ins Repository.
