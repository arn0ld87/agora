### Changed

- Run-Lifecycle-Meldungen (`runs.py`, `simulation_run.py`) tragen einen stabilen `message_key` (`run.*`), `RunDetail` und der Zod-Spiegel führen das Feld, Regal und Dossier übersetzen über `resolveStatusMessage` mit Klartext-Fallback. Ein neues `message` ohne Schlüssel räumt einen veralteten Schlüssel ab (#1557).
- Der Runner-Sync (`SimulationRunner._save_run_state`, alle zwei Sekunden aus `monitor_simulation`) und die Restart-Reconciliation schicken jetzt `run.runner_status_<status>` als `message_key` mit; vorher hätte der erste Poll den Startschlüssel geleert und Shelf/Dossier wären auf den englischen Klartext zurückgefallen (#1557).
