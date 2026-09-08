### Behoben

- Der parallele Twitter+Reddit-Runner (`run_parallel_simulation.py`) ist der
  Default-Pfad für jeden Simulationslauf, der nicht explizit Twitter- oder
  Reddit-only ist — er hatte bisher weder Hard-Budget noch Pause- noch
  Stop-Kontrolle. Beide Runden-Schleifen prüfen jetzt an jeder Rundengrenze
  über dieselbe `RoundBoundaryControl` wie `sim_runtime.platform_runner`
  (Pause abwarten, kooperativen Stop, hartes Budget); bei Budget-Abbruch
  endet der Lauf deterministisch statt in den Wait-Mode zu gehen, damit der
  Backend-Monitor den Abbruchgrund übernimmt.
- `platform_runner.py` nutzt dieselbe `RoundBoundaryControl` statt eines
  inline duplizierten Prüfblocks — Verhalten unverändert, `budget_abort_info`
  bleibt bei Stop/Normal-Durchlauf `None` und trägt nur beim Budget-Abbruch
  das Info-Dict, damit der nachfolgende Wait-Mode-Guard weiter korrekt greift.
- `ParallelIPCHandler` bucht Interview- und Batch-Interview-Verbrauch jetzt
  auf den Report-Run (`report_run_id`), sobald ein Report-Interview über den
  parallelen Default-Pfad läuft — vorher blieb dieser physische Modellaufruf
  unverbucht und das Hard-Budget eines Report-Laufs war dort umgehbar. Die
  Zuordnung nutzt dieselbe `report_attribution()`-Funktion wie
  `sim_runtime.ipc.IPCHandler` (aus dessen bisheriger Methode extrahiert,
  verhaltensneutral) statt einer zweiten Implementierung.
