### Fixed

- Chat-Routing, das bei Provider `anthropic` landet (Legacy-Profil, ausgewählte ProviderConnection oder eine bereits gerouteten Stage), scheitert jetzt laut mit einer klaren Fehlermeldung statt still über `custom_openai` an `https://api.anthropic.com/chat/completions` zu senden (403/404 zur Laufzeit). Es gibt keinen nativen Anthropic-Chat-Transport — Claude läuft über die Bedrock-Connection (#1282). Modell-Discovery für bestehende Anthropic-Connections bleibt unverändert nutzbar (#1284).
