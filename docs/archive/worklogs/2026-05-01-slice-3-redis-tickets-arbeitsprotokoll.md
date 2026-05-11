# Slice 3 — Redis-basierte Single-Use-Tickets (PR3)

**Datum:** 2026-05-01
**Branch:** `claude/sleepy-torvalds-32f68f`
**Slice-Quelle:** Repo-Review PR3 (User-Prompt, „Redis-basierte Single-Use-Tickets").

## Ziel

`signed_ticket.consume()` muss Replay-Attacken auch unter gunicorn-Multi-
Worker verhindern. Bisher war die `_seen`-Menge nur in-process.

## Ausgangslage

- [backend/app/utils/signed_ticket.py:22–25](../backend/app/utils/signed_ticket.py:22)
  bestätigt die Lücke: „Multi-worker deployments lose that guarantee per
  worker; tighten via a shared store later if needed."
- Redis war bereits als Dependency vorhanden (`redis>=5.0.0`) für den
  Event-Bus (Issue #9).

## Änderungen

### backend/app/utils/signed_ticket.py
- `_get_redis_client()`: Lazy-Init von `redis.Redis.from_url(Config.REDIS_URL)`
  mit 2 s Timeouts. Ping-Check beim ersten Zugriff.
- `_try_redis_consume(sig, ttl)`: Atomisches `SET NX EX`. `True` = erster
  Verbraucher, `False` = Replay, `None` = Redis nicht verfügbar.
- `consume()`: Versucht Redis zuerst; bei `None` fällt auf in-process mit
  `logger.debug` zurück.
- `_reset_seen_for_tests()`: Setzt auch `_redis_client` und
  `_redis_init_attempted` zurück.

### backend/tests/test_signed_ticket_redis.py (neu)
- 6 Cases in 2 Klassen:
  - `TestRedisConsume`: First-consume OK, Replay blockiert, Multi-Worker-Race
  - `TestInMemoryFallback`: Fallback erlaubt/blocked, Debug-Log emitted
- `fakeredis.FakeRedis()` als Redis-Client-Stub.

### backend/pyproject.toml
- `fakeredis[lua]>=2.30.0` in `[project.optional-dependencies] dev` und
  `[dependency-groups] dev` ergänzt.

### docs/security.md
- Neuer Abschnitt „Slice 3 — Redis-basierte Single-Use-Tickets" mit
  Änderungs-Übersicht und Verifikation.

## Verifikation

- `npm run check` grün
- Backend: 689 passed (bestehende 683 + 6 neue), 9 skipped (2 Redis-Integration,
  7 Compose-Snapshot)
- Frontend: 40 passed, Lint 0 errors / 1 pre-existing Warnung
- Build ok
- `uv run pytest tests/test_signed_ticket.py tests/test_signed_ticket_redis.py -v`
  → 16 passed

## Migration

Keine — Redis wird via `REDIS_URL` (bereits im Default-Compose vorhanden)
automatisch erkannt. Fehlt Redis, fällt `consume()` lautlos auf den
in-process-Pfad zurück.
