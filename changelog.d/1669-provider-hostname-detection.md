### Fixed

- **`app/llm/providers/registry.py` (`detect_provider`, beide Modi): Hostname-/Port-Vergleich statt URL-Substring (CodeQL #367/#389/#390, Issue #1669).**
  `_detect_http` prüfte Base-URLs bisher per roher Substring-Suche
  (`"openai.com" in base`, `"googleapis.com" in base or "generativelanguage" in base`,
  `"11434" in base`). Ein Drittanbieter-Host wie `https://api.openai.com.attacker.test`
  oder eine im Pfad/Query eingebettete Zeichenfolge (`https://evil.test/?u=openai.com`)
  matchte fälschlich und hätte einen fremden Endpoint als den echten Provider
  klassifiziert — dieselbe Fehlerklasse, die der MiniMax-/Bedrock-/Anthropic-Zweig schon
  über CodeQL #750 gefixt hatte. Der Port-Check `"11434" in base` traf zudem auch
  `:114340` (dokumentierte, jetzt entfernte Eigenheit). `_detect_oasis` hatte dieselben
  Substring-Muster für `generativelanguage.googleapis.com` und `ollama.com`. Beide
  Zweige nutzen jetzt den neuen Helper `_parse_host_port` (toleriert schemalose
  Base-URLs wie `api.openai.com/v1` oder `localhost:11434`) und vergleichen Hostname
  exakt bzw. per Suffix (`host == "openai.com" or host.endswith(".openai.com")`) sowie
  den geparsten Port statt eines Substrings. Downstream betroffen:
  `app/services/runtime_run_config.py::_detect_default_provider_id` (delegiert an die
  SSoT) klassifiziert Look-alike-Hosts wie `evil-openai.com` jetzt korrekt als
  `openai_compatible`-Fallback statt fälschlich als `openai`.
- **ReDoS-Cap für `_is_ollama_cloud_tag`** (CodeQL `py/polynomial-redos`, Issue #1669):
  `_OLLAMA_CLOUD_SIZE_TAG_RE` (`\d+[a-z]*-cloud`, per `fullmatch` auf
  user-kontrollierten Modellnamen) nutzt jetzt possessive Quantifiers
  (`\d++[a-z]*+-cloud`) plus einen Längen-Cap (64 Zeichen) auf den Tag-Teil vor dem
  Regex-Aufruf. Die dokumentierten Beispiele (`20b-cloud`, `120b-cloud`, `1t-cloud`,
  `custom:experimental-cloud`) behalten ihr Ergebnis unverändert.
