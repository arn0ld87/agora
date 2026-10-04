### Fixed

- Simulation: Das Agentengedächtnis wächst nicht mehr mit jedem Feed
  ([#1772](https://github.com/arn0ld87/agora/issues/1772)). OASIS schreibt bei
  jeder Aktivierung den kompletten Feed als USER-Nachricht ins CAMEL-Gedächtnis
  des Agenten; Agora hob das Token-Limit nur an, nie ab. Im Lauf
  `sim_cc6067a70603` wuchs der Prompt je Agentenschritt deshalb von median 3.800
  auf 91.900 Eingabe-Tokens (Maximum 220.000). Nach jeder Runde ersetzt
  `backend/scripts/agent_memory.py` jetzt die Feeds älterer Aktivierungen durch
  einen kurzen Platzhalter und behält die Feeds der letzten vier Aktivierungen
  (`AGORA_SIM_MEMORY_KEEP_FEEDS`); System-Nachricht und eigene Aktionen
  (Tool-Call samt Tool-Ergebnis, Textantwort) bleiben unverändert. Zusätzlich
  gilt eine Obergrenze für das Gedächtnis-Token-Limit
  (`AGORA_SIM_MEMORY_TOKEN_CAP`, Default 32.000, `0` = aus), auch wenn CAMEL
  für ein Modell auf `999_999_999` zurückfällt. Mit
  `AGORA_SIM_MEMORY_PRUNE_FEEDS=false` und `AGORA_SIM_MEMORY_TOKEN_CAP=0` gilt
  der alte Zustand. Agenten kennen ältere Feeds nicht mehr, nur ihre eigenen
  früheren Aktionen. Siehe `docs/runbooks/upgrade.md`.
