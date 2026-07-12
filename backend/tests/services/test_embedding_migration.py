"""Tests fuer ``EmbeddingMigrationService`` (Onboarding Slice 4.3)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingMigrationJob,
    EmbeddingMigrationProgress,
    EmbeddingMigrationStatus,
)
from app.services.embedding_configuration_store import EmbeddingConfigurationStore
from app.services.embedding_migration import EmbeddingMigrationService


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 7, 12, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> EmbeddingConfigurationStore:
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    return EmbeddingConfigurationStore(data_dir=tmp_path)


def _seed_probed_configuration(
    store: EmbeddingConfigurationStore, *, configuration_id: str = "emb-1"
) -> EmbeddingConfiguration:
    return store.upsert_configuration(
        configuration_id=configuration_id,
        provider_connection_id="conn-1",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
        status="probed",
    )


# ----------------------------------------------------------------------
# start
# ----------------------------------------------------------------------


def test_start_creates_pending_job(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    _seed_probed_configuration(store)
    service = EmbeddingMigrationService(store=store, now=lambda: fixed_now)
    job = service.start("emb-1")

    assert job.status == "pending"
    assert job.configuration_id == "emb-1"
    assert job.target_index_version == 1
    # source_index_version=0 ist der Cold-Start-Sentinel: es gibt
    # noch keinen Quell-Index, von dem kopiert werden kann.
    assert job.source_index_version == 0
    assert job.error_message is None
    assert job.progress.total == 0
    # Die neue Index-Version wurde im Store angelegt.
    index = store.get_index_version(1)
    assert index is not None
    assert index.status == "active"


def test_start_with_unknown_configuration_raises(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    service = EmbeddingMigrationService(store=store, now=lambda: fixed_now)
    with pytest.raises(KeyError):
        service.start("emb-bogus")


def test_start_rejects_configuration_not_in_probed_status(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    store.upsert_configuration(
        configuration_id="emb-failed",
        provider_connection_id="conn-1",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
        status="failed",
    )
    service = EmbeddingMigrationService(store=store, now=lambda: fixed_now)
    with pytest.raises(ValueError):
        service.start("emb-failed")


def test_start_is_idempotent_for_running_job(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    _seed_probed_configuration(store)
    service = EmbeddingMigrationService(store=store, now=lambda: fixed_now)
    service.start("emb-1")
    with pytest.raises(ValueError):
        service.start("emb-1")


# ----------------------------------------------------------------------
# run
# ----------------------------------------------------------------------


def test_run_completes_job_and_switches_configuration_to_active(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    _seed_probed_configuration(store)
    service = EmbeddingMigrationService(store=store, now=lambda: fixed_now)
    job = service.start("emb-1")

    completed = service.run(job.id)

    assert completed.status == "completed"
    assert completed.progress.finished_at == fixed_now
    config = store.get_configuration("emb-1")
    assert config is not None
    assert config.status == "active"
    assert config.index_version == 1


def test_run_with_non_pending_job_raises(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    _seed_probed_configuration(store)
    service = EmbeddingMigrationService(store=store, now=lambda: fixed_now)
    job = service.start("emb-1")
    service.run(job.id)  # -> completed

    with pytest.raises(ValueError):
        service.run(job.id)


def test_run_propagates_re_embedder_exception_as_failed(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    _seed_probed_configuration(store)

    class _Exploder:
        def run(self, *args, **kwargs) -> EmbeddingMigrationStatus:
            raise RuntimeError("simulated neo4j failure")

    service = EmbeddingMigrationService(
        store=store, re_embedder=_Exploder(), now=lambda: fixed_now
    )
    job = service.start("emb-1")
    final = service.run(job.id)

    assert final.status == "failed"
    assert "simulated neo4j failure" in (final.error_message or "")


def test_run_with_failed_re_embedder_result_keeps_old_index_active(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    _seed_probed_configuration(store)

    class _Failing:
        def run(self, *args, **kwargs) -> EmbeddingMigrationStatus:
            return "failed"

    service = EmbeddingMigrationService(
        store=store, re_embedder=_Failing(), now=lambda: fixed_now
    )
    job = service.start("emb-1")
    final = service.run(job.id)

    assert final.status == "failed"
    config = store.get_configuration("emb-1")
    assert config is not None
    assert config.status == "probed", "alter Index bleibt aktiv"


# ----------------------------------------------------------------------
# cancel
# ----------------------------------------------------------------------


def test_cancel_rolls_back_job_and_target_index(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    _seed_probed_configuration(store)
    service = EmbeddingMigrationService(store=store, now=lambda: fixed_now)
    job = service.start("emb-1")

    rolled_back = service.cancel(job.id)

    assert rolled_back.status == "rolled_back"
    assert "Operator-Abbruch" in (rolled_back.error_message or "")
    target_index = store.get_index_version(1)
    assert target_index is not None
    assert target_index.status == "rolled_back"


def test_cancel_of_completed_job_raises(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    _seed_probed_configuration(store)
    service = EmbeddingMigrationService(store=store, now=lambda: fixed_now)
    job = service.start("emb-1")
    service.run(job.id)

    with pytest.raises(ValueError):
        service.cancel(job.id)


# ----------------------------------------------------------------------
# read
# ----------------------------------------------------------------------


def test_list_jobs_returns_all_jobs(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    _seed_probed_configuration(store, configuration_id="emb-1")
    store.upsert_configuration(
        configuration_id="emb-2",
        provider_connection_id="conn-1",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
        status="probed",
    )
    service = EmbeddingMigrationService(store=store, now=lambda: fixed_now)
    service.start("emb-1")
    service.start("emb-2")

    all_jobs = service.list_jobs()
    assert len(all_jobs) == 2

    only_first = service.list_jobs(configuration_id="emb-1")
    assert len(only_first) == 1
    assert only_first[0].configuration_id == "emb-1"


def test_get_job_returns_none_for_unknown(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    service = EmbeddingMigrationService(store=store, now=lambda: fixed_now)
    assert service.get_job("job-bogus") is None
