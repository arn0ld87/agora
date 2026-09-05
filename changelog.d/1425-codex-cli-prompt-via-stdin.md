### Fixed

- Simulationsrunden über die Codex-CLI reichen den Prompt jetzt über stdin
  statt als Kommandozeilenargument. Ein Runden-Prompt trägt Persona, Historie
  und Werkzeugschemata und riss als einzelnes argv-Element Linux'
  `MAX_ARG_STRLEN` von 128 KiB; auf armserver starben dadurch 12 Agenten-Turns
  einer Runde mit `OSError: [Errno 7] Argument list too long`. (#1425)
