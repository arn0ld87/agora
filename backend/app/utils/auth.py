"""
Schlanke Token-Auth für alle /api-Endpoints.

Aktiv sobald ``AGORA_AUTH_TOKEN`` gesetzt ist. Fehlt die Env-Variable, läuft der
Backend im offenen Modus (nützlich für Dev / erste Clone-Versuche), gibt aber
beim Start ein lautes Warning.

Token wird erwartet in einem von:
  - Header ``X-Agora-Token: <token>``
  - Header ``Authorization: Bearer <token>``
  - Query-Param ``?token=<token>`` (nur als Fallback für Downloads, bei denen
    Browser keine Custom-Header setzen — siehe ``send_file``-Flows)
"""

from __future__ import annotations

import hmac
import os
from functools import wraps

from flask import Blueprint, Flask, jsonify, request


def _expected_token() -> str:
    return os.environ.get("AGORA_AUTH_TOKEN", "")


def _extract_token() -> str:
    hdr = request.headers.get("X-Agora-Token")
    if hdr:
        return hdr
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.args.get("token", "")


def token_required(view):
    """Decorator für einzelne Views. Kein-Op wenn ``AGORA_AUTH_TOKEN`` leer ist."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        expected = _expected_token()
        if not expected:
            return view(*args, **kwargs)
        got = _extract_token()
        if not got or not hmac.compare_digest(got, expected):
            return jsonify({"error": "unauthorized", "code": "auth_required"}), 401
        return view(*args, **kwargs)

    return wrapper


def install_blueprint_guard(bp: Blueprint) -> None:
    """Hängt den Token-Check als ``before_request``-Hook an ein Blueprint."""

    @bp.before_request
    def _check_token():
        expected = _expected_token()
        if not expected:
            return None
        got = _extract_token()
        if not got or not hmac.compare_digest(got, expected):
            return jsonify({"error": "unauthorized", "code": "auth_required"}), 401
        return None


def log_auth_mode(app: Flask, logger) -> None:
    if _expected_token():
        logger.info("Auth: AGORA_AUTH_TOKEN aktiv — /api/* verlangt Token.")
    else:
        logger.warning(
            "Auth: AGORA_AUTH_TOKEN nicht gesetzt — /api/* ist offen. "
            "Nur für lokale Entwicklung akzeptabel."
        )
