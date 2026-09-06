### Fixed

- Die Init-Zeile des `LLMClient` benennt jetzt zusaetzlich `provider_type`. Bisher
  loggten Aufrufer, die API-Key und Basis-URL selbst aufloesen und direkt
  durchreichen (etwa die Simulations-Konfigurationsgenerierung), ein
  `provider_id=unknown base_url=None` — bei `codex_cli` beides sachlich richtig,
  im Log aber nicht von einem fehlkonfigurierten Client zu unterscheiden. Die
  Provider-Erkennung selbst bleibt unveraendert; `provider_type` stammt aus
  derselben Aufloesung, aus der sich auch der Transport ergibt.
  Der Typ wird auch dann aufgeloest, wenn der Aufrufer den Schluessel
  selbst mitbringt und die aktive Konfiguration nur Modell oder Basis-URL
  beisteuert (Review-Nachbesserung).
