### Fixed (Reportstatus an Contract-Validität gekoppelt — 2026-08-14)

- Ein Report mit ungültigem `ReportV3`-Contract oder fehlgeschlagener Zitat-Validierung (`quote_validation_failed=True`) erreicht nicht mehr fälschlich den Status `completed` — er wird mindestens auf `incomplete` abgestuft, nie aufgewertet. Erfasst jetzt auch: einen frisch fehlgeschlagenen `ReportV3`-Build ohne persistiertes Artefakt (vorher unsichtbar, da `save_report()` den Fehler intern abfängt) sowie eine bereits vor einem Cancel erfolglos gebliebene Zitatprüfung im Teil-Report-Pfad.
