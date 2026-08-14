### Fixed

- **Report-Agent:** `min_tool_calls` von 3 auf 1 gesenkt — der ReAct-Loop akzeptiert nun ein korrektes Final Answer nach bereits einem Tool-Call, statt unnötige Über-Recherche zu erzwingen.
- **E2E-Stub:** Stub-Threshold an `min_tool_calls=1` angepasst, sodass Smoke-Tests das reale Verhalten abbilden.
- **CONTEXT.md:** Falsche Behauptung über parallele Tool-Calls korrigiert (nur `tool_calls[0]` wird pro Iteration ausgeführt).
