### Added (Job-Lease mit Heartbeat und TTL für In-Process-Jobs — 2026-09-24)

- In-Process-Jobs (`simulation_prepare`, `report_generate`, `graph_build`,
  `ontology_generate`) trugen bisher nur einen PID+Token-Stempel ohne Ablauf
  (`app/jobs/identity.py`): ein hängender Job-Thread, dessen Prozess formal
  noch lebt, sah für die Startup-Reconciliation und `/resume` für immer
  "lebendig" aus, weil sich `worker_token` nie ändert. `enqueue()`
  (`app/jobs/__init__.py`) schreibt jetzt eine Lease (`JobLease`,
  `app/contracts/job_lease_contract.py`) mit `owner_pid`, `owner_token`,
  `heartbeat_at` und `lease_ttl_s`; ein Heartbeat-Thread erneuert
  `heartbeat_at` periodisch (Default: alle 20s, TTL 90s — beide über
  `AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS`/`AGORA_JOB_LEASE_TTL_SECONDS`
  konfigurierbar) und endet zuverlässig mit dem Job, auch bei einer
  Exception im Job-Target.
- `reconcile_stale_jobs` markiert einen In-Process-Job jetzt auch dann als
  `failed`/`process_restart`, wenn die Prozessidentität formal noch passt
  (`owns_run() == True`), die Lease aber abgelaufen ist — ein hängender
  Thread erkennt sich nicht mehr selbst als lebendig.
- `POST /api/runs/<id>/resume` lehnt einen **nicht-terminalen**
  (`pending`/`processing`) Run mit einer **gültigen** Lease jetzt mit
  `409`/`job_lease_active` ab (Schutz gegen doppelte Wiederaufnahme). Ein
  bereits terminaler Run (insbesondere `failed`/`process_restart`, von der
  Reconciliation ehrlich als verwaist markiert) darf trotz einer rechnerisch
  noch nicht abgelaufenen Lease fortgesetzt werden — sonst bliebe ein
  korrekt terminalisierter Job bis zu `lease_ttl_s` Sekunden lang blockiert.
- Rückwärtskompatibel: ein Altbestand-Manifest ohne Lease-Felder (nur der
  alte PID+Token-Stempel) verhält sich unverändert — die TTL-Prüfung greift
  ausschließlich, wenn eine Lease vorhanden ist.
