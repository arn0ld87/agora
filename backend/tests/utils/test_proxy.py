from __future__ import annotations

from flask import Flask, request

from app.utils.rate_limit import build_rate_limit_key
from app.utils.proxy import apply_proxy_fix


def _client_ip_app(*, x_for: int = 0, x_proto: int = 0) -> Flask:
    app = Flask(__name__)
    app.config.update(
        AGORA_PROXY_FIX_X_FOR=x_for,
        AGORA_PROXY_FIX_X_PROTO=x_proto,
        AGORA_PROXY_FIX_X_HOST=0,
        AGORA_PROXY_FIX_X_PORT=0,
        AGORA_PROXY_FIX_X_PREFIX=0,
    )
    apply_proxy_fix(app)

    @app.get("/")
    def index():
        return {
            "key": build_rate_limit_key("auth-ticket"),
            "remote_addr": request.remote_addr,
            "scheme": request.scheme,
        }

    return app


def test_proxy_fix_is_opt_in_and_ignores_spoofed_forwarded_for_by_default():
    client = _client_ip_app().test_client()

    response = client.get(
        "/",
        environ_base={"REMOTE_ADDR": "172.18.0.5"},
        headers={"X-Forwarded-For": "198.51.100.23", "X-Forwarded-Proto": "https"},
    )

    assert response.get_json() == {
        "key": "auth-ticket:172.18.0.5",
        "remote_addr": "172.18.0.5",
        "scheme": "http",
    }


def test_proxy_fix_uses_forwarded_client_when_one_proxy_is_trusted():
    client = _client_ip_app(x_for=1, x_proto=1).test_client()

    response = client.get(
        "/",
        environ_base={"REMOTE_ADDR": "172.18.0.5"},
        headers={"X-Forwarded-For": "198.51.100.23", "X-Forwarded-Proto": "https"},
    )

    assert response.get_json() == {
        "key": "auth-ticket:198.51.100.23",
        "remote_addr": "198.51.100.23",
        "scheme": "https",
    }


def test_rate_limit_key_uses_jwt_identity_instead_of_shared_proxy_address():
    """#1688: behind Cloudflare/Traefik/nginx every visitor may share one
    ``remote_addr`` — JWT principals get their own bucket."""
    from uuid import UUID

    from app.contracts.auth_contract import AuthType, Principal
    from app.contracts.workspace_contract import WorkspaceRole
    from app.security.principal_context import set_principal

    app = Flask(__name__)
    users = {
        "a": UUID("11111111-1111-4111-8111-111111111111"),
        "b": UUID("33333333-3333-4333-8333-333333333333"),
    }

    @app.get("/<who>")
    def index(who):
        set_principal(Principal(
            auth_type=AuthType.JWT,
            user_id=users[who],
            workspace_id=UUID("22222222-2222-4222-8222-222222222222"),
            roles=frozenset({WorkspaceRole.MEMBER}),
        ))
        return {"key": build_rate_limit_key("llm")}

    client = app.test_client()
    key_a = client.get("/a").get_json()["key"]
    key_b = client.get("/b").get_json()["key"]

    assert key_a != key_b
    assert str(users["a"]) in key_a
    assert "127.0.0.1" not in key_a
