"""Shared response headers for legacy HTTP API routes."""

from flask import Response

# RFC 9745 Structured Field Date representing when this deprecation was announced.
# Fixed timestamp (2026-07-15 12:00:00 UTC) for deterministic tests.
_DEPRECATION_DATE = "@1752624000"


def add_legacy_deprecation_headers(response: Response) -> Response:
    """Mark a legacy response and point clients at the canonical successor."""
    response.headers["Deprecation"] = _DEPRECATION_DATE
    response.headers["X-Agora-Removal-Version"] = "1.0.0"
    response.headers["Link"] = '</api/llm/provider-connections>; rel="successor-version"'
    return response
