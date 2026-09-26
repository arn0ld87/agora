### Changed

- Subagent `agora-refactor-worker` (und `-m3`) gehärtet: Basis-Prüfung des Worktrees vor der ersten Änderung, Tests über einen im Briefing genannten Remote-Helper (sonst lokal), keine volle Test-Suite mehr als Sicherheitsnetz, Changelog nur als `changelog.d`-Fragment, Scope-Gate nur auf Anweisung, Regeln für Ops-Shell-Skripte (kein Logging in Command Substitution, Auflösen vor `stop`/`down`, garantierter Wiederanlauf, argv-prüfende Stubs), `maxTurns` 60 und Modell-Alias `sonnet`. (#1675)
