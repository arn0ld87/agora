"""Tests für Graph-Build-Resume (Issue #1472b).

Deckt drei Ebenen ab:

1. ``GraphBuilderService.add_text_batches`` — ``checkpoint_callback`` läuft
   für jeden committeten Chunk (Normalfall UND Cancel-Nachsammeln) und ein
   Schreibfehler darin propagiert sichtbar statt zu verschwinden.
2. ``graph_build_checkpoint`` — reine Validierungs-/Entscheidungsfunktionen
   (``checkpoint_is_resumable``, ``resume_capability_for_checkpoint``,
   ``resume_capability_for_run``): geänderte Chunk-Parameter machen einen
   Checkpoint ungültig, ein fehlender/nicht passender Checkpoint bietet
   ``resume`` nie fälschlich an.
3. ``GraphBuildService.resume_graph_build`` — der produktive Resume-Pfad:
   bereits abgeschlossene Chunks werden NICHT erneut an
   ``add_text_batches`` übergeben (das ist der Beleg dafür, dass die
   teuren NER-/Embedding-Aufrufe nicht nochmal laufen und dass Neo4j keine
   Dubletten-Episoden/-Relationen bekommt — deren MERGE-Schlüssel ist eine
   je Aufruf frisch generierte UUID, kein inhaltlicher Schlüssel), kein
   erneutes ``create_graph``, Checkpoint wird bei Erfolg gelöscht und ein
   Checkpoint-Schreibfehler beendet den Run sichtbar als ``failed``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.contracts.graph_build_checkpoint_contract import GraphBuildCheckpoint
from app.models.project import ProjectStatus
from app.services.graph_build import GraphBuildService
from app.services.graph_build_checkpoint import (
    checkpoint_is_resumable,
    resume_capability_for_checkpoint,
    resume_capability_for_run,
)
from app.services.graph_builder import GraphBuildCancelled, GraphBuilderService

PROJECT_ID = "proj_resume_1472b"


def _checkpoint(**overrides) -> GraphBuildCheckpoint:
    defaults = dict(
        graph_id="graph-resume-1",
        total_chunks=4,
        chunk_size=500,
        chunk_overlap=50,
        manifest_anchored=False,
        completed_chunk_indices=[0, 2],
        episode_uuids={"0": "ep-0", "2": "ep-2"},
        updated_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return GraphBuildCheckpoint(**defaults)


# ---------------------------------------------------------------------------
# 1. GraphBuilderService.add_text_batches — checkpoint_callback
# ---------------------------------------------------------------------------


class _FakeStorage:
    """Sequenzieller ``storage.add_text``-Stub (wie in test_graph_build_cancel.py)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def add_text(self, graph_id, chunk, **kwargs):
        self.calls.append(chunk)
        return f"episode-{chunk}"


def test_add_text_batches_checkpoint_callback_runs_per_chunk(monkeypatch):
    from app.config import Config

    monkeypatch.setattr(Config, "GRAPH_PARALLEL_CHUNKS", 1)
    storage = _FakeStorage()
    service = GraphBuilderService(storage=storage)

    recorded: list[tuple[int, str]] = []
    service.add_text_batches(
        "graph-x", ["c1", "c2", "c3"], batch_size=3,
        checkpoint_callback=lambda idx, uuid: recorded.append((idx, uuid)),
    )

    assert sorted(recorded) == [(0, "episode-c1"), (1, "episode-c2"), (2, "episode-c3")]


def test_add_text_batches_checkpoint_callback_error_propagates(monkeypatch):
    """Ein Checkpoint-Schreibfehler darf den Build nicht unbemerkt
    weiterlaufen lassen (Issue #1472b) — die Exception muss aus
    ``add_text_batches`` herauspropagieren."""
    from app.config import Config

    monkeypatch.setattr(Config, "GRAPH_PARALLEL_CHUNKS", 1)
    storage = _FakeStorage()
    service = GraphBuilderService(storage=storage)

    def _raising_checkpoint(idx, uuid):
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        service.add_text_batches(
            "graph-x", ["c1", "c2"], batch_size=3,
            checkpoint_callback=_raising_checkpoint,
        )


def test_add_text_batches_without_checkpoint_callback_unchanged():
    """``checkpoint_callback=None`` (Default) — Verhalten unverändert."""
    storage = _FakeStorage()
    service = GraphBuilderService(storage=storage)

    result = service.add_text_batches("graph-x", ["c1", "c2"], batch_size=3)

    assert sorted(result) == ["episode-c1", "episode-c2"]


def test_add_text_batches_checkpoint_callback_runs_for_nachgesammelte_chunks(monkeypatch):
    """Cancel-Zweig: auch nachgesammelte (bereits laufende) Chunks lösen
    ``checkpoint_callback`` aus — sonst würde ein Resume nach Abbruch genau
    diese Chunks erneut verarbeiten."""
    import time as _time

    from app.config import Config
    from app.services.sim.cancel_flag import clear_cancel, request_cancel

    run_id = "run_checkpoint_nachsammeln"
    clear_cancel(run_id)
    monkeypatch.setattr(Config, "GRAPH_PARALLEL_CHUNKS", 1)

    class _CancellingStorage(_FakeStorage):
        def add_text(self, graph_id, chunk, **kwargs):
            self.calls.append(chunk)
            if chunk == "c1":
                request_cancel(run_id)
            else:
                _time.sleep(0.05)
            return f"episode-{chunk}"

    storage = _CancellingStorage()
    service = GraphBuilderService(storage=storage)
    recorded: list[tuple[int, str]] = []

    try:
        with pytest.raises(GraphBuildCancelled):
            service.add_text_batches(
                "graph-x", ["c1", "c2", "c3", "c4"], batch_size=3, run_id=run_id,
                checkpoint_callback=lambda idx, uuid: recorded.append((idx, uuid)),
            )
    finally:
        clear_cancel(run_id)

    # c1 (Trigger) UND c2 (bereits laufend, nachgesammelt) müssen
    # gecheckpointed sein — c3/c4 wurden nie gestartet.
    recorded_chunks = {idx for idx, _uuid in recorded}
    assert 0 in recorded_chunks  # c1
    assert 1 in recorded_chunks  # c2, nachgesammelt
    assert len(recorded) == 2


# ---------------------------------------------------------------------------
# 2. graph_build_checkpoint — Validierung / Entscheidung
# ---------------------------------------------------------------------------


def test_checkpoint_is_resumable_true_for_matching_checkpoint():
    checkpoint = _checkpoint()
    assert checkpoint_is_resumable(
        checkpoint,
        graph_id="graph-resume-1",
        total_chunks=4,
        chunk_size=500,
        chunk_overlap=50,
        manifest_anchored=False,
    ) is True


def test_checkpoint_is_resumable_false_without_checkpoint():
    assert checkpoint_is_resumable(
        None, graph_id="graph-resume-1", total_chunks=4,
        chunk_size=500, chunk_overlap=50, manifest_anchored=False,
    ) is False


def test_checkpoint_is_resumable_false_without_graph_id():
    checkpoint = _checkpoint()
    assert checkpoint_is_resumable(
        checkpoint, graph_id=None, total_chunks=4,
        chunk_size=500, chunk_overlap=50, manifest_anchored=False,
    ) is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"graph_id": "graph-different"},
        {"chunk_size": 999},
        {"chunk_overlap": 999},
        {"manifest_anchored": True},
        {"total_chunks": 7},
        {"completed_chunk_indices": []},
    ],
)
def test_checkpoint_is_resumable_false_on_parameter_drift(overrides):
    """Geänderte Chunk-Parameter (oder ein leerer Checkpoint) machen den
    Checkpoint ungültig — ein Resume darauf muss sauber neu starten statt
    falsch übersprungene Chunks zu produzieren."""
    checkpoint = _checkpoint(**overrides)
    assert checkpoint_is_resumable(
        checkpoint,
        graph_id="graph-resume-1",
        total_chunks=4,
        chunk_size=500,
        chunk_overlap=50,
        manifest_anchored=False,
    ) is False


def test_resume_capability_for_checkpoint_none_is_restart():
    assert resume_capability_for_checkpoint(None)["action"] == "restart"


def test_resume_capability_for_checkpoint_empty_is_restart():
    assert resume_capability_for_checkpoint(_checkpoint(completed_chunk_indices=[]))["action"] == "restart"


def test_resume_capability_for_checkpoint_with_progress_is_resume():
    assert resume_capability_for_checkpoint(_checkpoint())["action"] == "resume"


def test_resume_capability_for_run_without_checkpoint_is_restart(monkeypatch, tmp_path):
    from app.models.project import ProjectManager

    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    run = {"linked_ids": {"project_id": PROJECT_ID, "graph_id": "graph-x"}}
    assert resume_capability_for_run(run)["action"] == "restart"


def test_resume_capability_for_run_missing_graph_id_is_restart():
    run = {"linked_ids": {"project_id": PROJECT_ID}}
    assert resume_capability_for_run(run)["action"] == "restart"


def test_resume_capability_for_run_with_matching_checkpoint_is_resume(monkeypatch, tmp_path):
    from app.models.project import ProjectManager
    from app.services.graph_build_checkpoint import save_checkpoint

    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    save_checkpoint(PROJECT_ID, _checkpoint(graph_id="graph-match"))

    run = {"linked_ids": {"project_id": PROJECT_ID, "graph_id": "graph-match"}}
    assert resume_capability_for_run(run)["action"] == "resume"


def test_resume_capability_for_run_with_mismatched_graph_id_is_restart(monkeypatch, tmp_path):
    from app.models.project import ProjectManager
    from app.services.graph_build_checkpoint import save_checkpoint

    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    save_checkpoint(PROJECT_ID, _checkpoint(graph_id="graph-old-attempt"))

    run = {"linked_ids": {"project_id": PROJECT_ID, "graph_id": "graph-new-attempt"}}
    assert resume_capability_for_run(run)["action"] == "restart"


# ---------------------------------------------------------------------------
# 3. GraphBuildService.resume_graph_build — produktiver Resume-Pfad
# ---------------------------------------------------------------------------


class _FakeResumeBuilder:
    """Spiegelt die im Resume-Pfad genutzte Teilmenge der Builder-API."""

    def __init__(self, *, cancel_effect=None):
        self.create_graph_calls = 0
        self.set_ontology_calls: list[tuple] = []
        self.add_text_batches_calls: list[dict] = []
        self.completed_graph_ids: list[str] = []
        self.incomplete_calls: list[tuple] = []
        self._cancel_effect = cancel_effect

    def create_graph(self, name: str) -> str:  # pragma: no cover — darf nie laufen
        self.create_graph_calls += 1
        return "graph-should-not-be-created"

    def set_ontology(self, graph_id, ontology) -> None:
        self.set_ontology_calls.append((graph_id, ontology))

    def add_text_batches(
        self, graph_id, chunks, batch_size, progress_callback,
        document_ids, chunk_ids, run_id, checkpoint_callback,
    ):
        self.add_text_batches_calls.append({
            "graph_id": graph_id,
            "chunks": list(chunks),
            "document_ids": list(document_ids),
            "chunk_ids": list(chunk_ids),
        })
        if self._cancel_effect is not None:
            raise self._cancel_effect
        # Simuliert reale Chunk-Verarbeitung: jeder verbleibende Chunk
        # committet und wird gecheckpointed — genau die Kopplung, die
        # ``record_checkpoint`` im Resume-Pfad konsumiert.
        for local_idx, chunk in enumerate(chunks):
            checkpoint_callback(local_idx, f"episode-{chunk}")
        return [f"episode-{c}" for c in chunks]

    def get_graph_data(self, graph_id):
        return {"node_count": 10, "edge_count": 6}

    def mark_graph_completed(self, graph_id) -> None:
        self.completed_graph_ids.append(graph_id)

    def mark_graph_incomplete(self, graph_id, reason=None) -> None:
        self.incomplete_calls.append((graph_id, reason))


def _run_resume(monkeypatch, tmp_path, builder: _FakeResumeBuilder, checkpoint: GraphBuildCheckpoint):
    from app.models.project import ProjectManager

    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))

    project = MagicMock()
    project.project_id = PROJECT_ID
    project.name = "Resume Project"
    project.status = ProjectStatus.FAILED
    project.ontology = {"entity_types": [], "edge_types": []}
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None

    task_manager = MagicMock()
    task_manager.create_task.return_value = "task-resume-1472b"

    container = MagicMock()
    container.graph_builder.return_value = builder

    run_creates: list[dict] = []
    run_updates: list[dict] = []

    def _fake_create_run(run_type, entity_id, **kwargs):
        run_id = "run_resume_new"
        record = {"run_id": run_id, "run_type": run_type, "entity_id": entity_id, **kwargs}
        run_creates.append(record)
        return record

    def _fake_update_run(run_id, **kwargs):
        record = {"run_id": run_id, **kwargs}
        run_updates.append(record)
        return record

    monkeypatch.setattr("app.services.graph_build.ProjectManager.get_project", lambda _id: project)
    monkeypatch.setattr("app.services.graph_build.ProjectManager.save_project", lambda _project: None)
    monkeypatch.setattr("app.services.graph_build.TaskManager", lambda: task_manager)
    monkeypatch.setattr("app.services.graph_build.run_registry.create_run", _fake_create_run)
    monkeypatch.setattr("app.services.graph_build.run_registry.update_run", _fake_update_run)
    monkeypatch.setattr("app.jobs.enqueue", lambda _name, fn, **_kw: fn())

    chunks = ["c0", "c1", "c2", "c3"]
    document_ids = [None, None, None, None]
    chunk_ids = [None, None, None, None]

    result = GraphBuildService.resume_graph_build(
        project_id=PROJECT_ID,
        parent_run_id="run_original_interrupted",
        checkpoint=checkpoint,
        chunks=chunks,
        document_ids=document_ids,
        chunk_ids=chunk_ids,
        container=container,
    )

    return {
        "result": result,
        "project": project,
        "task_manager": task_manager,
        "run_creates": run_creates,
        "run_updates": run_updates,
        "builder": builder,
    }


def test_resume_graph_build_skips_completed_chunks_and_reuses_graph(monkeypatch, tmp_path):
    """Kernbeleg: Chunks 0 und 2 sind laut Checkpoint fertig — sie dürfen
    NICHT nochmal an add_text_batches gehen (teure NER-/Embedding-Aufrufe
    UND Neo4j-Dubletten vermeiden), und es wird kein neuer Graph angelegt."""
    checkpoint = _checkpoint(completed_chunk_indices=[0, 2], episode_uuids={"0": "ep-0", "2": "ep-2"})
    builder = _FakeResumeBuilder()

    outcome = _run_resume(monkeypatch, tmp_path, builder, checkpoint)

    assert builder.create_graph_calls == 0, "Resume darf keinen neuen Graphen anlegen"
    assert len(builder.add_text_batches_calls) == 1
    call = builder.add_text_batches_calls[0]
    assert call["graph_id"] == "graph-resume-1"
    assert call["chunks"] == ["c1", "c3"], (
        "Nur die NICHT abgeschlossenen Chunks (Index 1, 3) dürfen verarbeitet werden"
    )

    assert outcome["project"].status == ProjectStatus.GRAPH_COMPLETED
    final_update = outcome["run_updates"][-1]
    assert final_update["status"] == "completed"


def test_resume_graph_build_clears_checkpoint_on_success(monkeypatch, tmp_path):
    from app.services.graph_build_checkpoint import load_checkpoint, save_checkpoint

    checkpoint = _checkpoint(completed_chunk_indices=[0, 2])
    save_checkpoint(PROJECT_ID, checkpoint)
    builder = _FakeResumeBuilder()

    _run_resume(monkeypatch, tmp_path, builder, checkpoint)

    assert load_checkpoint(PROJECT_ID) is None, (
        "Ein abgeschlossener Graph darf keinen Checkpoint mehr hinterlassen"
    )


def test_resume_graph_build_all_chunks_already_done_skips_add_text_batches(monkeypatch, tmp_path):
    """Alle 4 Chunks waren schon vor diesem Resume fertig — add_text_batches
    darf gar nicht erst aufgerufen werden."""
    checkpoint = _checkpoint(completed_chunk_indices=[0, 1, 2, 3])
    builder = _FakeResumeBuilder()

    outcome = _run_resume(monkeypatch, tmp_path, builder, checkpoint)

    assert builder.add_text_batches_calls == []
    assert outcome["project"].status == ProjectStatus.GRAPH_COMPLETED


def test_resume_graph_build_checkpoint_write_failure_ends_run_failed(monkeypatch, tmp_path):
    """Ein Checkpoint-Schreibfehler während des Resume-Durchlaufs muss den
    Run sichtbar als ``failed`` beenden statt still weiterzulaufen."""
    checkpoint = _checkpoint(completed_chunk_indices=[0, 2])
    builder = _FakeResumeBuilder()

    def _raise_save_checkpoint(_project_id, _checkpoint):
        raise OSError("disk full")

    from app.models.project import ProjectManager
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    # save_checkpoint wird in graph_build.py direkt importiert — dort patchen.
    monkeypatch.setattr("app.services.graph_build.save_checkpoint", _raise_save_checkpoint)

    outcome = _run_resume(monkeypatch, tmp_path, builder, checkpoint)

    assert outcome["project"].status == ProjectStatus.FAILED
    final_update = outcome["run_updates"][-1]
    assert final_update["status"] == "failed"
    assert "disk full" in final_update["message"]


def test_resume_graph_build_cancel_keeps_checkpoint_and_offers_resume_again(monkeypatch, tmp_path):
    checkpoint = _checkpoint(completed_chunk_indices=[0, 2])
    builder = _FakeResumeBuilder(cancel_effect=GraphBuildCancelled(["episode-c1"]))

    outcome = _run_resume(monkeypatch, tmp_path, builder, checkpoint)

    assert outcome["project"].status == ProjectStatus.GRAPH_INCOMPLETE
    final_update = outcome["run_updates"][-1]
    assert final_update["status"] == "stopped"
    assert final_update["termination_reason"] == "user_cancel"
    # Checkpoint hatte vor dem Cancel bereits Fortschritt (Index 0, 2) —
    # "resume" bleibt eine ehrliche Option, nicht "restart".
    assert final_update["resume_capability"]["action"] == "resume"
