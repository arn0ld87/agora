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

Der Registry-Lookup und die Key-Aufloesung der Active-Config liegen dafuer jetzt
als Modul-Helfer neben `LLMClient` statt inline im Konstruktor — sonst haette der
zweite Lookup `__init__` ueber die Radon-Obergrenze aus `radon-allowlist.txt`
getrieben (gemessen 38, erlaubt 34; jetzt 31).
