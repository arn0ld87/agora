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
