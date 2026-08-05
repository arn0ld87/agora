"""Atomizität des Ontology-Uploads bei File-I/O-Fehlern (Issue #899).

Deckt den Abschnitt zwischen ``ProjectManager.create_project`` und dem Aufruf
von ``GraphBuildService.generate_ontology`` in ``generate_ontology`` ab: ein
I/O-Fehler in diesem Fenster darf kein halb angelegtes Projekt (Verzeichnis,
files/, project.json mit Status CREATED) hinterlassen. Verifiziert wird über
zwei Seams: (a) der HTTP-Seam via Flask-Testclient, (b) der beobachtete
Cleanup über den gemockten ``ProjectManager``.
"""

from __future__ import annotations

import io
import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import graph_bp
from app.config import Config
from app.container import AgoraContainer
from app.models.project import ProjectStatus
from app.storage.graph_storage import GraphStorage


PROJECT_ID = "proj_upload_atomic01"
SECRET_SENTINEL = "sk-upload-atomicity-secret-must-not-leak"


def _capture_agora_logs(monkeypatch, caplog) -> None:
    """Macht die ``agora.*``-Logger für caplog sichtbar.

    ``get_logger`` setzt ``propagate = False``, deshalb erreicht kein Record den
    Root-Handler, an dem caplog hängt — ohne diesen Schalter wäre jede
    ``SECRET_SENTINEL not in caplog.text``-Zusicherung gegen ein leeres caplog
    trivial wahr. DEBUG-Level, damit auch INFO/DEBUG-Records erfasst werden.
    """
    caplog.set_level(logging.DEBUG)
    for name, candidate in list(logging.root.manager.loggerDict.items()):
        if isinstance(candidate, logging.Logger) and (
            name == "agora" or name.startswith("agora.")
        ):
            monkeypatch.setattr(candidate, "propagate", True)
            monkeypatch.setattr(candidate, "level", logging.DEBUG)


@pytest.fixture(params=["false", "true"], ids=["debug-off", "debug-on"])
def flask_debug(request, monkeypatch) -> str:
    """Fährt jeden Testfall gegen beide ``FLASK_DEBUG``-Werte.

    Der Leak, den diese Datei absichert, trat ausschließlich unter
    ``FLASK_DEBUG=true`` auf — nur ``FLASK_DEBUG=false`` zu prüfen hat ihn
    jahrelang durchgelassen. ``Config.DEBUG`` wird beim Import aus der
    Umgebungsvariable evaluiert, deshalb wird das Attribut zusätzlich direkt
    gesetzt.
    """
    value: str = request.param
    monkeypatch.setenv("FLASK_DEBUG", value)
    monkeypatch.setattr(Config, "DEBUG", value == "true")
    return value


@pytest.fixture
def upload_env(monkeypatch, caplog, flask_debug):
    _capture_agora_logs(monkeypatch, caplog)
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
        name="Upload Atomicity Project",
        files=[],
        total_text_length=0,
        ontology=None,
        analysis_summary=None,
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

    generate_ontology_service = MagicMock()

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

    return SimpleNamespace(
        client=app.test_client(),
        monkeypatch=monkeypatch,
        project=project,
        project_manager=project_manager,
        generate_ontology_service=generate_ontology_service,
    )


def _ref_payload() -> dict[str, str]:
    return {
        "provider_connection_id": "conn-upload-atomicity",
        "model_id": "upload-atomicity-model",
        "source": "explicit",
    }


def _post(client, *, canonical: bool):
    data = {
        "simulation_requirement": "Analyse the document.",
        "files": (io.BytesIO(b"document"), "document.txt"),
    }
    if canonical:
        data["ai_model_ref"] = json.dumps(_ref_payload())
    return client.post(
        "/api/graph/ontology/generate",
        data=data,
        content_type="multipart/form-data",
    )


def _assert_atomic_failure(
    response,
    caplog,
    capsys,
    project_manager,
    *,
    logged_sentinel: str,
    expected_project_id: str = PROJECT_ID,
):
    """Response bleibt eine generische 500, Cleanup wurde mit der project_id
    versucht, und weder Sentinel noch Dateipfade tauchen in der Response auf.

    Der Originalfehler muss dabei serverseitig erkennbar bleiben: er wird
    protokolliert, damit die generische Antwort nicht auch die Diagnose kostet.
    """
    captured = capsys.readouterr()
    assert response.status_code == 500
    body = response.get_json()
    assert body == {
        "success": False,
        "error": "internal server error",
        "code": "internal_error",
    }
    project_manager.delete_project.assert_called_with(expected_project_id)
    response_text = response.get_data(as_text=True)
    assert SECRET_SENTINEL not in response_text
    assert "/tmp/" not in response_text
    assert SECRET_SENTINEL not in captured.out
    assert SECRET_SENTINEL not in captured.err
    assert logged_sentinel in caplog.text


@pytest.mark.parametrize("canonical", [False, True], ids=["legacy", "canonical"])
def test_save_file_to_project_failure_cleans_up_project(
    upload_env, caplog, capsys, canonical
):
    upload_env.project_manager.save_file_to_project.side_effect = OSError(
        f"disk write failed: {SECRET_SENTINEL}"
    )

    response = _post(upload_env.client, canonical=canonical)

    _assert_atomic_failure(
        response,
        caplog,
        capsys,
        upload_env.project_manager,
        logged_sentinel="disk write failed",
    )
    upload_env.generate_ontology_service.assert_not_called()


@pytest.mark.parametrize("canonical", [False, True], ids=["legacy", "canonical"])
def test_extract_text_failure_cleans_up_project(
    upload_env, caplog, capsys, canonical
):
    def _boom(_path):
        raise OSError(f"read failed: {SECRET_SENTINEL}")

    upload_env.monkeypatch.setattr("app.api.graph_build.FileParser.extract_text", _boom)

    response = _post(upload_env.client, canonical=canonical)

    _assert_atomic_failure(
        response,
        caplog,
        capsys,
        upload_env.project_manager,
        logged_sentinel="read failed",
    )
    upload_env.generate_ontology_service.assert_not_called()


@pytest.mark.parametrize("canonical", [False, True], ids=["legacy", "canonical"])
def test_save_extracted_text_failure_cleans_up_project(
    upload_env, caplog, capsys, canonical
):
    upload_env.project_manager.save_extracted_text.side_effect = OSError(
        f"write extracted text failed: {SECRET_SENTINEL}"
    )

    response = _post(upload_env.client, canonical=canonical)

    _assert_atomic_failure(
        response,
        caplog,
        capsys,
        upload_env.project_manager,
        logged_sentinel="write extracted text failed",
    )
    upload_env.generate_ontology_service.assert_not_called()


@pytest.mark.parametrize("canonical", [False, True], ids=["legacy", "canonical"])
def test_save_project_failure_does_not_falsely_succeed(
    upload_env, caplog, capsys, canonical
):
    # Nur der save_project-Aufruf nach der Extraktion soll scheitern —
    # create_project() persistiert bereits intern und ruft save_project()
    # nicht separat auf, dieser Mock trifft daher genau die spätere Persistenz.
    upload_env.project_manager.save_project.side_effect = OSError(
        f"persist project failed: {SECRET_SENTINEL}"
    )

    response = _post(upload_env.client, canonical=canonical)

    _assert_atomic_failure(
        response,
        caplog,
        capsys,
        upload_env.project_manager,
        logged_sentinel="persist project failed",
    )
    upload_env.generate_ontology_service.assert_not_called()


@pytest.mark.parametrize("canonical", [False, True], ids=["legacy", "canonical"])
def test_cleanup_failure_itself_does_not_produce_success(
    upload_env, caplog, capsys, canonical
):
    original_failure_sentinel = f"{SECRET_SENTINEL}-original"
    cleanup_failure_sentinel = f"{SECRET_SENTINEL}-cleanup"

    upload_env.project_manager.save_file_to_project.side_effect = OSError(
        f"disk write failed: {original_failure_sentinel}"
    )
    upload_env.project_manager.delete_project.side_effect = OSError(
        f"cleanup failed: {cleanup_failure_sentinel}"
    )

    response = _post(upload_env.client, canonical=canonical)

    assert response.status_code == 500
    body = response.get_json()
    assert body == {
        "success": False,
        "error": "internal server error",
        "code": "internal_error",
    }
    upload_env.project_manager.delete_project.assert_called_with(PROJECT_ID)
    response_text = response.get_data(as_text=True)
    assert original_failure_sentinel not in response_text
    assert cleanup_failure_sentinel not in response_text

    # Der Cleanup-Fehler wird als Fehler samt Traceback geloggt ...
    cleanup_records = [
        record
        for record in caplog.records
        if record.levelno >= logging.ERROR and PROJECT_ID in record.getMessage()
    ]
    assert cleanup_records, "Cleanup-Fehler wurde nicht als Fehler geloggt"
    assert cleanup_records[0].exc_info is not None
    assert cleanup_failure_sentinel in caplog.text
    # ... und verdeckt die Ursprungsursache nicht: sie bleibt serverseitig
    # diagnostizierbar, obwohl die Antwort generisch bleibt.
    assert original_failure_sentinel in caplog.text
    upload_env.generate_ontology_service.assert_not_called()


@pytest.mark.parametrize("canonical", [False, True], ids=["legacy", "canonical"])
def test_no_case_leaks_paths_or_provider_details(upload_env, caplog, capsys, canonical):
    """Sanitization-Sammeltest: keine Dateipfade/Provider-Details/Sentinel in
    der Response, unabhängig davon, in welcher Stufe der I/O-Fehler auftritt."""
    upload_env.project_manager.save_file_to_project.side_effect = OSError(
        f"/var/secret/path failed: {SECRET_SENTINEL} provider=conn-upload-atomicity"
    )

    response = _post(upload_env.client, canonical=canonical)

    response_text = response.get_data(as_text=True)
    assert "/var/secret/path" not in response_text
    assert SECRET_SENTINEL not in response_text
    assert "conn-upload-atomicity" not in response_text
