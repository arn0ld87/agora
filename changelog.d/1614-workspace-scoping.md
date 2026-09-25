### Added

- **Workspace-Isolation der Metadaten** — Alembic `14d60476b8ce`: `workspace_id` auf `agora.projects`, `simulations`, `runs` und `reports`. Der Bestand wird auf den Default-Workspace zurückgeschrieben. Zusammengesetzte Fremdschlüssel verhindern Verweise über Workspace-Grenzen, `ON DELETE SET NULL (<spalte>)` lässt die `workspace_id` stehen. Im Request arbeiten die PostgreSQL-Adapter nur im Workspace des Principals. Hintergrundpfade erben den Workspace des Elternteils. (#1614)

### Security

- **Keine fremde Kennung erreicht eine View** — für Supabase-Nutzer prüft der Guard jede Projekt-, Graph-, Simulations-, Run- und Report-Kennung in Pfad, Query und JSON-Body gegen den eigenen Workspace. Fremde und unbekannte Kennungen ergeben `404`. Das deckt auch Dateien und Neo4j-Graphen, die nicht in PostgreSQL liegen. In-Memory-Tasks werden nach Workspace gefiltert, die gemeinsame Persona-Bibliothek ist Betreibern vorbehalten. JWT ist mit dieser Isolation zulässig (`TENANT_ISOLATION_AVAILABLE`). (#1614)
