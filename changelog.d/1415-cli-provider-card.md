### Fixed

- `LlmProvidersView.vue` rendert CLI-/Session-Provider (`codex_cli`,
  `claude_cli`) nicht länger wie HTTP-Provider: das API-Key-Feld und das
  Base-URL-Feld (Platzhalter `https://api.example.com/v1`) waren dort
  irreführend, weil `transport="cli"` weder einen HTTP-Endpunkt noch — bei
  `auth_mode="session"` (`codex_cli`) — einen verwalteten Secret kennt.
  `GET /api/llm/providers` liefert `transport`/`auth_mode` nicht mit; die
  View leitet beides jetzt clientseitig aus der bereits gespiegelten
  Registry-Matrix ab (statisch je `provider_kind`, identisch zu
  `supports_models_endpoint`) und übernimmt den tatsächlichen Wert aus dem
  `ProviderConnection`-Record, sobald eine Connection existiert. `codex_cli`
  zeigt weder Key- noch Base-URL-Feld, sondern einen Hinweis auf die lokale
  `codex login`-Session. `claude_cli` behält das Key-Feld (Langzeit-Token aus
  `claude setup-token`), verliert aber das Base-URL-Feld. Nicht unterstützte
  Bridges (Copilot, OpenCode Go) sind unverändert. Backend unangetastet.
