### Behoben

- **LLM:** Routen über OpenRouter senden `reasoning_effort` (Standard `none`) im `LLMClient` und in der Simulation. Reasoning-Modelle wie `deepseek/deepseek-v4.1-flash` dachten bisher bei jedem Aufruf mit Anbieter-Default, was Ausgabe-Tokens, Kosten und Laufzeit vervielfachte.
