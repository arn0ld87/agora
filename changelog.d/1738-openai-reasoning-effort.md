### Fixed

- `reasoning_effort` der Route erreicht OpenAI-Reasoning-Modelle jetzt wirklich
  (#1738). Bisher sendete Agora den Wert nie; `gpt-6.1-sol` u. a. haben
  serverseitig einen Default ungleich `none` und OpenAI antwortete auf jeden
  Tool-Call der Section-ReAct mit 400 „Function tools with reasoning_effort are
  not supported". Jetzt setzen der Tools-Pfad und `chat()`/`chat_json()` ein
  top-level `reasoning_effort` (Route-Wert, bei `force_no_thinking` `none`),
  aber nur wenn die bestehende Provider-Detection `openai` liefert und das
  Modell zur Reasoning-Familie gehört (`gpt-5`…`gpt-9`, `o1`/`o3`/`o4`).
  Ollama, OpenRouter, openai-kompatible Proxies und Nicht-Reasoning-Modelle
  (`gpt-4.1`, `gpt-4o`) bekommen den Parameter nicht. Lehnt ein älteres
  Reasoning-Modell den Wert `none` ab, wiederholt ein neuer Quirk den Request
  einmal ohne `reasoning_effort` (eigener Budget-Attempt); der Tools-400 matcht
  den Erkenner bewusst nicht.
- Report-Lauf: Ein nicht-transienter Provider-400 (z. B. dieser Tools-400) in einer
  Section wiederholte sich bisher für alle weiteren Sections. Jetzt setzen die
  restlichen Sections keinen LLM-Call mehr ab und enden als sichtbarer Fallback;
  der Bericht bleibt `INCOMPLETE`, `report.error` nennt die Ursache. 408/429/5xx,
  Timeouts und Prompt-spezifische 400er (Context-Length, Content-Filter) laufen
  unverändert weiter, `BudgetExceededError` wird weiter hart durchgereicht. Der
  Fallback-Text nennt statt des pauschalen „ungültiger API-Key, Rate-Limit,
  Modell nicht verfügbar" die Fehlerklasse und eine gekürzte, von Secrets
  bereinigte Providermeldung.
