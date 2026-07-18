"""Shared response headers for legacy HTTP API routes."""

from flask import Response

# RFC 9745 Structured Field Date for the 2026-07-18 deprecation announcement.
_DEPRECATION_DATE = "@1784332800"


def add_legacy_deprecation_headers(response: Response) -> Response:
    """Mark a legacy response and point clients at the canonical successor."""
    response.headers["Deprecation"] = _DEPRECATION_DATE
    response.headers["X-Agora-Removal-Version"] = "1.0.0"
    response.headers["Link"] = '</api/llm/provider-connections>; rel="successor-version"'
    return response
