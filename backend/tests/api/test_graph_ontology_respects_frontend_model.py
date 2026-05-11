"""POST /api/graph/ontology/generate respektiert die Frontend-Modellauswahl.

Sub-Slice „ontology-respects-frontend-model" — Frontend hängt
``llm_model`` (String) und ``llm_provider`` (JSON-String) ans FormData;
Backend muss daraus den ``LLMClient`` parametrieren, statt blind auf
``Config.LLM_MODEL_NAME`` zu fallen.
"""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import graph_bp
from app.container import AgoraContainer


@pytest.fixture
def app(monkeypatch, tmp_path):
    from app.api import graph as graph_module
    from app.services.run_registry import RunRegistry

    monkeypatch.setenv("AGORA_INSTANCE_DIR", str(tmp_path / "instance"))
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(tmp_path / "run_registry"))
    graph_module.run_registry._cache = {}

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


@patch("app.api.graph.LLMClient")
@patch("app.api.graph.OntologyGenerator")
@patch("app.api.graph.ProjectManager")
@patch("app.api.graph.FileParser")
@patch("app.api.graph.TextProcessor")
def test_ontology_generate_uses_frontend_llm_model_and_provider(
    text_processor_cls,
    file_parser_cls,
    project_manager_cls,
    ontology_generator_cls,
    llm_client_cls,
    client,
):
    # --- Arrange Stubs ---
    project_manager_cls.create_project.return_value = _make_project_mock()
    project_manager_cls.save_file_to_project.return_value = {
        "original_filename": "doc.txt",
        "path": "/tmp/doc.txt",
        "size": 42,
    }
    file_parser_cls.extract_text.return_value = "extracted text content"
    text_processor_cls.preprocess_text.return_value = "cleaned text"

    generator = MagicMock()
    generator.generate.return_value = {
        "entity_types": [{"name": "Person"}],
        "edge_types": [{"name": "KNOWS"}],
        "analysis_summary": "ok",
    }
    ontology_generator_cls.return_value = generator

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
    run_id = response.get_json()["data"]["run_id"]
    assert run_id.startswith("run_")

    # LLMClient muss mit dem Frontend-Modell + Provider-Override instanziiert sein.
    # Nach Refactor wird .from_route() verwendet.
    llm_client_cls.from_route.assert_called_once()
    route = llm_client_cls.from_route.call_args.args[0]
    assert llm_client_cls.from_route.call_args.kwargs["run_id"] == run_id
    assert route.model == "gpt-5-mini"
    assert route.provider_id == "openai"
    # base_url wird im SecretResolver/from_route aufgelöst, hier prüfen wir die Route
    assert route.base_url_sanitized == "https://api.openai.com/v1"

    # OntologyGenerator muss den injizierten Client bekommen.
    ontology_generator_cls.assert_called_once()
    assert ontology_generator_cls.call_args.kwargs.get("llm_client") is llm_client_cls.from_route.return_value


@patch("app.api.graph.LLMClient")
@patch("app.api.graph.OntologyGenerator")
@patch("app.api.graph.ProjectManager")
@patch("app.api.graph.FileParser")
@patch("app.api.graph.TextProcessor")
def test_ontology_generate_without_overrides_uses_server_default(
    text_processor_cls,
    file_parser_cls,
    project_manager_cls,
    ontology_generator_cls,
    llm_client_cls,
    client,
):
    """Backwards-Kompat: Ohne llm_model/llm_provider bleibt LLMClient(model=None) → Server-Default."""
    project_manager_cls.create_project.return_value = _make_project_mock()
    project_manager_cls.save_file_to_project.return_value = {
        "original_filename": "doc.txt",
        "path": "/tmp/doc.txt",
        "size": 42,
    }
    file_parser_cls.extract_text.return_value = "x"
    text_processor_cls.preprocess_text.return_value = "x"
    ontology_generator_cls.return_value.generate.return_value = {
        "entity_types": [],
        "edge_types": [],
        "analysis_summary": "",
    }

    response = client.post(
        "/api/graph/ontology/generate",
        data={"simulation_requirement": "Need ontology.", "files": _txt()},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200, response.get_json()
    llm_client_cls.from_route.assert_called_once()
    route = llm_client_cls.from_route.call_args.args[0]
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


def test_ontology_generate_rejects_provider_without_api_key(client):
    response = client.post(
        "/api/graph/ontology/generate",
        data={
            "simulation_requirement": "x",
            "files": _txt(),
            "llm_provider": json.dumps({"provider": "openai"}),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "validation_failed"


@patch("app.api.graph.LLMClient")
@patch("app.api.graph.OntologyGenerator")
@patch("app.api.graph.ProjectManager")
@patch("app.api.graph.FileParser")
@patch("app.api.graph.TextProcessor")
def test_ontology_generate_persists_llm_metadata_on_project(
    text_processor_cls,
    file_parser_cls,
    project_manager_cls,
    ontology_generator_cls,
    llm_client_cls,
    client,
):
    """Modell + redacted Provider-Metadaten landen am Projekt — Secrets bleiben draußen."""
    project_mock = _make_project_mock()
    project_manager_cls.create_project.return_value = project_mock
    project_manager_cls.save_file_to_project.return_value = {
        "original_filename": "doc.txt",
        "path": "/tmp/doc.txt",
        "size": 42,
    }
    file_parser_cls.extract_text.return_value = "x"
    text_processor_cls.preprocess_text.return_value = "x"
    ontology_generator_cls.return_value.generate.return_value = {
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
