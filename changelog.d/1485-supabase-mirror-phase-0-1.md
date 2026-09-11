### Added (Supabase-Mirror Phase 0/1 — optionaler App-Metadaten-Index)

- **Self-hosted Supabase als Metadaten-Spiegel hinter Feature-Flag:** Neues
  Paket `app.services.supabase_mirror` spiegelt Run-/Report-/Dokument-Metadaten
  idempotent nach Postgres (Schema `agora`, Tabellen `runs`, `run_events`,
  `report_index`, `documents`, `audit_log`) — service_role nur im Backend-Env,
  Write-Through best-effort und nie fatal. Wahrheit bleibt im Dateisystem
  (Run-Manifeste, Report-Metadaten, Dokument-Manifeste) bzw. Neo4j
  (Graph/Vektoren); `python -m app.services.supabase_mirror.rebuild`
  rekonstruiert den Index komplett aus der Wahrheit. Default
  `SUPABASE_ENABLED=false`: null Netzwerkverhalten. DDL+RLS (deny-by-default)
  unter `deploy/supabase/`, Contracts in
  `app/contracts/supabase_mirror_contract.py` (Schema-Dump inklusive). Kein
  Graph-, Embedding-, Auth- oder Edge-Function-Ersatz (Plan:
  `docs/plans/supabase.md`, Phase 2 Realtime und Phase 3 Auth folgen separat).
