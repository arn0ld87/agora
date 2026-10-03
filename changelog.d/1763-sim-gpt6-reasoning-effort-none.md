### Fixed (Simulation mit GPT-6-Modellen — 2026-10-03)

- **Simulation setzt `reasoning_effort: "none"` jetzt auch für `gpt-6` und neuer:**
  `supports_reasoning_effort_none()` in `backend/scripts/_sim_common.py` erkannte
  nur `gpt-5.<minor>`. Für `gpt-6-luna` und `gpt-6-sol` fehlte der Parameter in der
  CAMEL-Modell-Config, OpenAI griff auf den serverseitigen Reasoning-Default zurück
  und lehnte jeden Agenten-Call mit Function-Tools auf `/v1/chat/completions` mit
  400 ab ("Function tools with reasoning_effort are not supported"). Die
  Simulation lief dadurch ohne Agenten-Aktionen durch. Die Erkennung deckt jetzt
  `gpt-5` bis `gpt-9` ab; ab Major 6 gilt `"none"` auch ohne Minor-Version, `gpt-5`
  ohne Minor (5.0) bleibt ausgenommen. (#1763)
