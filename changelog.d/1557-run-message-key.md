### Changed

- Run-Lifecycle-Meldungen (`runs.py`, `simulation_run.py`) tragen einen stabilen `message_key` (`run.*`), `RunDetail` und der Zod-Spiegel führen das Feld, Regal und Dossier übersetzen über `resolveStatusMessage` mit Klartext-Fallback. Ein neues `message` ohne Schlüssel räumt einen veralteten Schlüssel ab (#1557).
