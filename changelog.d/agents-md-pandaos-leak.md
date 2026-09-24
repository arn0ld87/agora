### Security (AGENTS.md: lokaler PandaOS-Block entfernt — 2026-09-21)

- **`AGENTS.md` enthält wieder nur die Repo-Regeln:** PR #1539 hat versehentlich
  einen 531 Zeilen langen Block committet, den PandaOS lokal zwischen
  `<!-- >>> pandaos-managed … -->`-Markern pflegt. Er bestand aus
  Codex-Session-Anweisungen und maschinenspezifischer Konfiguration
  (interne Hostnamen, Ports und Pfade) und war damit im öffentlichen Repo
  sichtbar. Die Datei ist wieder byte-identisch zum Stand vor #1539; jeder
  Agent, der `AGENTS.md` liest oder per `@AGENTS.md` importiert, lädt damit
  rund 10.000 Tokens weniger. Die Git-Historie enthält den Block weiterhin.
- **Neues Leak-Gate:** `scripts/check_pandaos_managed_leak.sh` lehnt den Marker in
  versionierten Dateien ab. Es läuft in jedem Scope von
  `scripts/pre-push-gate.sh` und im Backend PR smoke gate. Ursache und Umgang mit
  dem lokalen `skip-worktree`-Bit stehen in `docs/runbooks/pre-push-gate.md`
  (Gate 14).
