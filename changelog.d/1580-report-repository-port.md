### Changed

- **Report-Metadaten: Repository-Port eingeführt** — `ReportManager` delegiert das Lesen/Schreiben von `meta.json` (inkl. Legacy-Flachformat-Fallback) jetzt an `FileReportRepository` hinter dem `ReportRepository`-Protocol. `ReportRecord` (Pydantic v2, `extra="ignore"`) ist der kanonische Persistenzvertrag; Report-Inhalte (Markdown, ReportV3-JSON, Outline, Sections, Logs) bleiben Dateien und laufen nicht über den Port. Der PostgreSQL-Adapter folgt in #1588. (#1580)
