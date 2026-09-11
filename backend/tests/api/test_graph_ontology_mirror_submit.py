"""Der Supabase-Mirror-Auftrag darf erst nach dem letzten Cleanup-Fenster raus.

``_mirror_uploaded_documents`` uebergibt asynchron an einen Worker-Thread.
Wird danach noch ``_discard_project_after_upload_failure()`` ausgeloest — bei
``ProjectManager.save_project`` oder bei ``GraphBuildService.generate_ontology``
—, schreibt der Worker Dokumentzeilen fuer ein Projekt, das lokal nicht mehr
existiert. Der Spiegel darf keine Zeilen erfinden, die die Wahrheit nicht hat.
"""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import graph_bp
from app.container import AgoraContainer
from app.models.project import ProjectStatus
from app.storage.graph_storage import GraphStorage

PROJECT_ID = "proj_mirror_submit01"


class SpyMirror:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, list, dict]] = []

    def mirror_documents(self, project_id, entries, *, file_paths=None):
        self.jobs.append((project_id, list(entries), dict(file_paths or {})))


@pytest.fixture
def upload_env(monkeypatch):
    storage = MagicMock(spec=GraphStorage)
    app = Flask(__name__)
    app.config.update(
        AGORA_AUTH_TOKEN="",
        AGORA_UPLOAD_RATE_LIMIT_MAX=1000,
        AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS=60,
    )
    app.extensions = {
        "container": AgoraContainer(neo4j_storage=storage),
        "neo4j_storage": storage,
    }
    app.register_blueprint(graph_bp, url_prefix="/api/graph")

    project = SimpleNamespace(
        project_id=PROJECT_ID,
        name="Mirror Submit Project",
        files=[],
        total_text_length=0,
        ontology={"entities": []},
        analysis_summary="ok",
        simulation_requirement=None,
        status=ProjectStatus.CREATED,
        error=None,
        graph_id=None,
        graph_build_task_id=None,
        chunk_size=500,
        chunk_overlap=50,
        llm_model=None,
        llm_provider=None,
        llm_profile_id=None,
    )
    project_manager = MagicMock()
    project_manager.create_project.return_value = project
    project_manager.get_project.return_value = project
    project_manager.save_file_to_project.return_value = {
        "original_filename": "document.txt",
        "path": "/tmp/document.txt",
        "size": 8,
    }
    project_manager.delete_project.return_value = True

    generate_ontology_service = MagicMock(return_value=project)
    spy_mirror = SpyMirror()

    monkeypatch.setattr("app.api.graph_build.ProjectManager", project_manager)
    monkeypatch.setattr(
        "app.api.graph_build.prevalidate_ai_model_ref_with_discovery", lambda _ref: None
    )
    monkeypatch.setattr(
        "app.api.graph_build.FileParser.extract_text", lambda _path: "document"
    )
    monkeypatch.setattr(
        "app.api.graph_build.TextProcessor.preprocess_text", lambda text: text
    )
    monkeypatch.setattr(
        "app.api.graph_build.GraphBuildService.generate_ontology",
        generate_ontology_service,
    )
    # _mirror_uploaded_documents importiert erst zur Laufzeit aus dem Paket.
    monkeypatch.setattr(
        "app.services.supabase_mirror.get_supabase_mirror", lambda: spy_mirror
    )

    return SimpleNamespace(
        client=app.test_client(),
        project_manager=project_manager,
        generate_ontology_service=generate_ontology_service,
        mirror=spy_mirror,
    )


def _post(client):
    return client.post(
        "/api/graph/ontology/generate",
        data={
            "simulation_requirement": "Analyse the document.",
            "files": (io.BytesIO(b"document"), "document.txt"),
        },
        content_type="multipart/form-data",
    )


def test_successful_upload_submits_mirror_job_once(upload_env):
    response = _post(upload_env.client)

    assert response.status_code == 200
    assert len(upload_env.mirror.jobs) == 1
    project_id, entries, file_paths = upload_env.mirror.jobs[0]
    assert project_id == PROJECT_ID
    assert [entry.filename for entry in entries] == ["document.txt"]
    assert file_paths == {"document": "/tmp/document.txt"}


def test_save_project_failure_submits_no_mirror_job(upload_env):
    upload_env.project_manager.save_project.side_effect = OSError("disk full")

    response = _post(upload_env.client)

    assert response.status_code == 500
    upload_env.project_manager.delete_project.assert_called_with(PROJECT_ID)
    assert upload_env.mirror.jobs == []


def test_generate_ontology_failure_submits_no_mirror_job(upload_env):
    upload_env.generate_ontology_service.side_effect = ValueError("ontology rejected")

    response = _post(upload_env.client)

    assert response.status_code >= 400
    upload_env.project_manager.delete_project.assert_called_with(PROJECT_ID)
    assert upload_env.mirror.jobs == []
