from __future__ import annotations

from flask import Flask, Response

from app.api import llm_bp
from app.api.llm_providers import add_provider_deprecation_headers


def test_provider_prefix_collision_is_not_marked_as_legacy():
    app = Flask(__name__)
    with app.test_request_context("/api/llm/providers-preview"):
        response = add_provider_deprecation_headers(Response())

    assert "Deprecation" not in response.headers


def test_legacy_header_follows_endpoint_under_prefix_containing_providers():
    """Ein Blueprint-Prefix darf selbst ein ``providers``-Segment enthalten."""
    app = Flask(__name__)
    app.register_blueprint(llm_bp, url_prefix="/api/tenants/providers")

    with app.test_request_context("/api/tenants/providers/providers/openai/models"):
        legacy = add_provider_deprecation_headers(Response())
    with app.test_request_context("/api/tenants/providers/provider-connections"):
        canonical = add_provider_deprecation_headers(Response())

    assert legacy.headers["Deprecation"] == "@1784332800"
    assert "Deprecation" not in canonical.headers
