"""Contract-Tests für ``app.repositories.run_repository`` (#1579).

Prüft die Invarianten, die der Port in seinen Docstrings festschreibt, gegen
``FileRunRepository`` — den einen heutigen Adapter. Der PostgreSQL-Adapter aus
#1587 muss dieselben Zusagen einhalten; diese Datei ist die Referenz dafür.

Jede Fixture bekommt ihr eigenes ``tmp_path``, damit kein Test in das echte
Upload-Verzeichnis schreibt.

Drei Kerninvarianten:
1. ``get`` gibt ``None`` zurück für unbekannte IDs — kein Raise.
2. ``list_all`` sortiert nach ``updated_at`` absteigend.
3. Roundtrip eines realistischen Manifests (inkl. Lease-Felder in metadata)
   verliert kein Feld.

Lease-Felder (``worker_pid``, ``worker_token``, ``heartbeat_at``,
``lease_ttl_s``) dürfen NICHT als explizite Felder im ``RunRecord``-Vertrag
stehen — sie gehören in ``metadata`` (Runtime-State, nicht Port-Vertrag).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.contracts.run_record_contract import RunRecord
from app.repositories.run_repository import RunRepository, get_run_repository
from app.services.file_run_store import FileRunRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> FileRunRepository:
    """Isolierter Dateiadapter — jeder Test schreibt in sein eigenes tmp_path."""
    return FileRunRepository(str(tmp_path / "run_registry"))


# ---------------------------------------------------------------------------
# Hilfsfunktion: realistisches Manifest
# ---------------------------------------------------------------------------

_REALISTIC_MANIFEST: dict[str, Any] = {
    "run_id": "run_abc123def456",
    "run_type": "simulation_prepare",
    "entity_id": "sim_abc123def456",
    "parent_run_id": None,
    "replayed_from_run_id": None,
    "status": "completed",
    "progress": 100,
    "message": "Preparation complete",
    "message_key": "run.prepare_completed",
    "error": None,
    "started_at": "2026-01-01T12:00:00",
    "updated_at": "2026-01-01T12:05:00",
    "completed_at": "2026-01-01T12:05:00",
    "branch_label": "main",
    "termination_reason": "completed",
    "artifacts": {"report_id": "rep_abc123def456"},
    "resume_capability": {"checkpoint": "step_2"},
    "metadata": {
        # Lease-Felder: in metadata, NICHT im RunRecord-Vertrag
        "worker_pid": 12345,
        "worker_token": "tok_abc123",
        "heartbeat_at": "2026-01-01T12:04:00+00:00",
        "lease_ttl_s": 90,
        "project_id": "proj_abc123def456",
    },
    "linked_ids": {
        "simulation_id": "sim_abc123def456",
        "project_id": "proj_abc123def456",
    },
    "events": [
        {
            "timestamp": "2026-01-01T12:00:00",
            "type": "created",
            "status": "pending",
            "progress": 0,
            "message": "simulation_prepare created",
            "error": None,
            "details": {},
        },
        {
            "timestamp": "2026-01-01T12:05:00",
            "type": "updated",
            "status": "completed",
            "progress": 100,
            "message": "Preparation complete",
            "error": None,
            "details": {},
        },
    ],
}


# ---------------------------------------------------------------------------
# RunRecord-Vertrag: keine Lease-Felder auf Top-Level
# ---------------------------------------------------------------------------


def test_run_record_has_no_lease_fields_at_top_level():
    """Lease-Felder sind Runtime-State und gehören in ``metadata``.

    ``JobLease`` (``app/contracts/job_lease_contract.py``) serialisiert sich
    in ``metadata``-Keys — der Repository-Vertrag darf sie NICHT als
    Top-Level-Felder führen, sonst würde ein Postgres-Adapter sie falsch
    mappen.
    """
    from app.contracts.job_lease_contract import (
        HEARTBEAT_AT_KEY,
        LEASE_TTL_KEY,
        OWNER_PID_KEY,
        OWNER_TOKEN_KEY,
    )

    lease_keys = {OWNER_PID_KEY, OWNER_TOKEN_KEY, HEARTBEAT_AT_KEY, LEASE_TTL_KEY}
    record_fields = set(RunRecord.model_fields)

    assert not (lease_keys & record_fields), (
        f"Lease-Felder {lease_keys & record_fields!r} dürfen nicht im "
        "RunRecord-Vertrag stehen."
    )


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------


def test_run_record_roundtrip_preserves_all_top_level_fields():
    """Jedes Top-Level-Feld eines realistischen Manifests überlebt den Roundtrip.

    Gilt auch für Felder, die RunRecord über ``extra='allow'`` durchreicht
    (Forward-Kompatibilität für künftige Manifest-Felder).
    """
    record = RunRecord(**_REALISTIC_MANIFEST)
    dumped = record.model_dump()

    for key, value in _REALISTIC_MANIFEST.items():
        assert key in dumped, f"Feld {key!r} fehlt nach Roundtrip"
        assert dumped[key] == value, (
            f"Feld {key!r}: erwartet {value!r}, got {dumped[key]!r}"
        )


def test_run_record_roundtrip_preserves_metadata_lease_keys():
    """Lease-Felder in ``metadata`` überleben den Roundtrip unverändert."""
    record = RunRecord(**_REALISTIC_MANIFEST)
    dumped = record.model_dump()

    assert dumped["metadata"]["worker_pid"] == 12345
    assert dumped["metadata"]["worker_token"] == "tok_abc123"
    assert dumped["metadata"]["heartbeat_at"] == "2026-01-01T12:04:00+00:00"
    assert dumped["metadata"]["lease_ttl_s"] == 90


# ---------------------------------------------------------------------------
# get — None-Zusage
# ---------------------------------------------------------------------------


def test_get_returns_none_for_unknown_run_id(repo):
    """``get`` wirft nicht, wenn der Run nicht existiert."""
    assert repo.get("run_unbekannt") is None


def test_get_returns_record_after_save(repo):
    record = RunRecord(**_REALISTIC_MANIFEST)
    repo.save(record)

    loaded = repo.get(record.run_id)

    assert loaded is not None
    assert loaded.run_id == record.run_id
    assert loaded.status == "completed"


def test_get_returns_none_for_corrupt_file(repo, tmp_path):
    """Korruptes JSON → ``None``, kein Crash."""
    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "run_abc123def456.json").write_text("{ kaputtes JSON")

    repo_corrupt = FileRunRepository(str(registry_dir))
    assert repo_corrupt.get("run_abc123def456") is None


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


def test_save_persists_to_disk(repo, tmp_path):
    record = RunRecord(**_REALISTIC_MANIFEST)
    repo.save(record)

    registry_dir = tmp_path / "run_registry"
    assert (registry_dir / f"{record.run_id}.json").exists()


def test_save_returns_the_saved_record(repo):
    record = RunRecord(**_REALISTIC_MANIFEST)
    returned = repo.save(record)

    assert returned.run_id == record.run_id
    assert returned.status == record.status


def test_save_overwrites_previous_version(repo):
    original = RunRecord(**_REALISTIC_MANIFEST)
    repo.save(original)

    updated_data = dict(_REALISTIC_MANIFEST)
    updated_data["status"] = "failed"
    updated = RunRecord(**updated_data)
    repo.save(updated)

    loaded = repo.get(original.run_id)
    assert loaded is not None
    assert loaded.status == "failed"


# ---------------------------------------------------------------------------
# list_all — Sortierung und Vollständigkeit
# ---------------------------------------------------------------------------


def test_list_all_returns_newest_updated_first(repo):
    """``list_all`` sortiert nach ``updated_at`` absteigend."""
    older_data = dict(_REALISTIC_MANIFEST)
    older_data["run_id"] = "run_older000000"
    older_data["updated_at"] = "2026-01-01T10:00:00"
    repo.save(RunRecord(**older_data))

    newer_data = dict(_REALISTIC_MANIFEST)
    newer_data["run_id"] = "run_newer000000"
    newer_data["updated_at"] = "2026-06-01T10:00:00"
    repo.save(RunRecord(**newer_data))

    records = repo.list_all()

    run_ids = [r.run_id for r in records]
    assert run_ids.index("run_newer000000") < run_ids.index("run_older000000"), (
        "Neuerer Record muss vor älterem stehen"
    )


def test_list_all_is_empty_when_no_records_exist(repo):
    assert repo.list_all() == []


def test_list_all_skips_corrupt_files(repo, tmp_path):
    """Ein korruptes JSON darf die Liste nicht abbrechen."""
    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir(parents=True, exist_ok=True)

    # Eine gültige Datei
    record = RunRecord(**_REALISTIC_MANIFEST)
    repo2 = FileRunRepository(str(registry_dir))
    repo2.save(record)

    # Eine korrupte Datei
    (registry_dir / "run_kaputt000000.json").write_text("{ kaputt")

    records = repo2.list_all()
    run_ids = [r.run_id for r in records]
    assert record.run_id in run_ids
    assert "run_kaputt000000" not in run_ids


def test_list_all_respects_limit(repo):
    for i in range(5):
        data = dict(_REALISTIC_MANIFEST)
        data["run_id"] = f"run_{i:012d}"
        repo.save(RunRecord(**data))

    records = repo.list_all(limit=3)
    assert len(records) == 3


# ---------------------------------------------------------------------------
# Pfadsicherheit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "boesartig",
    [
        "../anderswo",
        "../../etc",
        "/etc/passwd",
        "run_x/../../anderswo",
    ],
)
def test_traversal_id_never_reaches_filesystem(repo, boesartig):
    """Tiefen-Verteidigung: die Ablage prüft selbst, nicht nur die API."""
    with pytest.raises(ValueError):
        repo.get(boesartig)


# ---------------------------------------------------------------------------
# Protokoll-Konformität der Fabrik
# ---------------------------------------------------------------------------


def test_factory_returns_something_satisfying_the_port_protocol(tmp_path):
    repository = get_run_repository(registry_dir=str(tmp_path))

    assert isinstance(repository, RunRepository)


def test_factory_uses_registry_dir_it_is_given(tmp_path):
    """``registry_dir`` wird tatsächlich als Ablageort verwendet."""
    registry_dir = tmp_path / "custom_registry"
    repository = get_run_repository(registry_dir=str(registry_dir))

    record = RunRecord(**_REALISTIC_MANIFEST)
    repository.save(record)

    assert (registry_dir / f"{record.run_id}.json").exists()


# ---------------------------------------------------------------------------
# Altbestand und Dateiformat: der Port darf keinen Run verschwinden lassen
# und das Manifest nicht still umschreiben
# ---------------------------------------------------------------------------


def test_legacy_manifest_with_nonstandard_values_stays_readable_and_listed(tmp_path):
    """Vor dem Port akzeptierte der Lesepfad jedes Dict. Ein Manifest mit
    Alt-Status, fehlenden Feldern und ``progress`` ausserhalb 0..100 darf
    nicht als "fehlend" aus der Liste fallen."""
    import json

    legacy = {"run_id": "run_legacy", "status": "running", "progress": 150}
    (tmp_path / "run_legacy.json").write_text(json.dumps(legacy), encoding="utf-8")
    repo = FileRunRepository(str(tmp_path))

    record = repo.get("run_legacy")

    assert record is not None
    assert record.status == "running"
    assert [r.run_id for r in repo.list_all()] == ["run_legacy"]


def test_save_writes_the_manifest_unchanged(tmp_path):
    """Nicht gesetzte Vorgabewerte duerfen nicht als neue Keys in der Datei
    (und damit in API-Antworten, die das Manifest durchreichen) landen."""
    import json

    manifest = {
        "run_id": "run_shape",
        "run_type": "report",
        "entity_id": "rep_1",
        "status": "processing",
        "progress": 101,
        "started_at": "2026-09-24T10:00:00",
        "updated_at": "2026-09-24T10:00:00",
        "custom_field": {"kept": True},
    }
    FileRunRepository(str(tmp_path)).save(RunRecord(**manifest))

    on_disk = json.loads((tmp_path / "run_shape.json").read_text(encoding="utf-8"))
    assert on_disk == manifest
