"""POST /api/graph/ontology/generate respektiert die Frontend-Modellauswahl.

Sub-Slice „ontology-respects-frontend-model" — Frontend hängt
``llm_model`` (String) und ``llm_provider`` (JSON-String) ans FormData;
Backend muss daraus den ``LLMClient`` parametrieren, statt blind auf
``Config.LLM_MODEL_NAME`` zu fallen.
"""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import graph_bp
from app.container import AgoraContainer


@pytest.fixture
def app(monkeypatch):
    storage = MagicMock(name="Neo4jStorage")
    container = AgoraContainer(neo4j_storage=storage)
    flask_app = Flask(__name__)
    flask_app.config["AGORA_UPLOAD_RATE_LIMIT_MAX"] = 1000
    flask_app.config["AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS"] = 60
    flask_app.extensions = {"container": container, "neo4j_storage": storage}
    flask_app.register_blueprint(graph_bp, url_prefix="/api/graph")
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _txt(payload: bytes = b"Document body for ontology run.") -> tuple:
    return (io.BytesIO(payload), "doc.txt")


def _make_project_mock():
    """Project-Mock mit ausschließlich JSON-serialisierbaren Attributen,
    damit ``json_success({...})`` am Endpoint-Ende nicht über MagicMock-Auto-Attrs stolpert.

    Falle: ``MagicMock(name=...)`` setzt den Mock-Repr-Namen, **nicht** das
    ``.name``-Attribut. Daher alle felder explizit zugewiesen.
    """
    import uuid
    mock = MagicMock()
    mock.project_id = f"proj_{uuid.uuid4().hex[:12]}"
    mock.name = "Test"
    mock.files = []
    mock.total_text_length = 42
    mock.ontology = None
    mock.analysis_summary = None
    mock.llm_model = None
    mock.llm_provider = None
    mock.simulation_requirement = None
    return mock


@pytest.fixture
def ontology_mocks(monkeypatch):
    """Patch the ontology pipeline at the *consumer* binding sites.

    After PR #562 the logic lives in ``app.services.graph_build`` and the
    HTTP endpoint sits in ``app.api.graph_build``. Patches must target the
    module that actually performs the import — replacing
    ``app.api.graph.X`` is a no-op because nobody looks symbols up there
    anymore.
    """
    llm_client_cls = MagicMock(name="LLMClient")
    ontology_generator_cls = MagicMock(name="OntologyGenerator")
    project_manager_cls = MagicMock(name="ProjectManager")
    file_parser_cls = MagicMock(name="FileParser")
    text_processor_cls = MagicMock(name="TextProcessor")
    import uuid
    run_registry_mock = MagicMock(name="run_registry")
    # Unique run_id per test — seed_run_stage_routing persists per-run config
    # files on disk, so a shared id would cross-pollinate routing state.
    run_registry_mock.create_run.return_value = {
        "run_id": f"ontology-run-{uuid.uuid4().hex[:12]}"
    }

    # Service-side bindings (generate_ontology lives here).
    # StageModelRouter, seed_run_stage_routing and resolve_route_api_key are
    # NOT mocked — the test asserts on the real route the routing layer builds
    # from the llm_model/llm_provider form data.
    monkeypatch.setattr("app.services.graph_build.LLMClient", llm_client_cls)
    monkeypatch.setattr("app.services.graph_build.OntologyGenerator", ontology_generator_cls)
    monkeypatch.setattr("app.services.graph_build.ProjectManager", project_manager_cls)
    monkeypatch.setattr("app.services.graph_build.run_registry", run_registry_mock)

    # API-side bindings (endpoint generate_ontology reads form data, calls
    # FileParser/TextProcessor/ProjectManager directly).
    monkeypatch.setattr("app.api.graph_build.ProjectManager", project_manager_cls)
    monkeypatch.setattr("app.api.graph_build.FileParser", file_parser_cls)
    monkeypatch.setattr("app.api.graph_build.TextProcessor", text_processor_cls)

    return {
        "llm": llm_client_cls,
        "ontology_generator": ontology_generator_cls,
        "project_manager": project_manager_cls,
        "file_parser": file_parser_cls,
        "text_processor": text_processor_cls,
    }


def _arrange_happy_path(mocks, ontology_payload=None):
    project = _make_project_mock()
    # The endpoint creates a project, the service later looks it up by ID.
    # Both must hand back the same instance so the response payload reads the
    # mutations the service applies (ontology, analysis_summary, …).
    mocks["project_manager"].create_project.return_value = project
    mocks["project_manager"].get_project.return_value = project
    mocks["project_manager"].save_file_to_project.return_value = {
        "original_filename": "doc.txt",
        "path": "/tmp/doc.txt",
        "size": 42,
    }
    mocks["file_parser"].extract_text.return_value = "extracted text content"
    mocks["text_processor"].preprocess_text.return_value = "cleaned text"
    generator = MagicMock()
    generator.generate.return_value = ontology_payload or {
        "entity_types": [],
        "edge_types": [],
        "analysis_summary": "",
    }
    mocks["ontology_generator"].return_value = generator
    return generator


def test_ontology_generate_uses_frontend_llm_model_and_provider(client, ontology_mocks):
    # --- Arrange Stubs ---
    _arrange_happy_path(
        ontology_mocks,
        ontology_payload={
            "entity_types": [{"name": "Person"}],
            "edge_types": [{"name": "KNOWS"}],
            "analysis_summary": "ok",
        },
    )

    # --- Act ---
    response = client.post(
        "/api/graph/ontology/generate",
        data={
            "simulation_requirement": "Discuss climate policy.",
            "files": _txt(),
            "llm_model": "gpt-5-mini",
            "llm_provider": json.dumps(
                {
                    "provider": "openai",
                    "api_key": "sk-test",
                    "base_url": "https://api.openai.com/v1",
                }
            ),
        },
        content_type="multipart/form-data",
    )

    # --- Assert ---
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["success"] is True

    # LLMClient muss mit dem Frontend-Modell + Provider-Override instanziiert sein.
    # Nach Refactor wird .from_route() verwendet.
    ontology_mocks["llm"].from_route.assert_called_once()
    route = ontology_mocks["llm"].from_route.call_args.args[0]
    assert route.model == "gpt-5-mini"
    assert route.provider_id == "openai"
    # base_url wird im SecretResolver/from_route aufgelöst, hier prüfen wir die Route
    assert route.base_url_sanitized == "https://api.openai.com/v1"

    # OntologyGenerator muss den injizierten Client bekommen.
    ontology_mocks["ontology_generator"].assert_called_once()
    assert (
        ontology_mocks["ontology_generator"].call_args.kwargs.get("llm_client")
        is ontology_mocks["llm"].from_route.return_value
    )


def test_ontology_generate_without_overrides_uses_server_default(client, ontology_mocks):
    """Backwards-Kompat: Ohne llm_model/llm_provider bleibt LLMClient(model=None) → Server-Default."""
    _arrange_happy_path(ontology_mocks)

    response = client.post(
        "/api/graph/ontology/generate",
        data={"simulation_requirement": "Need ontology.", "files": _txt()},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200, response.get_json()
    ontology_mocks["llm"].from_route.assert_called_once()
    route = ontology_mocks["llm"].from_route.call_args.args[0]
    # Standard-Modell aus Config
    from app.config import Config
    assert route.model == Config.LLM_MODEL_NAME


def test_ontology_generate_rejects_invalid_llm_provider_json(client):
    response = client.post(
        "/api/graph/ontology/generate",
        data={
            "simulation_requirement": "x",
            "files": _txt(),
            "llm_provider": "not-json-{{{",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "validation_failed"
    assert "llm_provider" in payload["error"].lower()


def test_ontology_generate_accepts_provider_without_api_key_uses_db_fallback(client, ontology_mocks):
    """Provider ohne api_key im Payload → kein 400 mehr. Backend nutzt SecretResolver-Fallback.

    Geändertes Verhalten seit Smoke-Fix Slice 04:
    parse_runtime_llm_config() wirft keinen Fehler mehr bei fehlendem api_key.
    Der Fallback auf die Settings-DB erfolgt in resolve_route_api_key().
    """
    _arrange_happy_path(ontology_mocks)

    response = client.post(
        "/api/graph/ontology/generate",
        data={
            "simulation_requirement": "x",
            "files": _txt(),
            "llm_provider": json.dumps({"provider": "openai"}),
        },
        content_type="multipart/form-data",
    )
    # Provider ohne api_key wird erfolgreich akzeptiert — parse_runtime_llm_config
    # wirft keinen Fehler mehr, der Fallback auf Settings-DB erfolgt intern.
    # Copilot PR #466: Assertion auf konkreten 200 statt nur != 400, damit
    # 500er oder andere Fehler nicht unbemerkt durchgehen.
    assert response.status_code == 200, (
        "Provider ohne api_key muss erfolgreich verarbeitet werden (200); "
        f"erhalten: {response.status_code} — {response.get_json()}"
    )


def test_ontology_generate_persists_llm_metadata_on_project(client, ontology_mocks):
    """Modell + redacted Provider-Metadaten landen am Projekt — Secrets bleiben draußen."""
    project_mock = _make_project_mock()
    ontology_mocks["project_manager"].create_project.return_value = project_mock
    ontology_mocks["project_manager"].get_project.return_value = project_mock
    ontology_mocks["project_manager"].save_file_to_project.return_value = {
        "original_filename": "doc.txt",
        "path": "/tmp/doc.txt",
        "size": 42,
    }
    ontology_mocks["file_parser"].extract_text.return_value = "x"
    ontology_mocks["text_processor"].preprocess_text.return_value = "x"
    ontology_mocks["ontology_generator"].return_value.generate.return_value = {
        "entity_types": [],
        "edge_types": [],
        "analysis_summary": "",
    }

    client.post(
        "/api/graph/ontology/generate",
        data={
            "simulation_requirement": "x",
            "files": _txt(),
            "llm_model": "gpt-4o",
            "llm_provider": json.dumps(
                {"provider": "openai", "api_key": "sk-secret", "base_url": "https://api.openai.com/v1"}
            ),
        },
        content_type="multipart/form-data",
    )

    assert project_mock.llm_model == "gpt-4o"
    # redacted_metadata() liefert provider/base_url/api_key_set — KEIN api_key-Klartext.
    assert project_mock.llm_provider is not None
    assert "api_key" not in project_mock.llm_provider
    assert project_mock.llm_provider.get("provider") == "openai"
    assert project_mock.llm_provider.get("api_key_set") is True
