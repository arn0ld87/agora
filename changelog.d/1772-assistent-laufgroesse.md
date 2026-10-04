### Changed

- Simulation: Der Konfigurations-Assistent schlägt standardmäßig 1 Tag und
  24 Runden vor (24 Stunden, 60 Minuten je Runde). Bisher lagen Modell-Default
  und Regel-Fallback bei 72 Stunden, und das Modell durfte bis zu 168 Stunden
  wählen (beobachtet: 4 Tage und 90 Runden); der Tokenverbrauch wächst mit der
  Rundenzahl (Standardlauf `sim_cc6067a70603`: 24 Runden, 52 Agenten, 35,7 Mio.
  Eingabe-Tokens). Der Prompt nennt 24 Stunden als Standard und erlaubt eine
  längere Dauer nur bei ausdrücklichem Wunsch in der Simulationsanforderung.
  Zusätzlich klemmt die Erzeugung die Antwort des Modells deterministisch auf die
  neue Obergrenze `AGORA_SIM_MAX_HOURS` (Standard 24, gültig 1 bis 168, sonst
  Rückfall auf 24 mit Warnung): längere Dauer wird gesenkt, kürzere Runden, die
  mehr Runden als die Obergrenze ergäben, werden auf 60 Minuten angehoben. Jede
  Klemme steht als Warnung im Log und als Hinweis im `generation_reasoning`.
  **Verhaltenswechsel:** Neu erzeugte Konfigurationen sind kürzer; bereits
  gespeicherte `simulation_config.json` bleiben unverändert. Längere Läufe
  verlangt man beim Start ausdrücklich (`simulation_days`/`max_rounds`) oder über
  eine höhere `AGORA_SIM_MAX_HOURS` mit neuer Vorbereitung. Das LLM-Schema
  akzeptiert jetzt auch Dauern unter 24 Stunden.
