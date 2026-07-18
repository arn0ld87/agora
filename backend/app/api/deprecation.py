"""Shared response headers for legacy HTTP API routes."""

from flask import Response


def add_legacy_deprecation_headers(response: Response) -> Response:
    """Mark a legacy response and point clients at the canonical successor."""
    response.headers["Deprecation"] = "true"
    response.headers["X-Agora-Removal-Version"] = "1.0.0"
    response.headers["Link"] = '</api/llm/provider-connections>; rel="successor-version"'
    return response
