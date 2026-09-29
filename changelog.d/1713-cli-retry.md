### Fixed

- `CodexCliModel`/`ClaudeCliModel` (OASIS-Subprozess, `transport="cli"`) starteten pro
  Simulationsrunde beliebig viele `codex exec`/`claude -p`-Subprozesse gleichzeitig — CPU-
  Kontention unter Last machte einzelne Aufrufe langsamer und ließ sie eher in den Timeout
  laufen, obwohl kein echter Konfigurationsfehler vorlag. Eine prozessweite
  `asyncio.Semaphore` begrenzt jetzt die Concurrency (`AGORA_CLI_MAX_CONCURRENCY`, Default 4),
  und ein transienter Fehlschlag (Timeout, Startfehler) wird einmal mit festem Backoff
  wiederholt (`AGORA_CLI_RETRY_ATTEMPTS`/`AGORA_CLI_RETRY_BACKOFF_SECONDS`, Default 1 Retry/2s),
  bevor der Fehler wie bisher als `RuntimeError` an OASIS geht. `BudgetExceededError` wird
  bewusst nie retried — die Retry-Schleife fängt ausschließlich die CLI-eigene
  `*CliUnavailableError`.
