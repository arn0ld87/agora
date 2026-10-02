### Fixed (Test-Isolation der echten Datenverzeichnisse — 2026-10-02)

- **Die Testsuite schreibt nicht mehr in `backend/uploads`:** Ein autouse-Fixture lenkt
  `Config.UPLOAD_FOLDER`, `Config.OASIS_SIMULATION_DATA_DIR` und die beim Import berechneten
  Klassenpfade (`RunRegistry`, `ProjectManager`, `ReportManager`, `SimulationManager`,
  `SimulationRunner`) je Test in ein eigenes tmp-Verzeichnis; isoliert war bisher nur
  `AGORA_DATA_DIR`. Die `atexit`-Hooks der Job-Terminalisierung werden am Suite-Ende
  abgemeldet. Sie hatten nach dem letzten Test, mit zurückgenommenen Patches, noch
  „laufende“ Test-Runs als `failed` in die echte Run-Registry geschrieben. So entstanden die
  Manifeste für die Fixture `sim_abcdef012345` auf armserver. Ein Graph-Build-Test ließ zudem
  seinen Job-Thread über das Testende hinaus weiterlaufen. (#1632)
- **Schreibsperre als Regressionsschutz:** Ein Audit-Hook (`tests/_real_data_guard.py`)
  blockiert in der Suite Schreiben, Anlegen, Umbenennen, Verlinken oder Löschen über
  Python-Dateioperationen unter
  `backend/uploads`, `backend/data` und dem beim Start gesetzten `AGORA_DATA_DIR`. Er lässt
  den Test auch dann scheitern, wenn der Code die Ausnahme verschluckt; eine
  Subprozess-Gegenprobe belegt das. (#1632)
- **`/api/status` misst den Plattenplatz von `Config.UPLOAD_FOLDER`** statt eines eigenen
  `__file__`-Pfads. Im Betrieb ist das derselbe Pfad. (#1632)
