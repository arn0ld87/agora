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
from ..services.api_keys_store import get_api_keys_store
from .logger import get_logger

_logger = get_logger("agora.auth")
_TICKET_SCOPE_ATTR = "_agora_ticket_scope_fn"
_TICKET_SINGLE_USE_ATTR = "_agora_ticket_single_use"


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
        if not current_app.debug:
            # In Prod: ?token= ist deaktiviert (F2.2). Signed-Tickets nutzen.
            _logger.error(
                "auth: ?token= query rejected in production on %s — "
                "use signed tickets (POST /api/auth/ticket).",
                request.path,
            )
            return ""
        _logger.warning(
            "auth: ?token= query fallback used on %s — switch to signed tickets "
            "(see /api/auth/ticket).",
            request.path,
        )
    return query_token


def allow_ticket_auth(scope_fn: Callable[..., str], *, single_use: bool = True):
    """Mark a view as accepting ``?ticket=`` auth in addition to the bearer
    token. ``scope_fn`` receives the URL view kwargs and must return the
    expected ticket scope, e.g. ``lambda simulation_id: f"sse:{simulation_id}"``.

    ``single_use=True`` (default) consumes the ticket on first hit and
    rejects replays. SSE endpoints set this to ``False`` so an
    ``EventSource`` can reconnect within the ticket TTL — replay protection
    falls back to the short TTL alone.
    """

    def decorator(view):
        setattr(view, _TICKET_SCOPE_ATTR, scope_fn)
        setattr(view, _TICKET_SINGLE_USE_ATTR, single_use)
        return view

    return decorator


def _ticket_view_metadata() -> tuple[str, bool] | None:
    endpoint = request.endpoint
    if not endpoint:
        return None
    view = current_app.view_functions.get(endpoint)
    if view is None:
        return None
    scope_fn = getattr(view, _TICKET_SCOPE_ATTR, None)
    if scope_fn is None:
        return None
    single_use = bool(getattr(view, _TICKET_SINGLE_USE_ATTR, True))
    try:
        scope = scope_fn(**(request.view_args or {}))
    except Exception:  # noqa: BLE001
        _logger.exception("ticket scope_fn raised for %s", endpoint)
        return None
    return scope, single_use


def _try_consume_ticket() -> bool:
    ticket = request.args.get("ticket", "").strip()
    if not ticket:
        return False
    meta = _ticket_view_metadata()
    if meta is None:
        return False
    expected_scope, single_use = meta
    secret = current_app.config.get("SECRET_KEY") or ""
    if not secret:
        return False
    if single_use:
        return signed_ticket.consume(secret, ticket, expected_scope)
    return signed_ticket.verify(secret, ticket, expected_scope)


def _check_api_key(token: str) -> bool:
    """Prüft ob der Token ein gültiger ago_... API-Key ist."""
    if not token.startswith("ago_"):
        return False
    store = get_api_keys_store()
    key = store.validate_token(token)
    if key and key.status == "active":
        return True
    if key and key.status == "revoked":
        _logger.warning("auth: revoked API key used (prefix=%s)", key.prefix)
    return False


def token_required(view):
    """Decorator für einzelne Views. Kein-Op wenn ``AGORA_AUTH_TOKEN`` leer ist."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        expected = _expected_token()
        got = _extract_token()

        # 1. AGORA_AUTH_TOKEN (Master)
        if expected and got and hmac.compare_digest(got, expected):
            return view(*args, **kwargs)

        # 2. Workspace API Keys (ago_...)
        if got and _check_api_key(got):
            return view(*args, **kwargs)

        # 3. Open mode fallback (only if no master token configured)
        if not expected:
            return view(*args, **kwargs)

        return _auth_error()

    return wrapper


def install_blueprint_guard(
    bp: Blueprint,
    *,
    token_only_endpoints: frozenset[str] | None = None,
) -> None:
    """Hängt den Token-Check als ``before_request``-Hook an ein Blueprint.

    Akzeptiert Master-Token, Workspace-API-Keys (ago_...) oder signierte Tickets.

    ``token_only_endpoints`` benennt Flask-Endpoint-Strings (z. B.
    ``frozenset({"auth.issue_ticket"})``), die **kein** Signed-Ticket als
    Authentifizierungsmittel akzeptieren.  Master-Token und API-Keys greifen
    weiterhin.  Gedacht für den Ticket-Ausstellungs-Endpoint selbst, damit der
    Browser ein abgelaufenes Ticket erneuern kann ohne das Henne-Ei-Problem:
    POST /api/auth/ticket benötigt kein gültiges Ticket, aber einen gültigen
    Session-Token (Master-Token oder API-Key).
    """
    _token_only: frozenset[str] = token_only_endpoints or frozenset()

    @bp.before_request
    def _check_token():
        # CORS-Preflight: OPTIONS trägt keine Auth-Header (by-design im Browser).
        # Flask-CORS hängt die Allow-*-Header via after_request an; wir müssen die
        # Preflight durchwinken, sonst sieht der Browser 401 und blockt den Folge-Request.
        if request.method == "OPTIONS":
            return None

        expected = _expected_token()
        got = _extract_token()

        # 1. Master Token
        if expected and got and hmac.compare_digest(got, expected):
            return None

        # 2. Workspace API Keys
        if got and _check_api_key(got):
            return None

        # 3. Signed Tickets — übersprungen für token_only_endpoints
        if request.endpoint not in _token_only and _try_consume_ticket():
            return None

        # 4. Open mode fallback
        if not expected:
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
