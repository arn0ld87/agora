"""
Schlanke Token-Auth für alle /api-Endpoints.

Aktiv sobald ``AGORA_AUTH_TOKEN`` gesetzt ist. Fehlt die Env-Variable, läuft der
Backend im offenen Modus (nützlich für Dev / erste Clone-Versuche), gibt aber
beim Start ein lautes Warning.

Token wird erwartet in einem von:
  - Header ``X-Agora-Token: <token>``
  - Header ``Authorization: Bearer <token>``
  - Query-Param ``?token=<token>`` (Deprecation-Warning seit P0.2 — nur als
    Last-Resort-Fallback, wird durch signierte Kurzzeit-Tickets abgelöst.)

Endpoints, deren URL der Browser nicht signieren kann (SSE, Anchor-Downloads),
können sich mit ``@allow_ticket_auth(scope_fn)`` markieren. Der Guard
akzeptiert dann zusätzlich ein ``?ticket=<signed>``-Query-Param, validiert
und konsumiert es via :mod:`app.utils.signed_ticket`.
"""

from __future__ import annotations

import hmac
import os
from functools import wraps
from typing import Callable

from flask import Blueprint, Flask, current_app, request

from . import signed_ticket
from .api_responses import json_error
from .logger import get_logger

_logger = get_logger("agora.auth")
_TICKET_SCOPE_ATTR = "_agora_ticket_scope_fn"


def _auth_error():
    return json_error("unauthorized", status=401, code="auth_required")


def _expected_token() -> str:
    return os.environ.get("AGORA_AUTH_TOKEN", "")


def _extract_token() -> str:
    hdr = request.headers.get("X-Agora-Token")
    if hdr:
        return hdr
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    query_token = request.args.get("token", "")
    if query_token:
        _logger.warning(
            "auth: ?token= query fallback used on %s — switch to signed tickets "
            "(see /api/auth/ticket).",
            request.path,
        )
    return query_token


def allow_ticket_auth(scope_fn: Callable[..., str]):
    """Mark a view as accepting ``?ticket=`` auth in addition to the bearer
    token. ``scope_fn`` receives the URL view kwargs and must return the
    expected ticket scope, e.g. ``lambda simulation_id: f"sse:{simulation_id}"``.
    """

    def decorator(view):
        setattr(view, _TICKET_SCOPE_ATTR, scope_fn)
        return view

    return decorator


def _ticket_scope_for_request() -> str | None:
    endpoint = request.endpoint
    if not endpoint:
        return None
    view = current_app.view_functions.get(endpoint)
    if view is None:
        return None
    scope_fn = getattr(view, _TICKET_SCOPE_ATTR, None)
    if scope_fn is None:
        return None
    try:
        return scope_fn(**(request.view_args or {}))
    except Exception:  # noqa: BLE001
        _logger.exception("ticket scope_fn raised for %s", endpoint)
        return None


def _try_consume_ticket() -> bool:
    ticket = request.args.get("ticket", "").strip()
    if not ticket:
        return False
    expected_scope = _ticket_scope_for_request()
    if expected_scope is None:
        return False
    secret = current_app.config.get("SECRET_KEY") or ""
    if not secret:
        return False
    return signed_ticket.consume(secret, ticket, expected_scope)


def token_required(view):
    """Decorator für einzelne Views. Kein-Op wenn ``AGORA_AUTH_TOKEN`` leer ist."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        expected = _expected_token()
        if not expected:
            return view(*args, **kwargs)
        got = _extract_token()
        if not got or not hmac.compare_digest(got, expected):
            return _auth_error()
        return view(*args, **kwargs)

    return wrapper


def install_blueprint_guard(bp: Blueprint) -> None:
    """Hängt den Token-Check als ``before_request``-Hook an ein Blueprint.

    Akzeptiert Header/Bearer/``?token=`` Token. Wenn der View mit
    ``@allow_ticket_auth`` markiert ist, wird zusätzlich ein ``?ticket=``
    versucht — passend signiert, frisch und mit korrektem Scope reicht das
    aus, ohne dass der Bearer in der URL stehen muss.
    """

    @bp.before_request
    def _check_token():
        expected = _expected_token()
        if not expected:
            return None
        got = _extract_token()
        if got and hmac.compare_digest(got, expected):
            return None
        if _try_consume_ticket():
            return None
        return _auth_error()


def _allow_anonymous() -> bool:
    return os.environ.get("AGORA_ALLOW_ANONYMOUS", "false").lower() in (
        "true",
        "1",
        "yes",
    )


def log_auth_mode(app: Flask, logger) -> None:
    if _expected_token():
        logger.info("Auth: AGORA_AUTH_TOKEN aktiv — /api/* verlangt Token.")
        return

    debug_mode = bool(app.config.get("DEBUG"))
    if _allow_anonymous():
        logger.warning(
            "Auth: AGORA_ALLOW_ANONYMOUS=true — /api/* offen, opt-in erteilt. "
            "Nicht für Prod-Deployments."
        )
    elif debug_mode:
        logger.warning(
            "Auth: AGORA_AUTH_TOKEN nicht gesetzt — /api/* ist offen "
            "(FLASK_DEBUG aktiv, akzeptabel für lokale Entwicklung)."
        )
    else:
        # Sollte Config.validate() bereits abgefangen haben; lautes Signal
        # falls jemand die Validation umgangen hat.
        logger.error(
            "Auth: kein Token, kein Allow-Flag, kein Debug — /api/* offen. "
            "Config.validate() hätte das blocken müssen."
        )
