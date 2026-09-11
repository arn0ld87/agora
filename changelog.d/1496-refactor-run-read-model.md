### Changed (Run-Read-Model aus API-God-Controller extrahiert — 2026-09-11)

- Die rein lesende Summary-Anreicherung fuer Run-Listen und Run-Details liegt jetzt in `backend/app/services/run_read_model.py` statt in `backend/app/api/runs.py`.
- HTTP-Contracts, Feldnamen, Caching-Verhalten und Best-Effort-Fehlerbehandlung bleiben unveraendert; Resume-, Routing-, Budget- und Lifecycle-Pfade wurden nicht angefasst.
- Hintergrund ist das repository-weite LOC-/Struktur-Audit unter `docs/refactor/loc-audit.md`; `runs.py` war mit 1419 Zeilen der deutlichste God-Controller-Kandidat.
