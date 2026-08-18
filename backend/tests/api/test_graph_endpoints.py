"""Endpoint-Tests für ``app.api.graph`` — verifiziert die ApiErrorCode-Migration.

Fokus: jeder Error-Pfad liefert die richtige Envelope-Form
``{"success": false, "code": "<code>", "error": "..."}``. Frontend kann
sich auf ``code`` verlassen, der ``error``-Text bleibt menschenlesbar.

Enthält außerdem Tests für den progress_detail-Batch-Marker (Sub-Slice #137 SUB1).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import graph_bp
from app.container import AgoraContainer


VALID_PROJECT_ID = "proj_0123456789ab"
VALID_GRAPH_ID = "abcdef0123456789abcdef0123456789"
VALID_TASK_ID = "01234567-89ab-4def-8123-456789abcdef"


@pytest.fixture
def app(monkeypatch):
    # @require_scope ist aktiv, sobald AGORA_AUTH_TOKEN gesetzt ist. Diese
    # Endpunkt-Error-Tests prüfen Validierung/Mapping, nicht Auth — daher
    # erzwingen wir Open-Mode für die ganze Testdatei.
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    storage = MagicMock(name="Neo4jStorage")
    container = AgoraContainer(neo4j_storage=storage)
    flask_app = Flask(__name__)
    flask_app.config["AGORA_AUTH_TOKEN"] = ""
    flask_app.extensions = {"container": container, "neo4j_storage": storage}
    flask_app.register_blueprint(graph_bp, url_prefix="/api/graph")
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# --- INVALID_ID --------------------------------------------------------------


def test_get_project_invalid_id_returns_invalid_id_code(client):
    response = client.get("/api/graph/project/not-a-valid-id")
    payload = response.get_json()
    assert response.status_code == 400
    assert payload["success"] is False
    assert payload["code"] == "invalid_id"


def test_delete_project_invalid_id_returns_invalid_id_code(client):
    response = client.delete("/api/graph/project/not-a-valid-id")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_reset_project_invalid_id_returns_invalid_id_code(client):
    response = client.post("/api/graph/project/not-a-valid-id/reset")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_get_task_invalid_id_returns_invalid_id_code(client):
    response = client.get("/api/graph/task/garbage")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_get_graph_data_invalid_id_returns_invalid_id_code(client):
    response = client.get("/api/graph/data/not-valid")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_get_graph_snapshot_invalid_id_returns_invalid_id_code(client):
    response = client.get("/api/graph/snapshot/not-valid/0")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_get_graph_diff_invalid_id_returns_invalid_id_code(client):
    response = client.get("/api/graph/not-valid/diff?start_round=0&end_round=1")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_delete_graph_invalid_id_returns_invalid_id_code(client):
    response = client.delete("/api/graph/delete/not-valid")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


# --- VALIDATION_FAILED -------------------------------------------------------


def test_build_graph_missing_project_id_returns_validation_failed(client):
    response = client.post("/api/graph/build", json={})
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_get_graph_snapshot_negative_round_returns_validation_failed(client):
    # end_round < start_round → VALIDATION_FAILED
    response = client.get(f"/api/graph/{VALID_GRAPH_ID}/diff?start_round=2&end_round=1")
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_get_graph_diff_non_integer_rounds_returns_validation_failed(client):
    response = client.get(
        f"/api/graph/{VALID_GRAPH_ID}/diff?start_round=abc&end_round=def"
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


# --- NOT_FOUND ---------------------------------------------------------------


def test_get_project_not_found_returns_not_found_code(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.graph.ProjectManager.get_project",
        staticmethod(lambda _pid: None),
    )
    response = client.get(f"/api/graph/project/{VALID_PROJECT_ID}")
    payload = response.get_json()
    assert response.status_code == 404
    assert payload["code"] == "not_found"
    assert VALID_PROJECT_ID in payload["error"]


def test_get_task_not_found_returns_not_found_code(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.graph.TaskManager",
        lambda: MagicMock(get_task=MagicMock(return_value=None)),
    )
    response = client.get(f"/api/graph/task/{VALID_TASK_ID}")
    assert response.status_code == 404
    assert response.get_json()["code"] == "not_found"


# --- UNSUPPORTED_FORMAT ------------------------------------------------------


def test_export_unknown_format_returns_unsupported_format_code(client):
    response = client.get(f"/api/graph/{VALID_GRAPH_ID}/export?format=svg")
    assert response.status_code == 400
    assert response.get_json()["code"] == "unsupported_format"


# --- ONTOLOGY_MISSING --------------------------------------------------------


def test_build_graph_without_ontology_returns_ontology_missing(client, monkeypatch):
    from app.models.project import ProjectStatus

    fake_project = MagicMock()
    fake_project.status = ProjectStatus.CREATED
    fake_project.ontology = None
    fake_project.graph_build_task_id = None
    # MagicMock-Default für llm_profile_id ist truthy → würde Profile-Store
    # ansprechen, der hier nicht gemockt ist.
    fake_project.llm_profile_id = None
    fake_project.llm_model = None
    monkeypatch.setattr(
        "app.api.graph.ProjectManager.get_project",
        staticmethod(lambda _pid: fake_project),
    )
    response = client.post("/api/graph/build", json={"project_id": VALID_PROJECT_ID})
    assert response.status_code == 400
    assert response.get_json()["code"] == "ontology_missing"


# --- GRAPH_BUILD_IN_PROGRESS -------------------------------------------------


def test_build_graph_when_already_building_returns_graph_build_in_progress(
    client, monkeypatch
):
    from app.models.project import ProjectStatus

    fake_project = MagicMock()
    fake_project.status = ProjectStatus.GRAPH_BUILDING
    fake_project.ontology = {"entity_types": [], "edge_types": []}
    fake_project.graph_build_task_id = "existing-task-id"
    fake_project.llm_profile_id = None
    fake_project.llm_model = None
    monkeypatch.setattr(
        "app.api.graph.ProjectManager.get_project",
        staticmethod(lambda _pid: fake_project),
    )
    response = client.post("/api/graph/build", json={"project_id": VALID_PROJECT_ID})
    payload = response.get_json()
    assert response.status_code == 409
    assert payload["code"] == "graph_build_in_progress"
    assert payload["task_id"] == "existing-task-id"


# --- BATCH-MARKER / progress_detail CONTRACT (#137 SUB1) ---------------------


def test_add_text_batches_callback_receives_four_args():
    """add_text_batches ruft progress_callback mit (msg, ratio, completed, total) auf.

    Verifikation der neuen 4-Arg-Signatur: pro fertigem Chunk wird completed
    monoton hochgezählt und total bleibt konstant.
    """
    from app.services.graph_builder import GraphBuilderService

    storage = MagicMock(name="MockStorage")
    # add_text returns a fake uuid per chunk
    storage.add_text.side_effect = ["uuid-1", "uuid-2", "uuid-3"]

    service = GraphBuilderService(storage=storage)

    recorded: list[tuple] = []

    def capture_callback(msg: str, ratio: float, completed: int, total: int) -> None:
        recorded.append((msg, ratio, completed, total))

    uuids = service.add_text_batches(
        graph_id="test-graph-id",
        chunks=["chunk A", "chunk B", "chunk C"],
        progress_callback=capture_callback,
    )

    assert len(uuids) == 3
    assert len(recorded) == 3

    totals = [r[3] for r in recorded]
    assert all(t == 3 for t in totals), "total_batches muss konstant 3 sein"

    completed_vals = sorted(r[2] for r in recorded)
    assert completed_vals == [1, 2, 3], "completed muss monoton von 1 bis total steigen"

    ratios = [r[1] for r in recorded]
    for ratio, completed in zip(ratios, [r[2] for r in recorded]):
        assert abs(ratio - completed / 3) < 1e-9, "progress_ratio muss completed/total sein"


def test_add_progress_callback_sets_progress_detail_on_task_manager(monkeypatch):
    """add_progress_callback in graph.py setzt progress_detail mit Batch-Marker-Feldern.

    Wir patchen TaskManager.update_task und GraphBuilderService.add_text_batches,
    damit der Build-Thread synchron durchlaufen kann.
    """
    # @require_scope("graph:write") fordert Auth, sobald AGORA_AUTH_TOKEN gesetzt
    # ist. Dieser Test prüft progress_detail-Pipeline, nicht Auth — Open-Mode.
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    import threading

    from app.models.task import TaskManager
    from app.models.project import ProjectStatus
    from app.contracts.llm_routing_contract import ResolvedRoute

    # Captured update_task calls + Event, das im Background-Thread gesetzt wird,
    # sobald der erste progress_detail-Call durchlaeuft. Ersetzt den frueheren
    # 50x0.05s-Sleep-Loop (Gemini-MEDIUM auf #265, Slice 137-Followup).
    progress_detail_calls: list[dict] = []
    progress_event = threading.Event()
    original_update_task = TaskManager.update_task

    def spy_update_task(self, task_id, **kwargs):
        if "progress_detail" in kwargs and kwargs["progress_detail"] is not None:
            progress_detail_calls.append(dict(kwargs["progress_detail"]))
            progress_event.set()
        original_update_task(self, task_id, **kwargs)

    fake_project = MagicMock()
    fake_project.status = ProjectStatus.ONTOLOGY_GENERATED
    fake_project.ontology = {"entity_types": [], "edge_types": []}
    fake_project.graph_build_task_id = None
    fake_project.graph_id = None
    fake_project.name = "Test Project"
    fake_project.chunk_size = 500
    fake_project.chunk_overlap = 50
    fake_project.llm_model = None
    fake_project.llm_provider = None
    fake_project.llm_profile_id = None

    def fake_add_text_batches(
        graph_id,
        chunks,
        batch_size=3,
        progress_callback=None,
        ner_extractor=None,
        degradations=None,
        extraction_tally=None,
        document_ids=None,
        chunk_ids=None,
        run_id=None,
    ):
        # Simulate two chunks completing. ``degradations`` und
        # ``extraction_tally`` wurden mit PR #1030 (Issue #1029), ``document_ids``
        # und ``chunk_ids`` mit Issue #1152 Slice 1 Teil B, ``run_id`` mit
        # Issue B2 (kooperativer Abbruch) an ``add_text_batches`` angefuegt;
        # der Test akzeptiert sie explizit, damit eine kuenftige
        # Signatur-Erweiterung hier wieder laut aufschlaegt statt unbemerkt
        # durchzurutschen.
        if progress_callback:
            progress_callback("Processed 1/2 chunks...", 0.5, 1, 2)
            progress_callback("Processed 2/2 chunks...", 1.0, 2, 2)
        return ["uuid-a", "uuid-b"]

    fake_builder = MagicMock()
    fake_builder.create_graph.return_value = "graph-123"
    fake_builder.set_ontology.return_value = None
    fake_builder.add_text_batches.side_effect = fake_add_text_batches
    fake_builder.get_graph_data.return_value = {"node_count": 2, "edge_count": 1}

    fake_container = MagicMock()
    fake_container.neo4j_storage = MagicMock()  # must be non-None
    fake_container.graph_builder.return_value = fake_builder
    route_router = MagicMock()
    route_router.resolve.return_value = ResolvedRoute(
        stage="graph_build",
        provider_id="openai",
        model="gpt-4o-mini",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=4,
    )

    # After PR #562 the build logic lives in app.services.graph_build. Patches
    # on function symbols (seed_run_stage_routing, NERExtractor) must target
    # the service module — Class-attribute patches still work everywhere via
    # the shared class object.
    with (
        patch("app.api.graph.ProjectManager.get_project", return_value=fake_project),
        patch("app.api.graph.ProjectManager.save_project"),
        patch("app.api.graph.ProjectManager.get_extracted_text", return_value="some text"),
        patch("app.api.graph.TaskManager.update_task", spy_update_task),
        patch("app.api.graph.RunRegistry.create_run", return_value={"run_id": "progress-cb-run"}),
        patch("app.api.graph.RunRegistry.update_run"),
        patch("app.api.graph_build.get_container", return_value=fake_container),
        patch("app.api.graph.TextProcessor.split_text", return_value=["chunk1", "chunk2"]),
        patch("app.api.graph.ArtifactLocator.existing_paths", return_value={}),
        patch("app.services.graph_build.seed_run_stage_routing"),
        patch("app.services.graph_build.StageModelRouter", return_value=route_router),
        patch("app.services.graph_build.NERExtractor", return_value=MagicMock(name="NEROverride")),
        patch("app.services.graph_build.LLMClient.from_route", return_value=MagicMock(name="LLMClient", model="stub")),
        patch("app.services.graph_build.resolve_route_api_key", return_value="sk-stub"),
    ):
        flask_app = Flask(__name__)
        flask_app.config["AGORA_AUTH_TOKEN"] = ""
        storage = MagicMock()
        from app.container import AgoraContainer
        container = AgoraContainer(neo4j_storage=storage)
        flask_app.extensions = {"container": container, "neo4j_storage": storage}
        flask_app.register_blueprint(graph_bp, url_prefix="/api/graph")

        with flask_app.test_client() as client:
            response = client.post(
                "/api/graph/build",
                json={"project_id": VALID_PROJECT_ID},
            )
            assert response.status_code == 200, response.get_json()

        # Warte bis der Background-Thread mindestens einen progress_detail-
        # Call abgesetzt hat. threading.Event statt time.sleep-Loop verhindert
        # Flakiness unter Last und gibt sofort frei (Gemini-MEDIUM auf #265).
        assert progress_event.wait(timeout=2.5), (
            "Background-Thread hat innerhalb von 2.5 s keinen "
            "progress_detail-Call abgesetzt"
        )

    assert len(progress_detail_calls) >= 1, (
        "Es muss mindestens ein update_task mit progress_detail geben"
    )
    first = progress_detail_calls[0]
    assert "batch_count" in first, "progress_detail muss batch_count enthalten"
    assert "total_batches" in first, "progress_detail muss total_batches enthalten"
    assert "batch_at" in first, "progress_detail muss batch_at enthalten"
    assert first["batch_count"] >= 1
    assert first["total_batches"] == 2
    assert isinstance(first["batch_at"], float), "batch_at muss ein float (Unix-Epoch) sein"

    # Verify monotonic ordering: completed should never decrease
    batch_counts = [d["batch_count"] for d in progress_detail_calls]
    for i in range(1, len(batch_counts)):
        assert batch_counts[i] >= batch_counts[i - 1], (
            f"batch_count muss monoton steigen, bekam {batch_counts}"
        )
