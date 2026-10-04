### Changed

- Simulation: Die Zahl gleichzeitiger Modellaufrufe je Plattform ist nicht mehr
  fest 30, sondern über `AGORA_SIM_MAX_CONCURRENCY` einstellbar (Standard 8,
  gültig 1 bis 256, ungültige Werte fallen mit Warnung auf den Standard). Twitter
  und Reddit laufen parallel, die Gesamtlast ist also bis zu doppelt so hoch.
  Anlass ist der Lauf `sim_cc6067a70603` (#1772): bei 30 + 30 gleichzeitigen
  Aufrufen lieferte der Anbieter für 2.225 von 3.284 Aufrufen `RateLimitError`
  (68 %); ein Agentenschritt, dessen Wiederholungen erschöpft sind, ging still
  verloren. Die Laufzeit pro Runde kann dadurch steigen, dafür kommen die
  Agentenschritte an.
- Neu: `AGORA_SIM_INPUT_TOKENS_PER_MINUTE` (Standard `0` = aus) drosselt die
  Simulations-Aufrufe auf ein gleitendes 60-Sekunden-Fenster über die gemessenen
  Eingabe-Tokens. Der Limiter hängt im Budget-Proxy (`SubprocessBudgetGuard`) und
  gilt damit für beide Plattformen im Parallel-Runner gemeinsam; er wartet nur
  per `await` und prüft ein hartes Budget vor dem Warten. Aktive Parallelität und
  Limit stehen einmal pro Lauf im Log.
- Simulation: Die Aktivitäts-Untergrenze (Anteil der Agenten, die je Simulationsstunde
  mindestens aktiviert werden) ist konfigurierbar:
  `AGORA_SIM_AGENTS_PER_HOUR_MIN_RATIO` und `AGORA_SIM_AGENTS_PER_HOUR_MAX_RATIO`
  (auch in den Einstellungen unter OASIS). Der Standard sinkt von 0,4/0,7 auf 0,25/0,5.
  **Verhaltenswechsel:** Neu erzeugte Simulationskonfigurationen aktivieren je Runde
  weniger Agenten, es entstehen weniger Beiträge und weniger Modellaufrufe; das
  Liveness-Ziel L2 (aktive Agenten je Runde ≥ 40 %) liegt im Mittel bei rund 37 %
  und wird erst mit 0,4/0,7 wieder erreicht. Gültig ist `0 < min ≤ max ≤ 1`, sonst
  Rückfall auf den Standard mit Warnung. Bereits gespeicherte
  `simulation_config.json` bleiben unverändert.
