### Fixed (Hardstop-Check brach den Backend-Job auf main mit Bash-Syntaxfehler — 2026-08-08)

- **`scripts/check-pip-audit-hardstop.sh` endete bei jedem Lauf mit „syntax error in conditional expression" (Exit 2):** `[[ "$TODAY" >= "$HARDCUTOFF" ]]` — den Operator `>=` gibt es in Bash-`[[ ]]` nicht. Ersetzt durch den äquivalenten lexikografischen `<`-Vergleich; Regressionstests führen das Skript jetzt tatsächlich aus (vor/nach/am Cutoff-Tag). Der Defekt blieb unbemerkt, weil frühere main-Läufe schon am Ruff-Step scheiterten, bevor der Hardstop-Step erreicht wurde.
