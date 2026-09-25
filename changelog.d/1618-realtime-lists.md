### Added

- **Realtime für Listen-Projektionen** — Mit `AGORA_SUPABASE_REALTIME=true` lädt das Frontend Ablage und Run-Listen sofort nach, wenn sich im aktiven Workspace ein Projekt, eine Simulation, ein Run oder ein Report ändert. Das Ereignis ist nur ein Signal, die Daten kommen weiter über die Flask-API. Polling und das SSE laufender Läufe bleiben.
  - **Migration** `dc4e84e7c000`: die vier Tabellen in der Publication `supabase_realtime`, nur `INSERT`/`UPDATE`. Ohne Publication ein No-op.
  - **Dienst** `realtime` im Supabase-Stack, nur über das Gateway erreichbar; neuer Pflichtwert `REALTIME_DB_ENC_KEY`.
  - **Vertrag:** `AuthConfigResponse.realtime_enabled` (Default `false`). (#1618)
