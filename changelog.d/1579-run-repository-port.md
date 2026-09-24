### Changed

- **Run-Registry: Repository-Port eingeführt** — `RunRegistry` delegiert die Datei-I/O jetzt an `FileRunRepository` hinter dem `RunRepository`-Protocol. `RunRecord` (Pydantic v2, `extra="allow"`) ist der kanonische Persistenzvertrag; Lease-Felder bleiben in `metadata`. Der PostgreSQL-Adapter folgt in #1587. (#1579)
