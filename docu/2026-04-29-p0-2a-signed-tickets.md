# P0.2a — Signed-Ticket-Util

**Datum:** 2026-04-29
**Slice:** P0.2a (siehe `PLAN.md`)
**Branch:** `security/repo-hardening`

## Ziel

Self-contained HMAC-Ticket-Modul, das die Grundlage für die Migration weg von `?token=<bearer>` in URLs bildet. Tickets sind kurzlebig (Default 60 s), scope-bound und werden via `consume()` einmalig verbraucht.

## Format

```
v1.<exp_unix>.<scope>.<sig>
```

- `sig` = `HMAC-SHA256(secret, "v1.<exp>.<scope>")[0:32]` (128 Bit)
- `scope` darf keine `.` enthalten — kollidiert sonst mit dem Trenner
- `consume()` führt zusätzlich einen Process-Local-Set mit Expiry-Sweep, um Replay innerhalb der TTL zu verhindern

## Änderungen

- Neu: `backend/app/utils/signed_ticket.py` — `issue`, `verify`, `consume`, `_reset_seen_for_tests`.
- Neu: `backend/tests/test_signed_ticket.py` — 10 Tests:
  - Roundtrip
  - Expiry abgelaufen → False
  - Falscher Scope → False
  - Manipulierte Signatur → False
  - Falsches Secret → False
  - Garbage Input → False
  - `consume` einmal ok, zweites Mal False
  - `consume` für unterschiedliche Scopes blockiert sich nicht gegenseitig
  - `_seen`-Set wird bei späteren Consumes gesweept
  - `issue` validiert Inputs (leeres Secret/Scope, `.` in Scope, TTL ≤ 0)

## Verifikation

- `uv run pytest tests/test_signed_ticket.py` → 10/10 grün.
- `uv run pytest` Full-Suite → 312 passed, 2 skipped.
- `uv run ruff check app/utils/signed_ticket.py tests/test_signed_ticket.py` → clean.

## Bekannte Grenzen

- Process-Local-`_seen`: bei Multi-Worker-Deployments ist Replay theoretisch pro Worker möglich. Für TTL 60 s und enge Scopes vertretbar; Folge-Ticket: optional Redis-backed Set.
- Kein Format-Versions-Lifecycle: ein hartes `v1`-Reject macht Upgrades trivial, aber heute keine Migrationspfad-Annahme.

## Status

**Erledigt 2026-04-29.**
