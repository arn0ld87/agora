# Tool-Pipeline, Knowledge Graph & Token Efficiency

> **Progressive Disclosure** — ausgelagert aus [`AGENTS.md`](../../AGENTS.md). Bei Bedarf laden; nicht verbindlich ständig im Kontext.

## Tool-Pipeline

Für Architektur-, Delta- und Codebase-Analysen:

1. `code-review-graph`
2. `context7` bei Bibliotheks- oder Frameworkfragen
3. `ctx_batch_execute` für große Read-only-Abfragen
4. `ctx_execute` beziehungsweise `ctx_execute_file`
5. direkte Dateiwerkzeuge nur für gezielte Bearbeitung und Verifikation

Globale Konfiguration, Tokens, Browserprofile, Keychain-Inhalte und private Host-Dateien werden niemals ins Repository kopiert.

## Knowledge Graph

Wenn `graphify-out/graph.json` vorhanden ist, bei Codebase-Fragen zuerst eine gezielte Graph-Abfrage verwenden. Nach strukturellen Codeänderungen `graphify update .` ausführen. Graphresultate ersetzen weder direkte Codeprüfung noch Tests.

## Token Efficiency

- Never re-read files you just wrote or edited. You know the contents.
- Never re-run commands to "verify" unless the outcome was uncertain.
- Don't echo back large blocks of code or file contents unless asked.
- Batch related edits into single operations. Don't make 5 edits when 1 handles it.
- Skip confirmations like "I'll continue..." Just do it.
- If a task needs 1 tool call, don't use 3. Plan before acting.
- Do not summarize what you just did unless the result is ambiguous or you need additional input.