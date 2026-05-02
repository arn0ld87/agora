# Sub-Slice 21 — OASIS-DB-Pfad pro Sim (read-only-FS-Hotfix)

**Datum:** 2026-05-03
**Branch:** `feat/task-21-oasis-db-path`
**Layer:** Deployment / Subprozess-Glue
**Refs:** Folge-Crash zu Sub-Slice 18+19 (Prod-Container mit `read_only: true`).

## Symptom

Sim-Subprozess crashed nach Phase 2 (Persona-Generation OK) am ersten
OASIS-`step()`:

```
File "/app/backend/.venv/lib/python3.11/site-packages/oasis/social_platform/database.py",
  line 72, in get_db_path
    os.makedirs(db_dir, exist_ok=True)
OSError: [Errno 30] Read-only file system:
  '/app/backend/.venv/lib/python3.11/site-packages/oasis/data'
```

OASIS will eine SQLite-DB **innerhalb der venv** anlegen
(`site-packages/oasis/data/social_media.db`). Im Dev-Container ohne
`read_only: true` funktioniert das (zufällig), im Prod-Container ist
das Site-Packages-Layer read-only und der `mkdir` schlägt fehl.

## Root Cause

OASIS' [`get_db_path()`](backend/.venv/lib/python3.11/site-packages/oasis/social_platform/database.py)
hat einen sauberen ENV-Override:

```python
def get_db_path() -> str:
    env_db_path = os.environ.get("OASIS_DB_PATH")
    if env_db_path:
        return env_db_path  # ← kein mkdir, ENV nimmt Pfad as-is

    # Default-Pfad: in site-packages/oasis/data/
    parent_dir = osp.dirname(osp.dirname(osp.abspath(__file__)))
    db_dir = osp.join(parent_dir, DB_DIR)
    os.makedirs(db_dir, exist_ok=True)  # ← knallt im read-only-FS
    db_path = osp.join(db_dir, DB_NAME)
    return db_path
```

`SimulationRunner.start_simulation` setzte den Subprozess-Env zwar mit
`PYTHONUTF8` und `PYTHONIOENCODING`, aber **nicht** mit `OASIS_DB_PATH`.
Default-Pfad-Branch wurde getroffen → Crash.

## Fix

[`backend/app/services/simulation_runner.py`](backend/app/services/simulation_runner.py)
um zwei Helper erweitert:

```python
_OASIS_DB_DIR_NAME = "oasis_db"
_OASIS_DB_FILE_NAME = "social_media.db"


def _compute_oasis_db_path(sim_dir: str) -> str:
    """<sim_dir>/oasis_db/social_media.db, mkdir idempotent."""
    db_dir = os.path.join(sim_dir, _OASIS_DB_DIR_NAME)
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, _OASIS_DB_FILE_NAME)


def _inject_oasis_db_env(env: Dict[str, str], sim_dir: str) -> None:
    """Setzt OASIS_DB_PATH nur, wenn User es nicht selbst überschrieben hat."""
    if env.get("OASIS_DB_PATH"):
        return
    env["OASIS_DB_PATH"] = _compute_oasis_db_path(sim_dir)
```

Aufruf direkt vor `subprocess.Popen` in `start_simulation`:

```python
env = os.environ.copy()
env['PYTHONUTF8'] = '1'
env['PYTHONIOENCODING'] = 'utf-8'
_inject_oasis_db_env(env, sim_dir)
```

`sim_dir` ist `RUN_STATE_DIR/<simulation_id>` →
`/app/backend/uploads/simulations/sim_<id>/`. Das Verzeichnis
`uploads/` ist als Bind-Mount (`./backend/uploads:/app/backend/uploads`,
siehe [`docker-compose.yml:34`](docker-compose.yml:34)) schreibbar und
persistent.

## Tests

Neu: [`backend/tests/test_simulation_runner_oasis_db_path.py`](backend/tests/test_simulation_runner_oasis_db_path.py) — 4 Cases:

| Case | Erwartung |
|---|---|
| `_compute_oasis_db_path(sim_dir)` | endet auf `oasis_db/social_media.db`, Verzeichnis exists |
| Mehrfacher Aufruf | idempotent, gleicher Pfad |
| `OASIS_DB_PATH` von User gesetzt | Helper überschreibt nicht |
| `OASIS_DB_PATH` nicht gesetzt | Helper injiziert sim-spezifischen Pfad ins env |

## Verifikation

```
$ uv run pytest tests/test_simulation_runner_oasis_db_path.py -x -q
4 passed in 1.10s

$ uv run ruff check app/ tests/
All checks passed!

$ uv run pytest -x -q
1271 passed, 2 skipped in 60.42s
```

End-to-End-Verifikation ist nutzerseitig: nach Container-Rebuild läuft
eine Sim ohne `OSError: Read-only file system` durch, OASIS schreibt
ihre SQLite-DB nach `<uploads>/simulations/<sim_id>/oasis_db/social_media.db`.

## Sim-Isolation als Bonus

Vorher: alle Sims teilten sich eine DB im Site-Packages — bei parallelen
Runs Race-Condition auf SQLite-Locks. Jetzt: jede Sim hat ihre eigene DB
unter `<sim_dir>/oasis_db/`. Stabilerer Multi-Run-Pfad.

## Geänderte Dateien

- `backend/app/services/simulation_runner.py` — Helper + Inject-Aufruf
- `backend/tests/test_simulation_runner_oasis_db_path.py` (neu)
- `CHANGELOG.md` — `[Unreleased]` / Fixed-Block
