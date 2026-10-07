"""Endpunkt-Tests für ``app.api.graph_duplicate`` (Issue #1808, Etappe 8).

Der Dienst ist durch einen Stub ersetzt: geprüft werden Statuscodes,
Validierung, Fehlerabbildung und Scopes der Route. Die Fachregeln des Kopierens
(auch aus einem gesperrten Graphen) prüft ``tests/services/test_graph_duplicate_service.py``.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

import pytest
from cryptography.fernet import Fernet
from flask import Flask

from app.api import graph_bp
from app.contracts.graph_edit_contract import GraphDuplicateJob, GraphDuplicateRequest
from app.services.api_keys_store import ApiKeysStore
from app.services.graph_duplicate_service import (
    GraphDuplicateSourceNotFound,
    GraphDuplicateSourceStateError,
)
from app.services.graph_edit_service import EmbeddingMigrationRunningError
from app.utils.api_responses import install_api_error_handlers

GID = "11111111-1111-4111-8111-111111111111"
TARGET = "22222222-2222-4222-8222-222222222222"


class _StubService:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.calls: List[tuple[str, GraphDuplicateRequest]] = []

    def start(self, graph_id: str, request: GraphDuplicateRequest) -> GraphDuplicateJob:
        self.calls.append((graph_id, request))
        if self.error is not None:
            raise self.error
        return GraphDuplicateJob(
            run_id="run_0123456789ab", source_graph_id=graph_id, graph_id=TARGET,
            project_id="proj_0123456789ab", status="pending", progress=0, message="Kopie angelegt",
        )


@pytest.fixture
def service(monkeypatch) -> _StubService:
    stub = _StubService()
    monkeypatch.setattr("app.api.graph_duplicate._service", lambda: stub)
    return stub


@pytest.fixture
def client(monkeypatch, service):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    install_api_error_handlers(app)
    app.register_blueprint(graph_bp, url_prefix="/api/graph")
    return app.test_client()


def _body(**kw: Any) -> Dict[str, Any]:
    body = {"client_request_id": str(uuid.uuid4()), "name": "Kopie A"}
    body.update(kw)
    return body


# ── Erfolg ───────────────────────────────────────────────────────────────


def test_duplicate_returns_202_with_job(client, service):
    body = _body()

    response = client.post(f"/api/graph/{GID}/duplicate", json=body)

    assert response.status_code == 202
    assert response.get_json()["data"] == {
        "run_id": "run_0123456789ab", "source_graph_id": GID, "graph_id": TARGET,
        "project_id": "proj_0123456789ab", "status": "pending", "progress": 0,
        "message": "Kopie angelegt", "error": None,
    }
    (graph_id, request), = service.calls
    assert graph_id == GID
    assert (request.client_request_id, request.name) == (body["client_request_id"], "Kopie A")


def test_repeated_request_is_passed_through_and_answers_202_again(client, service):
    body = _body()

    first = client.post(f"/api/graph/{GID}/duplicate", json=body)
    second = client.post(f"/api/graph/{GID}/duplicate", json=body)

    assert (first.status_code, second.status_code) == (202, 202)
    assert first.get_json()["data"] == second.get_json()["data"]


# ── Validierung ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Kopie"},
        {"client_request_id": "keine-uuid", "name": "Kopie"},
        {"client_request_id": str(uuid.uuid4())},
        {"client_request_id": str(uuid.uuid4()), "name": ""},
        {"client_request_id": str(uuid.uuid4()), "name": "   "},
        {"client_request_id": str(uuid.uuid4()), "name": "Kopie", "extra": 1},
    ],
    ids=["ohne-kennung", "kennung-keine-uuid", "ohne-name", "leerer-name", "nur-leerzeichen", "zusatzfeld"],
)
def test_invalid_body_is_rejected_with_400(client, service, body):
    response = client.post(f"/api/graph/{GID}/duplicate", json=body)

    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"
    assert service.calls == []


def test_non_object_body_is_rejected(client, service):
    response = client.post(f"/api/graph/{GID}/duplicate", json=[1, 2])

    assert response.status_code == 400
    assert service.calls == []


def test_invalid_graph_id_is_rejected_with_400(client, service):
    response = client.post("/api/graph/nicht-gueltig/duplicate", json=_body())

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"
    assert service.calls == []


# ── Fehlerabbildung ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (GraphDuplicateSourceNotFound(GID), 404, "not_found"),
        (GraphDuplicateSourceStateError("building"), 409, "graph_build_in_progress"),
        (GraphDuplicateSourceStateError("failed"), 400, "validation_failed"),
        (EmbeddingMigrationRunningError(GID), 409, "embedding_migration_running"),
    ],
    ids=["quelle-fehlt", "quelle-im-bau", "quelle-fehlgeschlagen", "migration-laeuft"],
)
def test_service_errors_map_to_envelopes(client, service, error, status, code):
    service.error = error

    response = client.post(f"/api/graph/{GID}/duplicate", json=_body())

    assert response.status_code == status
    assert response.get_json()["code"] == code


# ── Scopes ───────────────────────────────────────────────────────────────


@pytest.fixture
def secured_client(monkeypatch, tmp_path, service):
    """Wie ``test_scope_enforcement``: ``AGORA_AUTH_TOKEN`` gesetzt, damit ``require_scope`` greift."""
    monkeypatch.setenv("AGORA_FERNET_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "test-master-token-for-duplicate-tests")
    import app.services.api_keys_persistence as persistence
    from app.services import api_keys_store as store_module

    persistence._fernet_instance = None
    persistence._fernet_key_raw = None
    store_module._store_singleton = ApiKeysStore()
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    install_api_error_handlers(app)
    app.register_blueprint(graph_bp, url_prefix="/api/graph")
    yield app.test_client()
    store_module._store_singleton = ApiKeysStore()


def _key(scopes: list[str]) -> str:
    from app.services.api_keys_store import get_api_keys_store

    return get_api_keys_store().create("duplicate-test", scopes).token  # type: ignore[arg-type]


def test_duplicate_without_credentials_is_401(secured_client, service):
    response = secured_client.post(f"/api/graph/{GID}/duplicate", json=_body())

    assert response.status_code == 401
    assert service.calls == []


def test_duplicate_with_read_scope_is_403(secured_client, service):
    response = secured_client.post(
        f"/api/graph/{GID}/duplicate", json=_body(),
        headers={"Authorization": f"Bearer {_key(['read'])}"},
    )

    assert response.status_code == 403
    assert response.get_json()["required"] == "graph:write"
    assert service.calls == []


def test_duplicate_with_write_scope_is_202(secured_client, service):
    response = secured_client.post(
        f"/api/graph/{GID}/duplicate", json=_body(),
        headers={"Authorization": f"Bearer {_key(['write'])}"},
    )

    assert response.status_code == 202
