"""Tests für ``_resume_or_restart_graph_build`` (app/api/runs.py, Issue #1472b).

Reine Dispatcher-Ebene: entscheidet, ob ein Checkpoint zum aktuellen
Build-Versuch passt (dann Resume) oder nicht (dann der bestehende
Restart-Pfad). ``_resume_graph_build``/``_restart_graph_build`` selbst sind
in ``tests/services/test_graph_build_resume.py`` bzw.
``tests/api/test_restart_graph_build_cancel.py`` abgedeckt — hier wird nur
geprüft, WELCHER Pfad gewählt wird, per Sentinel-Stubs.
"""

from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from app.contracts.graph_build_checkpoint_contract import GraphBuildCheckpoint
from app.models.project import ProjectStatus


def _fake_project(**overrides) -> SimpleNamespace:
    defaults = dict(
        project_id="proj_dispatch",
        name="Dispatch Project",
        status=ProjectStatus.FAILED,
        ontology={"entity_types": []},
        chunk_size=500,
        chunk_overlap=50,
        graph_id=None,
        graph_build_task_id=None,
        error=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _run(**overrides) -> dict:
    defaults = dict(
        run_id="run_interrupted",
        run_type="graph_build",
        entity_id="proj_dispatch",
        linked_ids={"project_id": "proj_dispatch", "graph_id": "graph-x"},
    )
    defaults.update(overrides)
    return defaults


def _dispatch(run: dict, *, checkpoint, chunks):
    from app.api.runs import _resume_or_restart_graph_build

    project = _fake_project()

    with ExitStack() as stack:
        mock_pm = stack.enter_context(patch("app.api.runs.ProjectManager"))
        mock_pm.get_project.return_value = project
        mock_pm.get_extracted_text.return_value = "extracted text " * 10

        stack.enter_context(patch("app.api.runs.load_checkpoint", return_value=checkpoint))
        stack.enter_context(
            patch(
                "app.api.runs.GraphBuildService.chunk_project_text",
                return_value=(chunks, [None] * len(chunks), [None] * len(chunks), False),
            )
        )
        restart_stub = stack.enter_context(
            patch("app.api.runs._restart_graph_build", return_value={"path": "restart"})
        )
        resume_stub = stack.enter_context(
            patch("app.api.runs._resume_graph_build", return_value={"path": "resume"})
        )

        result = _resume_or_restart_graph_build(run)

    return result, restart_stub, resume_stub


def test_dispatcher_uses_restart_without_any_checkpoint():
    run = _run()
    result, restart_stub, resume_stub = _dispatch(run, checkpoint=None, chunks=["c0", "c1"])

    assert result == {"path": "restart"}
    restart_stub.assert_called_once()
    resume_stub.assert_not_called()


def test_dispatcher_uses_restart_when_checkpoint_chunk_params_drifted():
    """Checkpoint stammt von einer anderen Chunk-Zerlegung (z. B. anderer
    chunk_size) — muss sauber auf restart zurückfallen, nicht falsch
    überspringen."""
    from datetime import UTC, datetime

    checkpoint = GraphBuildCheckpoint(
        graph_id="graph-x",
        total_chunks=99,  # passt nicht zur aktuellen Chunk-Zerlegung
        chunk_size=500,
        chunk_overlap=50,
        manifest_anchored=False,
        completed_chunk_indices=[0],
        episode_uuids={"0": "ep-0"},
        updated_at=datetime.now(UTC),
    )
    run = _run()
    result, restart_stub, resume_stub = _dispatch(run, checkpoint=checkpoint, chunks=["c0", "c1"])

    assert result == {"path": "restart"}
    restart_stub.assert_called_once()
    resume_stub.assert_not_called()


def test_dispatcher_uses_resume_when_checkpoint_matches():
    from datetime import UTC, datetime

    checkpoint = GraphBuildCheckpoint(
        graph_id="graph-x",
        total_chunks=2,
        chunk_size=500,
        chunk_overlap=50,
        manifest_anchored=False,
        completed_chunk_indices=[0],
        episode_uuids={"0": "ep-0"},
        updated_at=datetime.now(UTC),
    )
    run = _run()
    result, restart_stub, resume_stub = _dispatch(run, checkpoint=checkpoint, chunks=["c0", "c1"])

    assert result == {"path": "resume"}
    resume_stub.assert_called_once()
    restart_stub.assert_not_called()


def test_dispatcher_uses_restart_without_graph_id_linked():
    """Run ohne verknüpfte graph_id (Crash vor create_graph) hat nie einen
    Checkpoint zum Abgleichen — load_checkpoint wird also erst gar nicht
    fündig, aber die Route muss trotzdem sauber auf restart fallen."""
    run = _run(linked_ids={"project_id": "proj_dispatch"})
    result, restart_stub, resume_stub = _dispatch(run, checkpoint=None, chunks=["c0", "c1"])

    assert result == {"path": "restart"}
    restart_stub.assert_called_once()
    resume_stub.assert_not_called()
