### Fixed (Reportstatus an Contract-Validität gekoppelt — 2026-08-14)

- Ein Report mit ungültigem `ReportV3`-Contract oder fehlgeschlagener Zitat-Validierung (`quote_validation_failed=True`) erreicht nicht mehr fälschlich den Status `completed` — er wird mindestens auf `incomplete` abgestuft, nie aufgewertet.
