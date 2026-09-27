"""Demo-Vorschau (#1688): JWT-Readonly-Allowlist für Betreiber-Endpoints.

Öffentliche Demo-Instanz (``AGORA_DEMO_MODE=true``): JWT-Besucherinnen sehen
sonst nur den 403 ``operator_only`` (siehe ``tests/security/test_hybrid_auth_guard.py::
test_operator_blueprints_are_closed_to_jwt_users``). Für eine geprüfte,
kleine Menge lesender Endpoints (``app.utils.auth.DEMO_READONLY_OPERATOR_ENDPOINTS``)
lässt der Guard GET/HEAD jetzt durch, wenn zusätzlich ``AGORA_DEMO_MODE``
aktiv ist. Mutationen und alle anderen Betreiber-Endpoints bleiben in jedem
Modus 403.

Guard-Fixtures spiegeln ``test_hybrid_auth_guard.py``: eine Mini-App mit
frischen ``Blueprint``-Objekten, deren Namen exakt auf die
``<blueprint>.<funktion>``-Strings in ``DEMO_READONLY_OPERATOR_ENDPOINTS``
passen — ohne den echten ``llm_bp``/``onboarding_bp``-Singleton anzufassen
(der Guard-Hook ist pro Blueprint-Objekt einmalig und würde sonst über die
Testsession hinweg an anderen Tests kleben bleiben, die dieselben
Singletons unguarded registrieren, z. B. ``tests/api/test_provider_connections_api.py``).
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

import jwt
import pytest
from flask import Blueprint, Flask, jsonify

from app.config import WORKSPACE_SCOPED_BACKENDS, Config
from app.contracts.workspace_contract import Workspace, WorkspaceMembership, WorkspaceRole
from app.security import principal_context
from app.utils import auth as auth_module
from app.utils import signed_ticket
from app.utils.auth import DEMO_READONLY_OPERATOR_ENDPOINTS, install_blueprint_guard

ISSUER = "https://supabase.example.test/auth/v1"
SECRET = "j" * 40
USER = uuid.UUID("11111111-2222-4333-8444-555555555555")
WS_A = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)


class _FakeWorkspaces:
    def membership(self, workspace_id, user_id):
        if user_id != USER or workspace_id != WS_A:
            return None
        return WorkspaceMembership(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER, created_at=NOW
        )

    def list_for_user(self, user_id):
        if user_id != USER:
            return []
        return [Workspace(workspace_id=WS_A, name="W", slug="w", created_at=NOW, updated_at=NOW)]


def _token(**overrides: Any) -> str:
    now = int(time.time())
    claims = {"sub": str(USER), "iss": ISSUER, "aud": "authenticated", "iat": now, "exp": now + 600}
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def _bearer() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}"}


@pytest.fixture
def demo_guard_client(monkeypatch):
    """Mini-App mit ``llm``- und ``logs``-benannten Fake-Blueprints, deren
    Endpoints exakt auf ``DEMO_READONLY_OPERATOR_ENDPOINTS`` passen."""

    monkeypatch.setattr(Config, "AUTH_BACKEND", "hybrid")
    monkeypatch.setattr(Config, "SUPABASE_JWT_ISSUER", ISSUER)
    monkeypatch.setattr(Config, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(Config, "SUPABASE_JWKS_URL", "")
    monkeypatch.setattr("app.config.TENANT_ISOLATION_AVAILABLE", True)
    monkeypatch.delenv("AGORA_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.setattr(Config, "DATABASE_URL", "postgresql+psycopg://u:p@db:5432/agora")
    for _, attr in WORKSPACE_SCOPED_BACKENDS:
        monkeypatch.setattr(Config, attr, "postgres")
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(
        "app.repositories.workspace_repository.get_workspace_repository", lambda: _FakeWorkspaces()
    )
    monkeypatch.setattr(auth_module, "_check_api_key", lambda token: False)
    principal_context.reset_jwt_verifier()
    signed_ticket._reset_seen_for_tests()

    llm = Blueprint("llm", __name__)

    @llm.route("/provider-connections", methods=["GET", "PUT"])
    def list_provider_connections():
        return jsonify({"ok": True})

    @llm.route("/providers/api-keys", methods=["GET"])
    def list_provider_api_keys():
        return jsonify({"ok": True})

    logs = Blueprint("logs", __name__)

    @logs.route("/", methods=["GET"])
    def stream_logs():
        return jsonify({"ok": True})

    install_blueprint_guard(llm, tenant_access=False)
    install_blueprint_guard(logs, tenant_access=False)
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "ticket-secret-for-tests"
    app.register_blueprint(llm, url_prefix="/api/llm")
    app.register_blueprint(logs, url_prefix="/api/logs")
    yield app.test_client()
    principal_context.reset_jwt_verifier()


def test_allowlisted_get_passes_in_demo_mode_for_jwt(demo_guard_client, monkeypatch):
    monkeypatch.setenv("AGORA_DEMO_MODE", "true")

    response = demo_guard_client.get("/api/llm/provider-connections", headers=_bearer())

    assert response.status_code == 200


def test_allowlisted_endpoints_mutation_stays_forbidden_in_demo_mode(demo_guard_client, monkeypatch):
    monkeypatch.setenv("AGORA_DEMO_MODE", "true")

    response = demo_guard_client.put("/api/llm/provider-connections", headers=_bearer())

    assert (response.status_code, response.get_json()["code"]) == (403, "operator_only")


def test_non_allowlisted_operator_get_stays_forbidden_in_demo_mode(demo_guard_client, monkeypatch):
    """Weder Provider-API-Keys noch der Logs-Stream gehören zum Allowlist."""
    monkeypatch.setenv("AGORA_DEMO_MODE", "true")

    api_keys = demo_guard_client.get("/api/llm/providers/api-keys", headers=_bearer())
    logs = demo_guard_client.get("/api/logs/", headers=_bearer())

    assert (api_keys.status_code, api_keys.get_json()["code"]) == (403, "operator_only")
    assert (logs.status_code, logs.get_json()["code"]) == (403, "operator_only")


def test_allowlisted_get_stays_forbidden_outside_demo_mode(demo_guard_client, monkeypatch):
    monkeypatch.delenv("AGORA_DEMO_MODE", raising=False)

    response = demo_guard_client.get("/api/llm/provider-connections", headers=_bearer())

    assert (response.status_code, response.get_json()["code"]) == (403, "operator_only")


def test_allowlist_names_the_five_verified_read_endpoints():
    """Drift-Wächter: die Allowlist bleibt eine bewusst geprüfte, kleine
    Menge — keine stille Erweiterung ohne erneute Prüfung (siehe Kommentar
    bei ``DEMO_READONLY_OPERATOR_ENDPOINTS`` in ``app/utils/auth.py``)."""
    assert DEMO_READONLY_OPERATOR_ENDPOINTS == frozenset(
        {
            "llm.list_providers",
            "llm.list_provider_connections",
            "llm.get_routing_defaults",
            "llm.list_embedding_configurations",
            "onboarding.get_onboarding_status",
        }
    )


def test_master_token_is_unaffected_by_the_demo_allowlist(demo_guard_client, monkeypatch):
    """Die Allowlist ist ein JWT-spezifischer Sonderfall, kein genereller
    Freibrief — Master-Token-Zugriff war ohnehin schon erlaubt."""
    monkeypatch.setenv("AGORA_DEMO_MODE", "true")
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "master-token-for-tests")

    response = demo_guard_client.put(
        "/api/llm/provider-connections", headers={"X-Agora-Token": "master-token-for-tests"}
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Masking-Entscheidung (Spec-Punkt 2): base_url bleibt unmaskiert.
# ---------------------------------------------------------------------------
#
# ``ProviderConnection.base_url`` ist als ``PublicBaseUrl | LocalOllamaBaseUrl``
# typisiert (app/contracts/ai_provider_contract.py) und das Frontend parst
# die Antwort strikt gegen den gespiegelten Zod-Schema (``unwrapAndParse``,
# kein Silent-Fallback bei Schema-Drift, siehe frontend/src/contracts/
# aiProviderContract.ts:119). Ein Platzhalter wie "(vom Betreiber verwaltet)"
# ist keine valide URL und würde die Demo-Vorschau der Integrations-Seite
# crashen — der Spec-Fallback "wenn URL-typisiert, unmaskiert lassen und
# vermerken" greift. ``EmbeddingConfiguration`` trägt gar kein Base-URL-Feld
# (nur ``provider_connection_id`` als Referenz). Es gibt also aktuell kein
# Feld, das der Maskierungs-Helper in diesen beiden Endpoints greifen könnte;
# die folgenden Tests dokumentieren das als Regression gegen ein künftiges
# Wieder-Einführen einer stillen Maskierung, die die Verträge brechen würde.


def test_provider_connections_response_keeps_base_url_intact(monkeypatch):
    from datetime import datetime, timezone as _tz

    from flask import Flask as _Flask

    from app.api import llm_bp
    from app.contracts.ai_provider_contract import ProviderConnection

    connection = ProviderConnection(
        id="openai",
        provider_kind="openai",
        display_name="OpenAI",
        transport="http",
        auth_mode="api_key",
        base_url="https://api.openai.com/v1",
        secret_ref="openai",
        created_at=datetime.now(_tz.utc),
        updated_at=datetime.now(_tz.utc),
    )

    class _Store:
        def list_connections(self):
            return [connection]

    monkeypatch.setattr(
        "app.api.llm_providers.get_provider_connection_store", lambda: _Store(), raising=False
    )

    app = _Flask(__name__)
    app.register_blueprint(llm_bp, url_prefix="/api/llm")
    client = app.test_client()

    response = client.get("/api/llm/provider-connections")

    assert response.status_code == 200
    assert response.get_json()["data"]["items"][0]["base_url"] == "https://api.openai.com/v1"


def test_embedding_configuration_contract_has_no_base_url_field():
    from app.contracts.embedding_contract import EmbeddingConfiguration

    assert "base_url" not in EmbeddingConfiguration.model_fields
