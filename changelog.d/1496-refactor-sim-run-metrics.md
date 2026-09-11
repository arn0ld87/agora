### Changed (Simulations-Read-Metriken aus Monitor-Orchestrierung extrahiert — 2026-09-11)

- `get_timeline` und `get_agent_stats` aggregieren persistierte Agentenaktionen jetzt in `backend/app/services/sim/run_metrics.py`.
- `backend/app/services/sim/monitor.py` behaelt duenne kompatible Wrapper und den bestehenden `_get_actions`-Monkeypatch-Hook; Prozessueberwachung, Cancellation und Manifest-Finalisierung bleiben unveraendert im Monitor-Modul.
- Der veraltete Radon-Allowlist-Eintrag fuer die bereits extrahierte Run-Summary wurde entfernt; der Frontend-Kommentar zur Run-Summary-SSoT zeigt auf `services/run_read_model.py`.
