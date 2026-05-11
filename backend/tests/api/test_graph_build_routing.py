from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import graph_bp
from app.contracts.llm_routing_contract import ResolvedRoute
from app.models.project import ProjectStatus


VALID_PROJECT_ID = "proj_0123456789ab"


@pytest.fixture
def client():
    app = Flask(__name__)
    storage = MagicMock(name="Neo4jStorage")
    app.extensions = {"neo4j_storage": storage}
    app.register_blueprint(graph_bp, url_prefix="/api/graph")
    return app.test_client()


def test_build_graph_uses_resolved_route_for_ner_override(client, monkeypatch):
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

    fake_builder = MagicMock()
    fake_builder.create_graph.return_value = "graph-123"
    fake_builder.set_ontology.return_value = None
    fake_builder.add_text_batches.return_value = None
    fake_builder.get_graph_data.return_value = {"node_count": 2, "edge_count": 1}

    fake_container = MagicMock()
    fake_container.neo4j_storage = MagicMock()
    fake_container.graph_builder.return_value = fake_builder

    fake_llm_client = MagicMock(name="ResolvedRouteLLMClient")
    captured_ner = {}

    class FakeRouter:
        def __init__(self, run_id: str):
            self.run_id = run_id

        def resolve(self, _stage_id: str):
            return ResolvedRoute(
                stage="graph_build",
                provider_id="openai",
                model="gpt-4o-mini",
                base_url_sanitized="https://api.openai.com/v1",
                routing_version=4,
            )

        def lock_stage(self, *_args, **_kwargs):
            return None

    def run_inline(self):
        self.run()

    def fake_ner_extractor(*, llm_client):
        captured_ner["llm_client"] = llm_client
        return MagicMock(name="NEROverride")

    monkeypatch.setattr("app.api.graph.ProjectManager.get_project", lambda _pid: fake_project)
    monkeypatch.setattr("app.api.graph.ProjectManager.save_project", lambda _project: None)
    monkeypatch.setattr("app.api.graph.ProjectManager.get_extracted_text", lambda _pid: "some text")
    monkeypatch.setattr("app.api.graph.get_container", lambda: fake_container)
    monkeypatch.setattr("app.api.graph.TextProcessor.split_text", lambda *a, **k: ["chunk1"])
    monkeypatch.setattr("app.api.graph.ArtifactLocator.existing_paths", lambda *_a, **_k: {})
    monkeypatch.setattr("app.api.graph.seed_run_stage_routing", lambda *a, **k: None)
    monkeypatch.setattr("app.api.graph.StageModelRouter", FakeRouter)
    monkeypatch.setattr("app.api.graph.resolve_route_api_key", lambda *_a, **_k: "sk-route")
    monkeypatch.setattr("app.api.graph.LLMClient.from_route", lambda *a, **k: fake_llm_client)
    monkeypatch.setattr("app.api.graph.NERExtractor", fake_ner_extractor)
    monkeypatch.setattr("app.api.graph.threading.Thread.start", run_inline)
    monkeypatch.setattr("app.api.graph.run_registry.create_run", lambda *a, **k: {"run_id": "run_graph_1"})
    monkeypatch.setattr("app.api.graph.run_registry.update_run", lambda *a, **k: None)

    response = client.post("/api/graph/build", json={"project_id": VALID_PROJECT_ID})

    assert response.status_code == 200, response.get_json()
    assert captured_ner["llm_client"] is fake_llm_client
