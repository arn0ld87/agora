"""Tests für kooperativen Abbruch von ``graph_build`` (Plan B2).

Drei Ebenen:

1. ``GraphBuilderService.add_text_batches`` (services/graph_builder.py) —
   die ``as_completed``-Schleife muss bei gesetztem Cancel-Flag ausstehende
   Chunks verwerfen (``pool.shutdown(cancel_futures=True)``) und
   ``GraphBuildCancelled`` mit den bereits fertigen Episode-UUIDs werfen.
   Bereits laufende Chunks committen fertig — das ist akzeptiert.
2. ``Neo4jWriteMixin.mark_graph_incomplete`` (storage/neo4j_write.py) — Cypher
   setzt ``status='incomplete'`` + ``incomplete_reason``, analog
   ``mark_graph_failed``.
3. Der produktive Build-Pfad ``GraphBuildService.build_graph`` → ``build_task``
   (services/graph_build.py) — dieselbe Test-Harness wie
   ``test_graph_build_degradation_wiring.py``: der Fake-Builder spiegelt die
   echte Signatur explizit, damit ein weggefallenes Argument den Test mit
   ``TypeError`` bricht statt still zu bestehen.

Abgedeckte Szenarien:
  1  as_completed: Cancel mitten im Chunk-Durchlauf → GraphBuildCancelled,
     Teilliste der Episode-UUIDs, ausstehende Chunks werden nicht mehr
     verarbeitet
  2  as_completed: kein Cancel → alle Chunks normal verarbeitet (Baseline)
  3  as_completed: run_id=None → Verhalten unverändert (kein Check)
  4  mark_graph_incomplete: Cypher setzt status='incomplete' + reason
  5  build_task: Cancel VOR add_text_batches → kein add_text_batches-Aufruf,
     project.status=GRAPH_INCOMPLETE, Run stopped+user_cancel,
     delete_graph NIE aufgerufen
  6  build_task: Cancel WÄHREND add_text_batches (GraphBuildCancelled) →
     dieselben Endzustände, episode_count im Task-Ergebnis
  7  build_task: kein Cancel → Baseline bleibt GRAPH_COMPLETED (Regressionsnetz)
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.contracts.llm_routing_contract import ResolvedRoute
from app.models.project import ProjectStatus
from app.models.task import TaskStatus
from app.services.graph_build import GraphBuildService
from app.services.graph_builder import GraphBuildCancelled, GraphBuilderService
from app.services.sim.cancel_flag import clear_cancel, request_cancel

PROJECT_ID = "proj_cancel_b2"


def _unique_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def run_id():
    rid = _unique_run_id()
    clear_cancel(rid)
    yield rid
    clear_cancel(rid)


# ---------------------------------------------------------------------------
# 1. GraphBuilderService.add_text_batches — as_completed-Checkpoint
# ---------------------------------------------------------------------------


class _FakeStorage:
    """Minimaler ``storage.add_text``-Stub — sequenziell, deterministisch.

    ``GRAPH_PARALLEL_CHUNKS`` wird in den Tests auf 1 gepatcht, damit die
    Reihenfolge (und damit der Cancel-Zeitpunkt) reproduzierbar ist. Chunks
    außer dem "Cancel-Trigger" schlafen kurz: ohne das würde der einzige
    Worker-Thread nach dem Trigger-Chunk sofort weiterlaufen, bevor der
    Hauptthread (in ``as_completed``) überhaupt zum Cancel-Check kommt — bei
    einer synchronen Fake-Funktion ohne jede I/O gewinnt der Worker diesen
    Wettlauf verlässlich. Der Schlaf gibt dem GIL eine reale Chance, zum
    Hauptthread zu wechseln, bevor der Worker den nächsten Chunk aus der
    Queue holt — genau das Fenster, in dem ``pool.shutdown(cancel_futures=True)``
    im Produktionscode ausstehende Chunks noch verwerfen kann.
    """

    def __init__(self, *, cancel_after: "str | None" = None):
        self.calls: list[str] = []
        self._cancel_after = cancel_after

    def add_text(self, graph_id, chunk, **kwargs):
        self.calls.append(chunk)
        episode_id = f"episode-{chunk}"
        if self._cancel_after == chunk:
            request_cancel(self._run_id)
        else:
            import time

            time.sleep(0.05)
        return episode_id


def test_add_text_batches_cancel_mid_loop_raises_with_partial_uuids(monkeypatch, run_id):
    from app.config import Config

    # 1 Worker macht die Verarbeitungsreihenfolge deterministisch (kein
    # Wettlauf zwischen mehreren Chunks um freie Worker-Slots).
    monkeypatch.setattr(Config, "GRAPH_PARALLEL_CHUNKS", 1)

    storage = _FakeStorage(cancel_after="c1")
    storage._run_id = run_id
    service = GraphBuilderService(storage=storage)

    with pytest.raises(GraphBuildCancelled) as excinfo:
        service.add_text_batches(
            "graph-x", ["c1", "c2", "c3", "c4"], batch_size=3, run_id=run_id
        )

    assert len(storage.calls) < 4, (
        "Nach dem Cancel dürfen nicht mehr alle Chunks verarbeitet werden"
    )
    assert storage.calls[0] == "c1", "Der erste Chunk muss fertig committet worden sein"
    # Die Exception wird geworfen, sobald die ``as_completed``-Schleife den
    # ersten (gecancelten) Chunk verarbeitet hat — noch bevor ein eventuell
    # im Hintergrund bereits gestarteter zweiter Chunk (Restrisiko des
    # einzelnen Workers, s.o.) sein Ergebnis über ``future.result()``
    # einreihen konnte. Deterministisch ist deshalb nur, dass genau der
    # erste Chunk in der zurückgegebenen Liste steht.
    assert excinfo.value.episode_uuids == ["episode-c1"]


def test_add_text_batches_no_cancel_processes_all_chunks(run_id):
    """Baseline: run_id gesetzt, aber niemals gecancelt → normales Verhalten."""
    storage = _FakeStorage(cancel_after=None)
    service = GraphBuilderService(storage=storage)

    result = service.add_text_batches(
        "graph-x", ["c1", "c2", "c3"], batch_size=3, run_id=run_id
    )

    assert sorted(result) == ["episode-c1", "episode-c2", "episode-c3"]
    assert sorted(storage.calls) == ["c1", "c2", "c3"]


def test_add_text_batches_without_run_id_ignores_cancel_flag():
    """``run_id=None`` (Default) — das Cancel-Flag wird gar nicht erst geprüft."""
    storage = _FakeStorage(cancel_after=None)
    service = GraphBuilderService(storage=storage)

    result = service.add_text_batches("graph-x", ["c1", "c2"], batch_size=3)

    assert sorted(result) == ["episode-c1", "episode-c2"]


# ---------------------------------------------------------------------------
# 2. Neo4jWriteMixin.mark_graph_incomplete
# ---------------------------------------------------------------------------


def test_mark_graph_incomplete_sets_status_and_reason():
    from app.storage.neo4j_write import Neo4jWriteMixin

    captured_queries: list[str] = []
    captured_kwargs: list[dict] = []

    def _fake_call_with_retry(execute_write_fn, inner_fn, *args, **kwargs):
        mock_tx = MagicMock()

        def _capture_run(q, **kw):
            captured_queries.append(q)
            captured_kwargs.append(kw)

        mock_tx.run.side_effect = _capture_run
        inner_fn(mock_tx)

    mixin = object.__new__(Neo4jWriteMixin)  # type: ignore[arg-type]
    mixin._call_with_retry = _fake_call_with_retry  # type: ignore[attr-defined]

    mock_session = MagicMock()
    session_ctx = MagicMock()
    session_ctx.__enter__ = MagicMock(return_value=mock_session)
    session_ctx.__exit__ = MagicMock(return_value=False)
    mixin._get_session = MagicMock(return_value=session_ctx)  # type: ignore[attr-defined]

    Neo4jWriteMixin.mark_graph_incomplete(mixin, "graph-x", reason="user_cancel")

    combined = " ".join(captured_queries)
    assert "status" in combined
    assert "incomplete" in combined
    assert captured_kwargs[0]["reason"] == "user_cancel"
    assert captured_kwargs[0]["gid"] == "graph-x"


# ---------------------------------------------------------------------------
# 3. Produktiver Build-Pfad — GraphBuildService.build_graph -> build_task
# ---------------------------------------------------------------------------


class _FakeBuilder:
    """Spiegelt die echte ``add_text_batches``-Signatur explizit (wie in
    ``test_graph_build_degradation_wiring.py``) — ein im Produktionscode
    weggefallenes Argument bricht hier mit ``TypeError`` statt still zu
    bestehen.
    """

    def __init__(self, *, cancel_effect=None):
        self.completed_graph_ids: list[str] = []
        self.incomplete_calls: list[tuple] = []
        self.delete_calls: list[str] = []
        self.add_text_batches_called = False
        self._cancel_effect = cancel_effect

    def create_graph(self, name: str) -> str:
        return "graph-cancel-1"

    def set_ontology(self, graph_id, ontology) -> None:
        return None

    def add_text_batches(
        self,
        graph_id,
        chunks,
        batch_size,
        progress_callback,
        ner_extractor,
        degradations,
        extraction_tally,
        document_ids,
        chunk_ids,
        run_id,
    ):
        self.add_text_batches_called = True
        if self._cancel_effect is not None:
            raise self._cancel_effect
        return ["ep1", "ep2"]

    def get_graph_data(self, graph_id):
        return {"node_count": 10, "edge_count": 5}

    def assess_graph_quality_from_counts(self, **kwargs):
        return None

    def mark_graph_completed(self, graph_id) -> None:
        self.completed_graph_ids.append(graph_id)

    def mark_graph_incomplete(self, graph_id, reason=None) -> None:
        self.incomplete_calls.append((graph_id, reason))

    def delete_graph(self, graph_id) -> None:
        self.delete_calls.append(graph_id)

    def mark_graph_failed(self, graph_id, reason=None) -> None:
        pass


class _Router:
    def __init__(self, _run_id):
        pass

    def resolve(self, stage_id):
        return ResolvedRoute(
            stage=stage_id,
            provider_id="openai",
            model="gpt-4.1-mini",
            routing_version=1,
        )

    def lock_stage(self, *_args):
        return None


def _run_build(monkeypatch, builder: _FakeBuilder, *, run_id: str) -> dict:
    """Führt ``build_graph`` synchron aus (dieselbe Harness wie
    ``test_graph_build_degradation_wiring.py``) und gibt den ``run_registry``-
    Update-Verlauf plus Task-Manager-Mock zurück.
    """
    project = MagicMock()
    project.project_id = PROJECT_ID
    project.status = ProjectStatus.ONTOLOGY_GENERATED
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    project.chunk_size = 500
    project.chunk_overlap = 50
    project.ontology = {"entity_types": [], "edge_types": []}
    project.llm_profile_id = None
    project.ai_model_ref = None

    task_manager = MagicMock()
    task_manager.create_task.return_value = "task-cancel-1029"

    container = MagicMock()
    container.graph_builder.return_value = builder

    run_updates: list[dict] = []

    monkeypatch.setattr("app.services.graph_build.ProjectManager.get_project", lambda _id: project)
    monkeypatch.setattr("app.services.graph_build.ProjectManager.get_extracted_text", lambda _id: "text")
    monkeypatch.setattr("app.services.graph_build.ProjectManager.save_project", lambda _project: None)
    monkeypatch.setattr("app.services.graph_build.ProjectManager._get_project_dir", lambda _id: "/tmp/project")
    monkeypatch.setattr("app.services.graph_build.TaskManager", lambda: task_manager)
    monkeypatch.setattr(
        "app.services.graph_build.run_registry.create_run",
        lambda **_kwargs: {"run_id": run_id},
    )
    monkeypatch.setattr(
        "app.services.graph_build.run_registry.update_run",
        lambda rid, **kw: run_updates.append({"run_id": rid, **kw}),
    )
    monkeypatch.setattr("app.services.graph_build.seed_run_stage_routing", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.graph_build.StageModelRouter", _Router)
    monkeypatch.setattr("app.services.graph_build.resolve_route_api_key", lambda *_a: None)
    monkeypatch.setattr("app.services.graph_build.LLMClient.from_route", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr("app.services.graph_build.NERExtractor", lambda **_k: MagicMock())
    monkeypatch.setattr("app.services.graph_build.ArtifactLocator.existing_paths", lambda _paths: {})
    monkeypatch.setattr("app.services.graph_build.TextProcessor.split_text", lambda *_a, **_k: ["c1", "c2"])
    monkeypatch.setattr("app.jobs.enqueue", lambda _name, fn: fn())

    GraphBuildService.build_graph(
        project_id=PROJECT_ID,
        graph_name="Cancel graph",
        container=container,
    )

    return {
        "project": project,
        "task_manager": task_manager,
        "run_updates": run_updates,
        "builder": builder,
    }


def test_build_task_cancel_before_add_text_batches(monkeypatch, run_id):
    """Cancel-Flag schon vor dem Chunk-Durchlauf gesetzt."""
    request_cancel(run_id)
    builder = _FakeBuilder()

    result = _run_build(monkeypatch, builder, run_id=run_id)

    assert builder.add_text_batches_called is False, (
        "add_text_batches darf nach einem Cancel-Pre-Check nicht mehr laufen"
    )
    assert builder.incomplete_calls == [("graph-cancel-1", "user_cancel")]
    assert builder.delete_calls == [], "Kein Rollback/delete_graph im Cancel-Pfad"
    assert result["project"].status == ProjectStatus.GRAPH_INCOMPLETE
    assert result["project"].graph_id == "graph-cancel-1"

    result["task_manager"].complete_task.assert_called_once()
    task_result = result["task_manager"].complete_task.call_args.kwargs["result"]
    assert task_result["cancelled"] is True
    assert task_result["episode_count"] == 0

    # run_registry.update_run läuft zweimal: einmal "Graph created" (direkt
    # nach create_graph, vor dem Cancel-Checkpoint), einmal der finale
    # Abbruch-Endzustand — nur der zweite trägt status/termination_reason.
    assert len(result["run_updates"]) == 2
    update = result["run_updates"][-1]
    assert update["status"] == "stopped"
    assert update["termination_reason"] == "user_cancel"
    assert update["resume_capability"]["action"] == "restart"


def test_build_task_cancel_during_add_text_batches(monkeypatch, run_id):
    """Cancel-Flag wird erst mitten in ``add_text_batches`` erkannt
    (GraphBuildCancelled aus der as_completed-Schleife)."""
    builder = _FakeBuilder(cancel_effect=GraphBuildCancelled(["ep1"]))

    result = _run_build(monkeypatch, builder, run_id=run_id)

    assert builder.add_text_batches_called is True
    assert builder.incomplete_calls == [("graph-cancel-1", "user_cancel")]
    assert builder.delete_calls == []
    assert result["project"].status == ProjectStatus.GRAPH_INCOMPLETE

    task_result = result["task_manager"].complete_task.call_args.kwargs["result"]
    assert task_result["episode_count"] == 1
    assert task_result["cancelled"] is True

    assert len(result["run_updates"]) == 2
    update = result["run_updates"][-1]
    assert update["status"] == "stopped"
    assert update["termination_reason"] == "user_cancel"


def test_build_task_no_cancel_completes_normally(monkeypatch, run_id):
    """Regressionsnetz: ohne Cancel bleibt der Erfolgspfad unverändert."""
    builder = _FakeBuilder()

    result = _run_build(monkeypatch, builder, run_id=run_id)

    assert builder.add_text_batches_called is True
    assert builder.completed_graph_ids == ["graph-cancel-1"]
    assert builder.incomplete_calls == []
    assert builder.delete_calls == []
    assert result["project"].status == ProjectStatus.GRAPH_COMPLETED

    assert len(result["run_updates"]) == 2
    update = result["run_updates"][-1]
    assert update["status"] == "completed"
    assert "termination_reason" not in update
