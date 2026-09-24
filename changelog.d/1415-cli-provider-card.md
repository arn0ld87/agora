### Fixed

- `LlmProvidersView.vue` rendert CLI-/Session-Provider (`codex_cli`,
  `claude_cli`) nicht länger wie HTTP-Provider: das API-Key-Feld und das
  Base-URL-Feld (Platzhalter `https://api.example.com/v1`) waren dort
  irreführend, weil `transport="cli"` weder einen HTTP-Endpunkt noch — bei
  `auth_mode="session"` (`codex_cli`) — einen verwalteten Secret kennt.
  `ProviderDescriptor` (`GET /api/llm/providers`) trägt dazu jetzt
  `transport`/`auth_mode` aus der Registry-Matrix; eine gespeicherte
  Connection gewinnt. `codex_cli`
  zeigt weder Key- noch Base-URL-Feld, sondern einen Hinweis auf die lokale
  `codex login`-Session. `claude_cli` behält das Key-Feld (Langzeit-Token aus
  `claude setup-token`), verliert aber das Base-URL-Feld. Nicht unterstützte
  Bridges (Copilot, OpenCode Go) sind unverändert.
