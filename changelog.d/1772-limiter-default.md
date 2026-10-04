### Changed

- Simulation: Der Tokens-pro-Minute-Limiter ist jetzt standardmäßig an.
  `AGORA_SIM_INPUT_TOKENS_PER_MINUTE` steht auf `1500000` (75 % des Kontolimits von
  2 Mio. TPM für `gpt-6-luna`), `0` schaltet ihn ab. **Verhaltenswechsel:** Läufe
  werden gedrosselt und damit langsamer, verlieren aber weniger Agentenschritte
  (Lauf `sim_c8c6b30aa652` ohne Limiter: 872 von 2.091 Aufrufen `RateLimitError`,
  209 verlorene Schritte). Rückweg: Variable auf `0` setzen.

### Fixed

- Simulation: Fehlgeschlagene Anbieteraufrufe tragen ihren HTTP-Status jetzt im
  Call-Event (`http_status`, bisher immer `null`), und das `simulation.log` nennt
  die gekürzte Anbietermeldung (z. B. welches Limit gerissen wurde: Limit, Used,
  Requested). Je Fehlerklasse und Status erscheint höchstens eine Zeile pro Minute
  mit der Zahl der unterdrückten gleichartigen Fehler; Schlüssel (`sk-…`,
  `Bearer …`, `api_key=…`) werden vorher entfernt, Prompt und Header nie gelesen.
  Die Redaktion ist aus dem Report-Workflow nach `app/utils/provider_message.py`
  verschoben (Verhalten unverändert).

- Simulation: Der Limiter ließ bei leerem Fenster alle gleichzeitig wartenden Aufrufe
  durch (zwei Plattformen mit Parallelität 8 starteten 16 Aufrufe, bevor ein
  Messwert existierte). Jetzt läuft zuerst eine Sonde allein, danach reserviert jeder
  laufende Aufruf das Mittel der letzten 32 Messwerte, auch nach einer Pause. Meldet
  der Anbieter keine Usage, wird nicht serialisiert (Warnung im Log).
- Simulation: `AGORA_SIM_MAX_CONCURRENCY` und `AGORA_SIM_INPUT_TOKENS_PER_MINUTE`
  standen nicht in der Env-Whitelist des Simulations-Subprozesses; ein in `.env` oder
  Compose gesetzter Wert erreichte ihn nie.
