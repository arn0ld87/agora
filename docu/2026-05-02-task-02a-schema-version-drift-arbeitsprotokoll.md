# Sub-Slice 02a · Schema-Version-Drift fixen + v1→v2-Migrator

**Datum:** 2026-05-02
**Branch:** `feat/layer-0-task-02a-schema-version-drift`
**Refs:** [`PLAN.md`](../PLAN.md) Layer 0 Task 02, GitHub-Issue #107
**Auto-Close:** **nein** — #107 schließt erst mit Sub-Slice 02b/02c (Pydantic-Boundary-Validierung)

## Ausgangslage

Der ChatGPT-Audit hat einen `schema_version`-Drift zwischen Init- und Lade-/Export-Pfad belegt. **Wichtige Korrektur** zum vorherigen Plan-Review: Die Layer-0-Bundle-Dateien (Pydantic-Contracts, Zod-Spiegel, Schema-Dump-CLI, CI-Gate, Subagenten, Slash-Commands) sind **nicht auf `origin/main` committed** — sie liegen nur als untracked Files im Hauptrepo-Working-Tree (vermutlich aus `agora-layer0-bundle.zip` entpackt). `git ls-files backend/app/contracts/` und `git log --all -- backend/app/contracts/__init__.py` sind beide leer. Sub-Slice 02a baut deshalb auf `origin/main` ohne Pydantic-Contracts und hat keine Import-Abhängigkeit zu ihnen — der Migrator steht für sich. Layer-0-Bundle-Commit folgt als eigener Slice (Task 01/03/04 aus PLAN.md), bevor 02b/02c die Pydantic-Boundary-Validierung verdrahten.

Der echte Code in `report_agent.py` und `api/report.py` zieht weiter `schema_version=1` durch:

- [`backend/app/services/report_agent.py:184`](../backend/app/services/report_agent.py:184) — `_init_evidence_map` setzt `schema_version=2` (korrekt)
- [`backend/app/services/report_agent.py:564`](../backend/app/services/report_agent.py:564) — `setdefault("schema_version", 1)` (Drift)
- [`backend/app/services/report_agent.py:567`](../backend/app/services/report_agent.py:567) — neue Section-Einträge mit `schema_version=1` (Drift)
- [`backend/app/services/report_agent.py:1127`](../backend/app/services/report_agent.py:1127) — Default beim Laden ohne persistierte Map: `schema_version=1` (Drift)
- [`backend/app/api/report.py:379`](../backend/app/api/report.py:379) — `EXPORT_SCHEMA_VERSION = 1`

`PLAN.md` Teil D.2 sieht für #107 zusätzlich einen Migrator vor:

```python
def migrate_v1_to_v2(raw: dict) -> dict:
    if raw.get("schema_version", 1) == 2:
        return raw
    raw["schema_version"] = 2
    return raw
```

## Scope dieses Sub-Slice

Genau **ein Commit**, kleinster ehrlicher Schritt aus PLAN.md Task 02:

1. Migrator anlegen ([`backend/app/services/evidence_migrations.py`](../backend/app/services/evidence_migrations.py)) — in-place wie im Plan-Snippet, idempotent, hebt auch Section-`schema_version`.
2. Drift-Konstanten fixen (4 Stellen, alle aus dem Audit-Beleg).
3. Migrator beim **Laden** und beim **Export** einhängen, damit alte v1-Reports lesbar bleiben.
4. Bestehender Export-Test (`test_report_export.py`) auf v2-Erwartung umstellen — er verifiziert jetzt zusätzlich, dass die Migration im Export-Pfad greift (`payload["evidence"]["schema_version"] == 2` obwohl `_persist_report` v1-Storage schreibt).
5. Neuer Migrations-Test (`test_evidence_migration.py`).

**Out of Scope (folgt in 02b/02c):**

- Pydantic-Validation am Flask-Boundary in `api/report.py` (`ReportContract.model_validate(...)`).
- Pydantic-Validation am Generator-Output (`ReportAgent.generate_report` Rückgabe).
- Persistenz-Round-Trip im `ReportManager.save_evidence_map`/`get_evidence_map` (Pre-Save-/Post-Load-Validation).
- Round-Trip-Test gegen echte v1-Reports aus Prod-Backup (kein Backup vorhanden, daher synthetische Fixtures).

## Diff

### Neu

- [`backend/app/services/evidence_migrations.py`](../backend/app/services/evidence_migrations.py) — `CURRENT_SCHEMA_VERSION = 2`, `migrate_v1_to_v2(raw) -> raw`. In-place-Mutation entspricht dem Plan-Snippet, hebt zusätzlich `sections[*].schema_version`.
- [`backend/tests/test_evidence_migration.py`](../backend/tests/test_evidence_migration.py) — 8 Cases:
  - `test_current_schema_version_is_2`
  - `test_migrate_none_returns_none`
  - `test_migrate_v1_lifts_to_v2`
  - `test_migrate_v2_is_idempotent`
  - `test_migrate_missing_schema_version_treated_as_v1`
  - `test_migrate_handles_missing_sections_key`
  - `test_migrate_handles_null_sections`
  - `test_migrate_round_trip_preserves_claim_payload`

### Geändert

- [`backend/app/services/report_agent.py`](../backend/app/services/report_agent.py)
  - Import von `CURRENT_SCHEMA_VERSION` und `migrate_v1_to_v2` aus dem neuen Modul.
  - Z.564 `setdefault("schema_version", 1)` → `setdefault("schema_version", CURRENT_SCHEMA_VERSION)`.
  - Z.567 Section-Entry `"schema_version": 1` → `CURRENT_SCHEMA_VERSION`.
  - Z.1126 `ReportManager.get_evidence_map(report_id) or {…}` → `migrate_v1_to_v2(ReportManager.get_evidence_map(report_id)) or {…}`. Default-Branch (`or {…}`) zieht jetzt v2.
- [`backend/app/api/report.py`](../backend/app/api/report.py)
  - Import von `CURRENT_SCHEMA_VERSION` und `migrate_v1_to_v2`.
  - Z.379 `EXPORT_SCHEMA_VERSION = 1` → `EXPORT_SCHEMA_VERSION = CURRENT_SCHEMA_VERSION`.
  - JSON-Export-Payload nutzt `migrate_v1_to_v2(ReportManager.get_evidence_map(report_id))` statt direktem Read; alte persistierte v1-Reports werden also v2-konsistent ausgeliefert.
- [`backend/tests/test_report_export.py`](../backend/tests/test_report_export.py)
  - `test_export_json_returns_combined_envelope` assertet jetzt `payload["schema_version"] == 2` und zusätzlich `payload["evidence"]["schema_version"] == 2`. Die Fixture in `_persist_report` schreibt **bewusst v1** in den Storage, damit der Test den Migrationspfad mit-deckt.

## Verifikation

Aus dem Worktree-Working-Tree (`feat/layer-0-task-02a-schema-version-drift`, Basis `origin/main`):

- `uv run pytest tests/test_evidence_migration.py -v` → **8 passed** (neue Cases).
- `uv run pytest tests/test_evidence_migration.py tests/test_report_export.py tests/test_report_manager.py -v` → **27 passed**.
- `uv run pytest` (Volltest backend) → **886 passed, 9 skipped** in 79 s. Skips orthogonal: 2 × Redis (`test_event_bus_redis`, `test_subprocess_redis_bridge`, weil `TEST_REDIS_URL` nicht gesetzt) plus 7 × Compose-Snapshot (`.env` im Worktree fehlt — `docker compose config` braucht es).
- `rg "schema_version.*1" backend/app/` (im Worktree) → **leer** (Akzeptanzkriterium aus PLAN.md Master-Issue erfüllt).
- `rg "EXPORT_SCHEMA_VERSION = 1" backend/` → **leer**.

Layer-0-Contracts-Tests (`tests/contracts/`) existieren auf `origin/main` nicht und sind deshalb hier kein Verifikationspunkt — sie kommen mit dem Layer-0-Bundle-Slice (Tasks 01/03/04 aus PLAN.md), bevor 02b/02c die Pydantic-Boundary-Validierung verdrahten.

## Issue- und Milestone-Mapping

| Issue | Status nach 02a | Begründung |
|---|---|---|
| #107 — Schema-Migration v1→v2 | offen, `Refs #107` (kein Auto-Close) | Migrator existiert + ist im Generator-Lade-Pfad und im Export-Pfad eingehängt. **Persist-Boundary** im `ReportManager` und **Pydantic-Validation am API-Boundary** folgen in 02b/02c — erst dann gilt der Issue als geschlossen. |
| PLAN.md Task 02 (Master) | Sub-Slice 02a done | 02b: API-Boundary in `api/report.py` validiert Response durch `ReportContract`. 02c: `report_agent.generate_report` validiert Generator-Output durch Pydantic-Modelle. |

## Folge-Sub-Slices

- **02b** — Pydantic-`ReportContract.model_validate(...)` als Response-Gate in `api/report.py` (Endpoints `GET /api/report/<id>/evidence`, `GET .../export?format=json`); `ReportManager.get_evidence_map` ruft Migrator beim Laden, sodass auch andere Konsumenten v2-konsistent sehen.
- **02c** — Pydantic-Validation am Generator-Output (`report_agent.generate_report`) plus `PersonaQuotaPlan`-Validation an der Persona-Generation-Boundary. Schließt #107.

## Notizen

- Plan-Snippet aus D.2 verlangt In-Place-Mutation; übernommen, weil PLAN.md das so spezifiziert. Defensive Kopien wären eine semantische Abweichung.
- Der Test `test_export_json_returns_combined_envelope` testet jetzt **implizit** den Migrator. Bewusste Wahl: doppelte Coverage gegen Regression im Export-Pfad.
- `tests/test_report_manager.py:251` (`test_evidence_map_round_trip_updates_report_meta`) hat eine v1-Fixture und prüft Section-/Claim-Felder, **nicht** `schema_version`. Bleibt grün (Migration läuft im Generator-Lade-Pfad, der Test ruft direkt `ReportManager.get_evidence_map` und assertet auf Felder, die der Migrator nicht anfasst). Migration im `ReportManager` selbst ist 02b-Scope.
