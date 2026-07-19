"""POST /api/graph/ontology/generate persistiert die Projekt-Metadaten.

Regression aus dem #562-Refactor: ``create_project()`` speichert die
``project.json`` sofort — also BEVOR der Endpoint ``simulation_requirement``,
``files`` und ``total_text_length`` ans Objekt schreibt. Der Service
(``GraphBuildService.generate_ontology``) lädt das Projekt anschließend
frisch von Platte und überschreibt die Meta beim eigenen ``save_project``.
Ohne explizites ``save_project`` in der Route gingen die drei Felder
verloren; Report-Generate und Simulation-Prepare lehnten jedes Projekt mit
400 "Missing simulation requirement description" ab (e2e-Smokes
report-modes + minimal-report, CI-Run 27241443657).

Anders als ``test_graph_ontology_respects_frontend_model.py`` mockt dieser
Test den ``ProjectManager`` NICHT — die Persistenz läuft echt gegen ein
``tmp_path``-Projektverzeichnis, nur LLM-Pipeline und Datei-Parsing sind
gestubbt.
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import graph_bp
from app.container import AgoraContainer
from app.models.project import ProjectManager

REQUIREMENT = "Persistenz-Smoke: Requirement muss den Service-Reload überleben."


@pytest.fixture
def app(monkeypatch):
    """
    Create a Flask application configured for graph API integration tests.
    
    Returns:
        Flask: A test application with the graph blueprint and mocked storage configured.
    """
    monkeypatch.setattr("app.config.Config.LLM_MODEL_NAME", "gpt-4o")
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


@pytest.fixture
def persistence_mocks(monkeypatch, tmp_path):
    """Echter ProjectManager auf tmp_path; LLM-Pipeline und Parsing gestubbt."""
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))

    llm_client_cls = MagicMock(name="LLMClient")
    generator = MagicMock(name="OntologyGeneratorInstance")
    generator.generate.return_value = {
        "entity_types": [{"name": "Person"}],
        "edge_types": [{"name": "KNOWS"}],
        "analysis_summary": "ok",
    }
    ontology_generator_cls = MagicMock(name="OntologyGenerator", return_value=generator)

    run_registry_mock = MagicMock(name="run_registry")
    run_registry_mock.create_run.return_value = {
        "run_id": f"ontology-run-{uuid.uuid4().hex[:12]}"
    }

    # Service-side bindings — ProjectManager läuft bewusst ECHT.
    monkeypatch.setattr("app.services.graph_build.LLMClient", llm_client_cls)
    monkeypatch.setattr("app.services.graph_build.OntologyGenerator", ontology_generator_cls)
    monkeypatch.setattr("app.services.graph_build.run_registry", run_registry_mock)

    # API-side bindings — Datei-Parsing gestubbt, Persistenz ECHT.
    file_parser_cls = MagicMock(name="FileParser")
    file_parser_cls.extract_text.return_value = "extracted text content"
    text_processor_cls = MagicMock(name="TextProcessor")
    text_processor_cls.preprocess_text.return_value = "cleaned text"
    monkeypatch.setattr("app.api.graph_build.FileParser", file_parser_cls)
    monkeypatch.setattr("app.api.graph_build.TextProcessor", text_processor_cls)


def test_ontology_generate_persists_requirement_files_and_text_length(
    client, persistence_mocks
):
    response = client.post(
        "/api/graph/ontology/generate",
        data={
            "simulation_requirement": REQUIREMENT,
            "project_name": "persistenz-check",
            "files": (io.BytesIO(b"Document body for ontology run."), "doc.txt"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200, response.get_json()
    project_id = response.get_json()["data"]["project_id"]

    # Frisch von Platte laden — exakt das, was Report-Generate und
    # Simulation-Prepare später tun (project.simulation_requirement leer
    # => ValueError "Missing simulation requirement description").
    reloaded = ProjectManager.get_project(project_id)
    assert reloaded is not None
    assert reloaded.simulation_requirement == REQUIREMENT
    assert reloaded.files, "files-Liste muss die project.json überleben"
    assert reloaded.total_text_length and reloaded.total_text_length > 0
