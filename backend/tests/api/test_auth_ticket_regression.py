import re
from pathlib import Path
import pytest
from flask import Flask
from app.api.auth import auth_bp, _scope_is_allowed
from app.utils.api_responses import install_api_error_handlers
from app.utils.auth import install_blueprint_guard

SECRET = "test-secret-do-not-use"
TOKEN = "test-token"

@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config["SECRET_KEY"] = SECRET
    flask_app.config["AGORA_TICKET_RATE_LIMIT_MAX"] = 100
    flask_app.config["AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS"] = 60
    install_api_error_handlers(flask_app)

    install_blueprint_guard(auth_bp)
    flask_app.register_blueprint(auth_bp, url_prefix="/api/auth")
    return flask_app

@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", TOKEN)
    return app.test_client()

def test_logs_stream_scope_is_allowed(client):
    """Verifies that 'logs:stream' is allowed (the fix)."""
    response = client.post(
        "/api/auth/ticket",
        json={"scope": "logs:stream"},
        headers={"X-Agora-Token": TOKEN},
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["scope"] == "logs:stream"
    assert "ticket" in data

def find_ticket_scopes():
    api_dir = Path(__file__).parent.parent.parent / "app" / "api"
    scopes = set()

    # Regex for literals: @allow_ticket_auth(lambda ...: f?"([^"]+)"
    regex_literal = re.compile(r'@allow_ticket_auth\(lambda.*?:\s*f?["\']([^"\']+)["\']')
    # Regex for variables: @allow_ticket_auth(lambda ...: ([A-Z_][A-Z0-9_]*)
    regex_var = re.compile(r'@allow_ticket_auth\(lambda.*?:\s*([A-Z_][A-Z0-9_]*)')

    for python_file in api_dir.glob("*.py"):
        content = python_file.read_text()
        for match in regex_literal.finditer(content):
            scope_raw = match.group(1)
            # If it has {param}, take the prefix
            if "{" in scope_raw:
                scopes.add(scope_raw.split("{")[0])
            else:
                scopes.add(scope_raw)

        for match in regex_var.finditer(content):
            var_name = match.group(1)
            # Find the variable definition in the same file
            var_regex = re.compile(rf'^{var_name}\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
            var_match = var_regex.search(content)
            if var_match:
                scopes.add(var_match.group(1))

    return sorted(list(scopes))

@pytest.mark.parametrize("scope_prefix", find_ticket_scopes())
def test_all_discovered_scopes_are_whitelisted(scope_prefix):
    """Regression gate: every scope used in @allow_ticket_auth must be whitelisted in auth.py."""
    # We append 'dummy' to prefixes that end in ':' to simulate a real scope.
    test_scope = scope_prefix + "dummy" if scope_prefix.endswith(":") else scope_prefix
    assert _scope_is_allowed(test_scope), (
        f"Scope '{test_scope}' (derived from '{scope_prefix}') is not whitelisted in _ALLOWED_SCOPE_PREFIXES. "
        "Please add it to backend/app/api/auth.py."
    )
