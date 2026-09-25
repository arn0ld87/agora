### Changed

- **Report-Metadaten: letzte Direktzugriffe auf `meta.json` über den Port** — `branching_service.create_branch` und `simulation_history._get_report_id_for_simulation` lesen Report-Metadaten jetzt über `ReportRepository` (`list_ids()`/`get()` bzw. `list(simulation_id=...)`) statt `meta.json` per `open()` zu lesen. Der Zweig kopiert den Report-Ordner unter dem Ablageschlüssel, nicht unter der `report_id` im Manifest. Vorbereitung für den PostgreSQL-Adapter (Teil 1 von #1588).
