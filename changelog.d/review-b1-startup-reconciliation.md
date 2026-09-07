### Added (Simulations-Laufzeit - 2026-09-07)

- **Startup-Reconciliation für verwaiste `simulation_run`-Runs:** `reconcile_stale_runs` (`backend/app/services/sim/reconciliation.py`) läuft einmalig in `create_app`, direkt nach `SimulationRunner.register_cleanup()`. Sie iteriert alle RunRegistry-Einträge mit Status `pending`/`processing` und Typ `simulation_run`, lädt den zugehörigen `run_state.json` und prüft die dort persistierte `process_pid` per `os.kill(pid, 0)`-Liveness (`is_process_alive`). Fehlt der Prozess (oder fehlt `process_pid`/`run_state.json` ganz), wird der Run als `failed`/`process_restart` markiert — sonst bleibt er unangetastet. Steuerbar über `AGORA_STARTUP_RECONCILIATION` (Default an); ein Fehler in der Reconciliation bricht den App-Start nicht ab (best effort, geloggt).
- **`TerminationReason` um `"process_restart"` erweitert** (additiv, kein neuer `RunStatus`) — `backend/app/contracts/run_budget_contract.py` und Zod-Spiegel `frontend/src/contracts/runBudgetContract.ts`; Schemas neu gerendert.

### Fixed (Simulations-Laufzeit - 2026-09-07)

- **`process_manager.start_simulation` blockt einen Neustart nicht mehr allein wegen eines persistierten `RUNNING`/`STARTING`-Status.** Vor dem Ablehnen wird die `process_pid` aus dem letzten `run_state.json` per Liveness geprüft (`is_process_alive`); ist der Prozess tot, wird der alte State auf `FAILED`/„Prozess-Neustart während des Runs" korrigiert und der Start zugelassen, statt eine Simulation für immer als „läuft schon" zu blockieren.
- **Docker `stop_grace_period: 45s` + `init: true` am `agora`-Service in allen fünf Compose-Files** (`docker-compose.yml`, `docker-compose.override.yml`, `docker-compose.prod.yml`, `deploy/compose/docker-compose.prod-with-proxy.yml`, `deploy/compose/docker-compose.e2e.override.yml`). `gunicorn.conf.py` setzt `graceful_timeout=30`; Dockers Default von 10s hätte den Worker per SIGKILL abgeschossen, bevor er sauber beenden kann — genau die Ursache für die oben behobenen Orphan-Runs. `init: true` reapt Zombie-Kindprozesse (OASIS-Subprozesse).

### Bekannt offen (nicht Teil dieses Slices)

- Prepare-/Report-Daemon-Threads überleben einen Container-Restart ebenfalls nicht sauber (Issue [#1472](https://github.com/arn0ld87/agora/issues/1472)).
- Cancel-Flags (`cancel_flag.py`) liegen nur als `threading.Event` im Prozessspeicher, nicht Redis-persistent.
- Kein `worker_exit`-Hook in `gunicorn.conf.py`, der laufende Subprozesse beim Worker-Reload proaktiv abräumt.
