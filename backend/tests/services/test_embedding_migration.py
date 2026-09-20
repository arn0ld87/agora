"""Tests fuer ``EmbeddingMigrationService`` (Onboarding Slice 4.3)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
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
    # Die neue Index-Version wurde im Store angelegt, aber noch nicht
    # aktiv — der Switch erfolgt erst nach erfolgreichem run() (Slice 2.2,
    # #1417: das ist der Regressionsschutz gegen den P1, dass ein
    # laufendes Re-Embedding den Betrieb vorzeitig umschaltet).
    index = store.get_index_version(1)
    assert index is not None
    assert index.status == "building"


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


def test_run_passes_configuration_and_persists_checkpoints(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    _seed_probed_configuration(store)
    seen: dict[str, object] = {}

    class _Checkpointing:
        def run(self, *args, **kwargs) -> EmbeddingMigrationStatus:
            progress = args[3]
            seen["configuration_id"] = kwargs["configuration"].id
            kwargs["checkpoint"](
                progress.model_copy(
                    update={
                        "total": 4,
                        "processed": 2,
                        "last_processed_id": "uuid-001",
                    }
                )
            )
            return "completed"

    service = EmbeddingMigrationService(
        store=store, re_embedder=_Checkpointing(), now=lambda: fixed_now
    )
    job = service.start("emb-1")
    final = service.run(job.id)

    assert seen["configuration_id"] == "emb-1"
    assert final.status == "completed"
    # Der Checkpoint wurde persistiert und ueberlebt bis in den Endzustand.
    assert final.progress.total == 4
    assert final.progress.processed == 2
    assert final.progress.last_processed_id == "uuid-001"


def test_run_resumes_job_stuck_in_running(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    """Crash-Recovery: ein Job in 'running' darf erneut ausgefuehrt werden.

    Der Re-Embedder bekommt dabei den zuletzt persistierten Progress
    inklusive ``last_processed_id`` und setzt dort fort.
    """
    _seed_probed_configuration(store)
    received: dict[str, object] = {}

    class _Recorder:
        def run(self, *args, **kwargs) -> EmbeddingMigrationStatus:
            received["last_processed_id"] = args[3].last_processed_id
            return "completed"

    service = EmbeddingMigrationService(
        store=store, re_embedder=_Recorder(), now=lambda: fixed_now
    )
    job = service.start("emb-1")

    # Simulierter Crash: Job haengt in 'running' mit Checkpoint-Progress.
    running = service.get_job(job.id)
    assert running is not None
    stuck = running.model_copy(
        update={
            "status": "running",
            "progress": running.progress.model_copy(
                update={
                    "total": 10,
                    "processed": 6,
                    "last_processed_id": "uuid-005",
                    "started_at": fixed_now,
                }
            ),
        }
    )
    service._save_job(stuck)  # noqa: SLF001 — Testaufbau fuer Crash-Zustand

    final = service.run(job.id)

    assert final.status == "completed"
    assert received["last_processed_id"] == "uuid-005"
    # started_at bleibt der urspruengliche Wert, kein Neustart der Uhr.
    assert final.progress.started_at == fixed_now


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


# ----------------------------------------------------------------------
# Cutover (Slice 2.2, #1417): Ziel-Version bleibt 'building' bis zum
# erfolgreichen Switch, die alte Version bleibt bis dahin aktiv. Das ist
# der Regressionsschutz gegen den P1, dass ein laufendes Re-Embedding
# den Betrieb vorzeitig auf einen leeren/unvollstaendigen Index umschaltet.
# ----------------------------------------------------------------------


def _run_first_migration_to_active(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> EmbeddingMigrationService:
    """Bringt eine erste (Cold-Start-)Migration vollstaendig durch, damit
    Version 1 aktiv ist und ein zweiter Cutover getestet werden kann.
    """
    _seed_probed_configuration(store)
    service = EmbeddingMigrationService(store=store, now=lambda: fixed_now)
    job = service.start("emb-1")
    service.run(job.id)
    # Konfiguration zurueck auf 'probed' setzen, damit ein zweiter
    # Migrationslauf ueberhaupt gestartet werden darf (start() verlangt
    # status == 'probed').
    store.update_configuration_status("emb-1", status="probed")
    return service


def test_active_index_stays_old_while_migration_is_in_progress(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    """Regressionstest: ``start()`` allein darf den Betrieb nicht
    umschalten. Nach ``start()`` (vor ``run()``) liefert
    ``get_active_index_version()`` weiterhin die alte Version, und die
    kanonische Auflösung (Slice 2.1) weiterhin deren Namen.
    """
    service = _run_first_migration_to_active(store, fixed_now)
    v1 = store.get_index_version(1)
    assert v1 is not None and v1.status == "active"

    job = service.start("emb-1")
    assert job.target_index_version == 2

    active = store.get_active_index_version()
    assert active is not None
    assert active.version == 1

    entity_index, entity_property = store.resolve_active_entity_index()
    assert entity_index == v1.index_name
    assert entity_property == v1.property_key

    v2 = store.get_index_version(2)
    assert v2 is not None
    assert v2.status == "building"


def test_switch_activates_new_version_and_supersedes_old(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    service = _run_first_migration_to_active(store, fixed_now)
    job = service.start("emb-1")
    final = service.run(job.id)

    assert final.status == "completed"
    v1 = store.get_index_version(1)
    v2 = store.get_index_version(2)
    assert v1 is not None and v1.status == "superseded"
    assert v2 is not None and v2.status == "active"

    active = store.get_active_index_version()
    assert active is not None and active.version == 2

    entity_index, entity_property = store.resolve_active_entity_index()
    assert entity_index == v2.index_name
    assert entity_property == v2.property_key


def test_failed_index_validation_blocks_switch_and_rolls_back_target(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    """Der Ziel-Index ist laut Validator nicht ONLINE -> kein Switch, der
    alte Index bleibt aktiv, der Job endet 'failed'.
    """
    _run_first_migration_to_active(store, fixed_now)
    always_offline = EmbeddingMigrationService(
        store=store,
        index_validator=lambda index_name: False,
        now=lambda: fixed_now,
    )
    job = always_offline.start("emb-1")
    final = always_offline.run(job.id)

    assert final.status == "failed"
    assert "ONLINE" in (final.error_message or "")

    v1 = store.get_index_version(1)
    v2 = store.get_index_version(2)
    assert v1 is not None and v1.status == "active"
    assert v2 is not None and v2.status == "rolled_back"

    config = store.get_configuration("emb-1")
    assert config is not None
    assert config.status == "probed", "kein Switch — Konfiguration bleibt unveraendert"
    assert config.index_version == 1


def test_cancel_during_second_migration_keeps_old_index_active(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    service = _run_first_migration_to_active(store, fixed_now)
    job = service.start("emb-1")

    cancelled = service.cancel(job.id)

    assert cancelled.status == "rolled_back"
    v1 = store.get_index_version(1)
    v2 = store.get_index_version(2)
    assert v1 is not None and v1.status == "active"
    assert v2 is not None and v2.status == "rolled_back"
