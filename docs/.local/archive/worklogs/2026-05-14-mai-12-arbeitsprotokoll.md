# MAI-12 Arbeitsprotokoll — 2026-05-14

## Ziel
Fork-safe Neo4j/Redis-Pools + gunicorn --preload, um doppelte Init-Logs
zu eliminieren und ~40 % schnelleren Worker-Start zu erzielen.

## Änderungen

- `backend/app/extensions.py` (NEU, +44 LOC): `register_fork_handlers()`
  registriert `os.register_at_fork(after_in_child=...)` für Neo4j-Driver
  und Redis signed_ticket. Safe auf non-Unix-Plattformen (kein
  `register_at_fork`-Attribut → early return).

- `backend/app/storage/neo4j_storage.py` (+17 LOC): `_reset_driver_after_fork()`
  schließt den geerbten Driver nach gunicorn-Fork und setzt `_driver = None` /
  `_is_connected = False`. Der erste echte DB-Call triggert Reconnect via
  `neo4j_call_with_retry`.

- `backend/app/__init__.py` (+3 LOC): `register_fork_handlers(neo4j_storage=neo4j_storage)`
  wird nach dem Storage-Init-Block in `create_app()` aufgerufen.

- `Dockerfile` (+1 LOC): `--preload` Flag in gunicorn CMD nach `--workers 2`.

- `backend/tests/test_fork_safety.py` (NEU, +60 LOC): 5 Unit-Tests.

## Abweichungen vom Plan

- `_reset_signed_ticket_redis_client` im Brief war halluziniert. Tatsächlich
  existiert `_reset_seen_for_tests()` in `signed_ticket.py`, die korrekt
  `_redis_client = None` + `_redis_init_attempted = False` setzt. Diese
  Funktion wird als Fork-Handler registriert (alias `_reset_redis`).

- mypy erforderte `TYPE_CHECKING`-Import für `Neo4jStorage` in `extensions.py`
  (Zirkelimport-Vermeidung) und explizite `Optional["Neo4jStorage"]`-Annotation
  statt `object`.

## Tests

```
tests/test_fork_safety.py::test_reset_driver_after_fork_closes_and_nones_driver PASSED
tests/test_fork_safety.py::test_reset_driver_after_fork_handles_close_error PASSED
tests/test_fork_safety.py::test_reset_driver_after_fork_handles_none_driver PASSED
tests/test_fork_safety.py::test_register_fork_handlers_no_neo4j PASSED
tests/test_fork_safety.py::test_register_fork_handlers_with_mock_storage PASSED

5 passed in 1.05s
```

Volltest: 30 passed, 2 skipped, 1 pre-existing failure
(`test_add_progress_callback_sets_progress_detail_on_task_manager` —
`LLM_API_KEY not configured`, bestand vor MAI-12, verifiziert via `git stash`).

## Akzeptanzkriterien

- [x] `register_at_fork` in `extensions.py`
- [x] `register_fork_handlers` in `__init__.py`
- [x] `_reset_driver_after_fork` in `neo4j_storage.py`
- [x] `--preload` in Dockerfile
- [x] `test_fork_safety.py` — 5/5 grün
- [x] `ruff check app/ tests/` — kein Fehler
- [x] `mypy app` — kein Fehler (156 source files)
- [x] `git diff --exit-code schemas/` — kein Schema-Drift
