# M11-Hygiene — drei rote CI-Gates auf `main` und `feat/issue-212-live-settings` fixen

**Datum:** 2026-05-11
**Branch:** `feat/m11-hygiene-radon-status`
**Worktree:** `.claude/worktrees/m11-hygiene`
**Refs:** #212 (PR #363 verklemmt sich an denselben Gates), PLAN.md M11.5 / Phase 6, CLAUDE.md PR-Workflow

## Befund

`main` ist seit Commit `83b7488` (P3.1-Followup, echte Persona/Segment/FrictionPoint/TrustSignal-Aggregation in `migrate_v2_to_v3`) auf drei CI-Gates rot. PR #363 (Live-Settings #212) erbt die gleichen Failures, weil er von `main` ausgeht.

| Gate | Befund | Ursache |
|---|---|---|
| Komplexitäts-Gate (radon) | `migrate_v2_to_v3` Class F (cc=50), `_map_profile_to_persona` Class D (cc=21) — beide nicht in Allowlist | `83b7488` hat die Aggregations-Logik massiv ausgebaut, Allowlist wurde nicht nachgezogen |
| status.md Drift-Check | Backend-Test-Count 1782 in status.md, real 1855 | Mehrere Slice-Adds seit 2026-05-04 ohne `scripts/sync-status.sh`-Lauf |
| GitGuardian Security Checks | `frontend/src/store/__tests__/settings.spec.ts:118` — Generic Password `'new-pw'` als Test-Marker | `.gitguardian.yaml` listet noch alte `.spec.js`-Endung von vor der TS-Migration (Sub-Slice 28, #71/#72/#73) |

## Fixes

### 1. GitGuardian-Pfad-Korrektur

`.gitguardian.yaml`: `frontend/src/store/__tests__/settings.spec.js` → `.spec.ts`. Die Test-Strings (`new-pw`, `tok-xyz`, …) sind synthetische Marker, die im bestehenden Block-Kommentar bereits begründet sind. Die Konfig wollte schon vor der TS-Migration nur diese Datei freigeben — sie hat das durch die Endung-Änderung verloren.

### 2. Radon-Allowlist-Erweiterung

`backend/radon-allowlist.txt`: zwei Einträge dazu:

```
app/services/evidence_migrations.py::migrate_v2_to_v3
app/services/evidence_migrations.py::_map_profile_to_persona
```

Top-5-Tabelle und Refactor-Kandidaten-Liste am Kopf der Datei aktualisiert (Stand 2026-05-11): `migrate_v2_to_v3` rückt mit cc=50 an Position 1 vor `get_generate_status` (cc=44). Die Datei `evidence_migrations.py` ist als eigener Refactor-Kandidat „nach v1.0" markiert (Aggregations-Helper splitten, Persona-Mapper ausgliedern).

Begründung für den Allow statt sofortigen Refactor: P3.1-Followup ist auf `main` und durch `tests/` abgedeckt; ein Refactor-Slice mitten in v1.0-Releasekritik (P4.1 echte Verdrahtung steht noch aus) lenkt den Fokus weg.

### 3. status.md-Sync

`bash scripts/sync-status.sh` lief sauber durch: nur die `<!-- BEGIN_AUTOGEN_TESTS -->`-Tabelle wurde upgedated (Backend 1782 → 1855). Frontend-Test-Files bleiben 47 — meine #212-Test-Adds sind dort nicht enthalten, weil dieser Branch von `main` ausgeht und PR #363 noch nicht gemerged ist.

## Verify

- `bash scripts/check_complexity.sh` → `OK: Keine neuen D/E/F-Klassen-Funktionen ausserhalb der Allow-List.`
- `bash scripts/sync-status.sh --check` → grün (keine weitere Drift)
- `cd backend && uv run ruff check app/ tests/` → grün
- Schemas-Drift: nicht angerührt, keine Veränderung in `schemas/`

## Out of Scope

- **P4.1 echt verdrahten** — Code-Audit 2026-05-11 hat aufgedeckt, dass `ReportMode`-Literal/Schema-Feld/Resolver fehlen und `ReportModelControls.vue` nur LLM-Modellwahl ist. Eigener Slice, kein Hygiene-Beifang.
- **`evidence_migrations.py` refactoren** — eigener Slice nach v1.0 (Allow-Eintrag dokumentiert das).
- **PR #363 weiterbringen** — die hier gefixten Gates entspannen #363 mit, aber #363 wartet zusätzlich auf User-Go zum Merge (CLAUDE.md: „Live-Settings #212 P2: erst nach M11-Stabilisierung").

## Folgeaktionen

1. Diesen PR mergen → `main` ist auf drei Gates wieder grün.
2. PR #363 rebase auf neue `main` → übernimmt die Fixes automatisch.
3. P4.1 als nächsten v1.0-Slice anziehen.
