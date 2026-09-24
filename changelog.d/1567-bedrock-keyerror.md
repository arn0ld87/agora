### Fixed

- Eine Legacy-Server-Config mit Bedrock-`LLM_BASE_URL` (kein persistiertes `runtime_llm_routing.json`) crashte beim Laden mit `KeyError('bedrock')`, weil `_HTTP_DETECTION_TO_PROVIDER_ID` den seit #1282 erkannten `detect_provider`-Wert `"bedrock"` nicht auf eine Provider-ID abbildete. Gemappt auf die Bedrock-Provider-ID; jeder Rückgabewert von `detect_provider(mode="http")` ist jetzt entweder gemappt oder (wie `anthropic`, #1284) explizit als `ValueError` abgelehnt, kein roher `KeyError` mehr möglich (#1567).
