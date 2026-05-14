---
description: MAI-12 — Neo4j/Redis-Pools sind fork-safe via os.register_at_fork. Aktiviert gunicorn --preload für ~40% schnelleren Startup.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-12-fork-safety — Fork-Safety + `--preload` aktivieren

## Ziel

Neo4j-Driver-Pool, Redis-Pool und Embedding-Service werden via `os.register_at_fork(after_in_child=...)` re-initialisiert. Damit kann Gunicorn mit `--preload` starten, was die Master-Init (Pre-Fork) einmalig laufen lässt und alle Worker per fork erbt — eliminiert „Init-Logs doppelt", spart ~40 % Boot-Zeit pro Worker.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-12/`.
- Branch: `feat/mai-12-fork-safety`.
- **MAI-06 muss durch sein** — Persistenz-Pfade müssen final sein, sonst lassen sich Race-Conditions zwischen Workern nicht ausschließen.
- **Opus-Pre-Review-Pflicht** (Pool-Touch + gevent-Interaktion).

## Schritt-für-Schritt

### Schritt 1: Pool-Initialisierung lokalisieren

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-12
rg -n "GraphDatabase\.driver\|neo4j\.driver" backend/app/
rg -n "redis\.from_url\|Redis\(" backend/app/
rg -n "create_app\|def create_app" backend/app/__init__.py
rg -n "monkey\.patch_all\|gevent" backend/
```

### Schritt 2: Pool-Factories isolieren

`backend/app/extensions.py` (neu, oder zentralisieren falls schon vorhanden):

```python
"""MAI-12: Fork-safe Pool-Factories.

Pattern:
    - Master init: factory()-Aufruf legt Pool an
    - Fork: register_at_fork(after_in_child=reset) bricht alten Pool ab,
      Worker baut sich beim ersten Use einen neuen.
"""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from neo4j import Driver
    from redis import Redis

_neo4j_driver: Optional["Driver"] = None
_neo4j_lock = threading.Lock()

_redis_client: Optional["Redis"] = None
_redis_lock = threading.Lock()


def get_neo4j_driver() -> "Driver":
    """Lazy-init Neo4j-Driver, fork-safe via register_at_fork."""
    global _neo4j_driver
    if _neo4j_driver is None:
        with _neo4j_lock:
            if _neo4j_driver is None:
                from neo4j import GraphDatabase
                from .config import Config
                _neo4j_driver = GraphDatabase.driver(
                    Config.NEO4J_URI,
                    auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
                )
    return _neo4j_driver


def _reset_neo4j_after_fork() -> None:
    """Forked Workers dürfen den Master-Pool nicht weiterverwenden."""
    global _neo4j_driver
    if _neo4j_driver is not None:
        try:
            _neo4j_driver.close()
        except Exception:
            pass
    _neo4j_driver = None


def get_redis_client() -> "Redis":
    global _redis_client
    if _redis_client is None:
        with _redis_lock:
            if _redis_client is None:
                import redis
                from .config import Config
                _redis_client = redis.from_url(Config.REDIS_URL)
    return _redis_client


def _reset_redis_after_fork() -> None:
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:
            pass
    _redis_client = None


def register_fork_handlers() -> None:
    """Registriert after-in-child-Handler für alle Pools.

    Muss VOR dem ersten fork() laufen — d.h. im create_app() Master-Init.
    """
    if not hasattr(os, "register_at_fork"):
        # macOS Edge-Case / sehr alte Python — defensive.
        return
    os.register_at_fork(
        after_in_child=_reset_neo4j_after_fork,
    )
    os.register_at_fork(
        after_in_child=_reset_redis_after_fork,
    )
```

### Schritt 3: create_app anpassen

`backend/app/__init__.py`:

```python
def create_app(config_overrides=None):
    # gevent monkey-patch MUSS vor allen Net-Lib-Imports laufen
    import gevent.monkey
    gevent.monkey.patch_all()

    from flask import Flask
    from .config import Config
    from .extensions import register_fork_handlers

    app = Flask(__name__)
    # ... bestehende Config-Loading-Logik ...

    # MAI-12: Fork-Handler registrieren BEVOR Worker forken
    register_fork_handlers()

    # MAI-12: Pre-Fork init der Singletons. Worker erben den Master-Snapshot
    # und re-initialisieren via register_at_fork.
    from .extensions import get_neo4j_driver
    try:
        driver = get_neo4j_driver()
        app.extensions['neo4j_driver'] = driver
        app.logger.info("Neo4j storage initialized (pre-fork, MAI-12)")
    except Exception as exc:
        app.extensions['neo4j_storage_error'] = str(exc)
        app.logger.warning(f"Neo4j init failed pre-fork: {exc}")

    # ... Blueprint-Registration, etc.
    return app
```

### Schritt 4: gunicorn --preload aktivieren

`backend/Dockerfile` (prod-stage CMD):

```dockerfile
CMD ["gunicorn", \
     "-k", "gevent", \
     "--workers", "2", \
     "--preload", \
     "--bind", "0.0.0.0:5001", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:create_app()"]
```

`backend/run.py` für lokales Dev (falls genutzt):

```python
# MAI-12: --preload-Smoke vor Prod-Deploy
# gunicorn -k gevent --workers 2 --preload "app:create_app()"
```

### Schritt 5: Tests

`backend/tests/test_fork_safety.py`:

```python
"""MAI-12: Fork-Safety der Connection-Pools."""

import os
from unittest.mock import patch, MagicMock

import pytest

from app.extensions import (
    _reset_neo4j_after_fork,
    _reset_redis_after_fork,
    get_neo4j_driver,
    get_redis_client,
    register_fork_handlers,
)


def test_register_fork_handlers_idempotent():
    """register_fork_handlers() darf mehrfach aufgerufen werden."""
    register_fork_handlers()
    register_fork_handlers()  # kein Crash


def test_reset_neo4j_clears_singleton(monkeypatch):
    """after_in_child schließt alten Driver und nullt das Singleton."""
    import app.extensions as ext

    mock_driver = MagicMock()
    monkeypatch.setattr(ext, "_neo4j_driver", mock_driver)

    _reset_neo4j_after_fork()

    assert ext._neo4j_driver is None
    mock_driver.close.assert_called_once()


def test_reset_redis_clears_singleton(monkeypatch):
    import app.extensions as ext

    mock_client = MagicMock()
    monkeypatch.setattr(ext, "_redis_client", mock_client)

    _reset_redis_after_fork()

    assert ext._redis_client is None
    mock_client.close.assert_called_once()


def test_get_neo4j_driver_thread_safe(monkeypatch):
    """Concurrent get_neo4j_driver liefert dieselbe Instanz."""
    import threading
    import app.extensions as ext

    mock_driver = MagicMock()
    monkeypatch.setattr(ext, "_neo4j_driver", None)
    with patch("neo4j.GraphDatabase.driver", return_value=mock_driver):
        results = []
        threads = [threading.Thread(target=lambda: results.append(get_neo4j_driver()))
                   for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(set(id(r) for r in results)) == 1  # alle dieselbe Instanz
```

### Schritt 6: Live-Smoke

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-12

# Container-Build mit --preload
docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache agora
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate agora neo4j redis

# Init-Logs zählen
sleep 8
LINES=$(docker logs agora 2>&1 | grep -c "Neo4j storage initialized")
echo "Neo4j-Init-Log-Lines: $LINES (erwartet: 1)"

# 100 Requests gegen /api/status — keine Connection-Resets
for i in {1..100}; do
  curl -fsS -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
    http://localhost/api/status > /dev/null || echo "FAIL #$i"
done
```

## Verifikation

```bash
# 1) Unit-Tests grün
cd backend && uv run pytest tests/test_fork_safety.py tests/test_gevent_fork.py -x -v

# 2) Voll-Test
cd backend && uv run pytest -x -q

# 3) Container-Smoke (siehe Schritt 6)
LINES=$(docker logs agora 2>&1 | grep -c "Neo4j storage initialized")
[ "$LINES" -eq 1 ] && echo "OK MAI-12" || echo "FAIL: $LINES Init-Lines (erwartet 1)"

# 4) verify-deploy.sh
bash scripts/verify-deploy.sh
```

## Warum?

CLAUDE.md Hot-Spots: „Init-Logs doppelt — Folge-Slice braucht Fork-Safety-Verifikation der Neo4j/Redis-Pools vor `--preload`-Aktivierung." Ohne fork-safe Pools würde `--preload` den Master-Pool an alle Worker durchreichen, die Worker shared sockets verwenden würden → unvorhersehbares Connection-Reset-Verhalten unter Last. `os.register_at_fork` ist der Standard-Mechanismus dafür (Python 3.7+).

## Nächste Schritte

1. **PR statt FF-Push** wegen High Risk (Pool-Touch).
2. Worklog mit Container-Smoke-Output (Init-Lines, Request-Count).
3. CHANGELOG: `MAI-12 · Fork-safe Neo4j/Redis-Pools via os.register_at_fork; gunicorn --preload aktiviert.`
4. `/fix-mai-11-pr-smoke-rc-only` parallel oder nach Merge.
