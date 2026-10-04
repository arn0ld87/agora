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
- Neu: `AGORA_SIM_INPUT_TOKENS_PER_MINUTE` (Standard inzwischen `1500000`, `0` = aus; siehe `1772-limiter-default`) drosselt die
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
- Budget: Die Preflight-Schätzung der Simulation (`POST /api/simulation/preflight-estimate`)
  rechnet ohne Verlaufsdaten nicht mehr mit 1.000 bis 5.000 Tokens je Aufruf, sondern
  mit einem Messwertmodell: der Kontext je Agentenschritt wächst mit der Runde, solange
  das Agenten-Gedächtnis nicht begrenzt ist (Kalibrierung am Lauf `sim_cc6067a70603`,
  Mittel 33.700 Eingabe-Tokens je Aufruf). Der Referenzlauf (52 Agenten, 24 Runden, zwei
  Plattformen) wird mit rund 31 bis 100 Mio. Tokens statt rund 6 Mio. angezeigt. Neu:
  optionaler Body-Parameter `platform` (`parallel` Standard, `twitter`, `reddit`), die
  Antwort nennt als Annahme, dass der Budget-Zähler nur erfolgreiche Aufrufe zählt, und
  warnt, wenn die untere Schätzung über dem Standard-Tokendeckel liegt.
- Budget: Eine Simulation ohne Nutzerbudget bekommt einen **harten Standard-Tokendeckel**
  von 20 Mio. Tokens (`AGORA_SIM_DEFAULT_MAX_TOKENS`, `0` = abgeschaltet, auch in den
  Einstellungen unter OASIS). **Verhaltenswechsel:** Große Läufe ohne begrenztes Gedächtnis
  (wie der Referenzlauf mit rund 36 Mio. Tokens) enden jetzt mit
  `termination_reason=budget_tokens`, geprüft wird an den Rundengrenzen. Ein vom Nutzer
  gesetztes Budget gewinnt und wird nicht um einen Tokendeckel ergänzt; Replay, Neustart und
  Branch erben das Budget des Ursprungslaufs und bekommen keinen nachträglichen Deckel.
- Budget: Gecachte Eingabe-Tokens werden erfasst. Der Subprozess-Budget-Guard liest
  `usage.prompt_tokens_details.cached_tokens` OpenAI-kompatibler Antworten und schreibt sie als
  optionales Feld `cached_input_tokens` in `llm_call_events.jsonl`; `UsageMetrics` (Usage-Summary,
  Run-Detail, Runs-Liste, Schemas und Zod-Spiegel) summiert den Wert. `null` heißt „nicht
  gemeldet“, nie 0; alte Events und Summaries ohne das Feld bleiben lesbar. Budget und Kosten
  rechnen unverändert mit den vollen Eingabe-Tokens (konservativ).
