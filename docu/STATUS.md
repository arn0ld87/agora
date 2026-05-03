# Agora — Status (Single Source of Truth)

Stand: 2026-05-03

**Aktualisiert via `scripts/sync-status.sh`.** README, CLAUDE.md und ROADMAP verweisen auf diese Datei — Versionsstände und Test-Counts werden nicht mehr inline kopiert.

## Versionen

| Komponente | Pfad | Version |
|---|---|---|
| Backend | `backend/pyproject.toml` | 0.9.0 |
| Frontend | `frontend/package.json` | 0.9.0 |
| Root | `package.json` | 0.9.0 |

## Tests

| Kategorie | Anzahl | Methode |
|---|---|---|
| Backend Tests (collected) | 1330 | `cd backend && uv run pytest --collect-only -q` |
| Frontend Spec-Files | 17 | `find frontend/src \( -name '*.spec.ts' -o -name '*.spec.js' \)` |

_Hinweise: 2 Redis-Integrationstests skippen sauber ohne `TEST_REDIS_URL` und sind in der Backend-Summe enthalten (sie zählen als collected, werden aber zur Laufzeit übersprungen)._
_Die Frontend-Zeile zählt Dateien, nicht einzelne Test-Cases. Pro Spec-File laufen mehrere `it`-Blöcke; die exakte Test-Case-Anzahl liefert `cd frontend && npx vitest list`._

## Layer-Status (Übersicht)

Verbindliche Detailtabelle und Layer-Semantik: [`CLAUDE.md` § Architektur-Layer](../CLAUDE.md#architektur-layer-status).

| Layer | Inhalt | Status |
|---|---|---|
| 0 | Pydantic-Contracts + Zod-Spiegel | grün |
| 1 | Backend-Hardening | grün |
| 2 | DACH-Voice + Glossar v1 | grün |
| 3 | Reader-Honesty | grün |
| 4 | Frontend strict-Zod | grün |
| 5 | Eval/Baseline-Suite | grün |
| 6 | Frontend-TypeScript-Migration | grün |
| 7–8 | Graph/Runs/Persona-Review | teilweise |
| 9 | Prod-Deployment (Reverse-Proxy, gevent, SSE-Auth) | offen |
| 10 | Security Watchlist | dokumentiert |

## Aktuelles Milestone

**M9 — Prod-Hardening (Mai 2026, 23 Wochen).**

Detail: [`PLAN.md` § Milestone M9](../PLAN.md).

Aktive Slices: F5 Doku-Sync, F1 Reverse-Proxy, F2 Auth-Hardening, F3 Gunicorn-Gevent.

## Aktualisierungs-Protokoll

- 2026-05-03: Sub-Slice 44 — STATUS.md inaugural, Test-Counts und Versionsstände zentralisiert, Inline-Zahlen aus README/CLAUDE.md entfernt, ROADMAP auf v0.9.0+ / 2026-05-03 geheben.
