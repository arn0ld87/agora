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

Seit ADR-0018 (#1613) kennt der Guard ``AGORA_AUTH_BACKEND``:

* ``legacy`` — genau der Pfad oben.
* ``hybrid`` (Default) — zusätzlich und zuerst ein Supabase-JWT im
  ``Authorization: Bearer``-Header, sofern JWT konfiguriert ist. Ohne diese
  Konfiguration ist ``hybrid`` gleich ``legacy``.
* ``supabase`` — JWT und ``ago_``-Keys; der Master-Token wird abgelehnt, einen
  offenen Modus gibt es nicht.

Jeder erfolgreiche Zugang legt einen ``Principal`` ab
(:mod:`app.security.principal_context`). Tickets tragen den Principal ihres
Ausstellers in der signierten Scope-Bindung; mit aktivem JWT gilt nur ein
gebundenes Ticket.
"""

from __future__ import annotations

import hmac
import os
from functools import wraps
from typing import Callable

from flask import Blueprint, Flask, current_app, request

from . import signed_ticket
from .api_responses import json_error
from ..config import (
    Config,
    supabase_jwt_configured,
    supabase_jwt_settings,
    validate_auth_backend,
)
from ..contracts.auth_contract import AuthType, Principal
from ..security.principal_context import (
    WORKSPACE_HEADER,
    current_principal,
    WorkspaceSelectionError,
    get_jwt_verifier,
    legacy_principal,
    resolve_jwt_principal,
    set_principal,
    split_bound_scope,
)
from ..security.supabase_jwt import JwtVerificationError, looks_like_jwt
from ..services.api_keys_store import get_api_keys_store
from .logger import get_logger

_logger = get_logger("agora.auth")
_TICKET_SCOPE_ATTR = "_agora_ticket_scope_fn"
_TICKET_SINGLE_USE_ATTR = "_agora_ticket_single_use"


def _auth_error(code: str = "auth_required"):
    return json_error("unauthorized", status=401, code=code)


def _jwt_enabled() -> bool:
    """JWT-Zweig aktiv: Modus ``hybrid``/``supabase``, JWT konfiguriert **und**
    die Invariante aus ADR-0018 erfüllt.

    Die Invariante wird hier selbst geprüft, nicht nur in ``Config.validate()``:
    mit ``FLASK_DEBUG`` protokolliert ``create_app`` Validierungsfehler nur und
    startet trotzdem. Ein JWT-Zweig ohne Workspace-Isolation wäre dann offen
    (Codex-Review auf #1622). Scheitert die Prüfung, bleibt JWT aus.
    """
    if Config.AUTH_BACKEND not in ("hybrid", "supabase") or not supabase_jwt_configured(Config):
        return False
    return _jwt_invariant_holds()


def _jwt_invariant_holds() -> bool:
    errors = validate_auth_backend(Config)
    if errors:
        _logger.error(
            "auth: Supabase-JWT bleibt aus — Konfiguration verletzt ADR-0018 (%d Fehler, "
            "siehe Config.validate()).",
            len(errors),
        )
        return False
    return True


def _master_token_allowed() -> bool:
    return Config.AUTH_BACKEND != "supabase"


def _bearer_value() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


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


def _try_consume_ticket(jwt_enabled: bool) -> Principal | None:
    """Principal eines gültigen Tickets oder ``None``.

    Der Scope im Ticket ist ``<basis>`` oder ``<basis>@<bindung>``; die
    Signatur deckt beides. Die Basis muss zum Endpunkt passen. Mit aktivem
    JWT gilt nur ein gebundenes Ticket — ein ungebundenes käme sonst mit
    Owner-Rechten im Default-Workspace durch.
    """
    ticket = request.args.get("ticket", "").strip()
    if not ticket:
        return None
    meta = _ticket_view_metadata()
    if meta is None:
        return None
    expected_scope, single_use = meta
    secret = current_app.config.get("SECRET_KEY") or ""
    if not secret:
        return None
    full_scope = signed_ticket.scope_of(ticket)
    if full_scope is None:
        return None
    base_scope, principal = split_bound_scope(full_scope)
    if base_scope != expected_scope:
        return None
    if principal is None:
        if jwt_enabled or "@" in full_scope:
            return None
        principal = legacy_principal(AuthType.MASTER_TOKEN)
    if single_use:
        ok = signed_ticket.consume(secret, ticket, full_scope)
    else:
        ok = signed_ticket.verify(secret, ticket, full_scope)
    return principal if ok else None


def _authenticate_jwt(token: str):
    settings = supabase_jwt_settings(Config)
    assert settings is not None  # _jwt_enabled() hat das geprüft
    try:
        claims = get_jwt_verifier(settings).verify(token)
    except JwtVerificationError as exc:
        # Nur der Code, nie Token oder Claims.
        _logger.info("auth: JWT rejected (%s) on %s", exc.code.value, request.path)
        return _auth_error("invalid_token")
    from ..repositories.workspace_repository import get_workspace_repository

    try:
        principal = resolve_jwt_principal(
            claims, request.headers.get(WORKSPACE_HEADER), get_workspace_repository()
        )
    except WorkspaceSelectionError as exc:
        return json_error(exc.code, status=exc.status, code=exc.code)
    set_principal(principal)
    return None


def _authenticate(*, allow_tickets: bool):
    """Gemeinsamer Kern von Blueprint-Guard und ``token_required``.

    Gibt ``None`` zurück, wenn der Request zugelassen ist (der Principal liegt
    dann in ``flask.g``), sonst die Fehlerantwort.
    """
    jwt_enabled = _jwt_enabled()

    # 1. Supabase-JWT. Ein Bearer in JWT-Form wird nie als Master-Token
    #    verglichen: ist er ungültig, ist der Request abgelehnt.
    bearer = _bearer_value()
    if jwt_enabled and bearer and looks_like_jwt(bearer):
        return _authenticate_jwt(bearer)

    expected = _expected_token() if _master_token_allowed() else ""
    got = _extract_token()

    # 2. Master-Token (nicht im Modus ``supabase``)
    if expected and got and hmac.compare_digest(got, expected):
        set_principal(legacy_principal(AuthType.MASTER_TOKEN))
        return None

    # 3. Workspace-API-Keys
    if got and _check_api_key(got):
        set_principal(legacy_principal(AuthType.API_KEY))
        return None

    # 4. Signierte Tickets
    if allow_tickets:
        principal = _try_consume_ticket(jwt_enabled)
        if principal is not None:
            set_principal(principal)
            return None

    # 5. Offener Modus: nur ohne Master-Token, ohne JWT und nicht im Modus
    #    ``supabase``.
    if not expected and not jwt_enabled and _master_token_allowed():
        set_principal(legacy_principal(AuthType.ANONYMOUS))
        return None

    return _auth_error()


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
    """Decorator für einzelne Views; dieselben Regeln wie der Blueprint-Guard,
    ohne Tickets."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        denied = _authenticate(allow_tickets=False)
        if denied is not None:
            return denied
        return view(*args, **kwargs)

    return wrapper


# Attribute, die install_blueprint_guard auf dem Blueprint hinterlegt, um
# Mehrfach-Installation des Hooks zu verhindern (Blueprints sind Modul-Level-
# Singletons und können von mehreren Apps/Tests wiederverwendet werden).
_GUARD_INSTALLED_ATTR = "_agora_guard_installed"
_GUARD_TOKEN_ONLY_ATTR = "_agora_guard_token_only"  # noqa: S105 - Attributname, kein Secret
_GUARD_TENANT_ACCESS_ATTR = "_agora_guard_tenant_access"


def install_blueprint_guard(
    bp: Blueprint,
    *,
    token_only_endpoints: frozenset[str] | None = None,
    tenant_access: bool = True,
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

    ``tenant_access=False`` sperrt das Blueprint für Supabase-Nutzer (JWT):
    es verwaltet prozessweiten Zustand (Provider-Keys, API-Keys, Logs,
    Onboarding), der allen Workspaces gemeinsam ist. Zugang haben dann nur
    Master-Token, ``ago_``-Keys und der offene Modus (ADR-0018).

    Idempotent: Der Hook wird genau einmal pro Blueprint installiert; weitere
    Aufrufe aktualisieren nur ``token_only_endpoints`` und ``tenant_access``
    (letzter Aufruf gewinnt).
    Funktioniert auch, wenn das Blueprint bereits auf einer App registriert
    wurde (z. B. weiteres ``create_app()`` im selben Prozess oder geteilte
    Blueprint-Singletons in Tests): In dem Fall greift der Guard für alle
    *künftigen* Registrierungen; bereits registrierte Apps bleiben unverändert.
    """
    setattr(bp, _GUARD_TOKEN_ONLY_ATTR, token_only_endpoints or frozenset())
    setattr(bp, _GUARD_TENANT_ACCESS_ATTR, tenant_access)
    if getattr(bp, _GUARD_INSTALLED_ATTR, False):
        return

    def _check_token():
        # CORS-Preflight: OPTIONS trägt keine Auth-Header (by-design im Browser).
        # Flask-CORS hängt die Allow-*-Header via after_request an; wir müssen die
        # Preflight durchwinken, sonst sieht der Browser 401 und blockt den Folge-Request.
        if request.method == "OPTIONS":
            return None

        _token_only = getattr(bp, _GUARD_TOKEN_ONLY_ATTR, frozenset())
        denied = _authenticate(allow_tickets=request.endpoint not in _token_only)
        if denied is not None:
            return denied
        principal = current_principal()
        if (
            not getattr(bp, _GUARD_TENANT_ACCESS_ATTR, True)
            and principal is not None
            and principal.auth_type == AuthType.JWT
        ):
            return json_error("forbidden", status=403, code="operator_only")
        return None

    if bp._got_registered_once:
        # Flask verbietet ``bp.before_request()`` nach der ersten Registrierung
        # (Setup-Finished-Check).  Der Hook landet hier direkt im
        # ``before_request_funcs``-Dict des Blueprints — exakt das, was
        # ``before_request`` intern tut.  Flask merged dieses Dict bei jeder
        # Erst-Registrierung pro App (``_merge_blueprint_funcs``), d. h. alle
        # künftigen Apps erhalten den Guard; bereits registrierte nicht.
        bp.before_request_funcs.setdefault(None, []).append(_check_token)
    else:
        bp.before_request(_check_token)

    setattr(bp, _GUARD_INSTALLED_ATTR, True)


def _allow_anonymous() -> bool:
    return os.environ.get("AGORA_ALLOW_ANONYMOUS", "false").lower() in (
        "true",
        "1",
        "yes",
    )


def log_auth_mode(app: Flask, logger) -> None:
    mode = Config.AUTH_BACKEND
    if _jwt_enabled():
        logger.info(
            "Auth: AGORA_AUTH_BACKEND=%s — Supabase-JWT aktiv (Issuer konfiguriert), "
            "Workspace-Isolation über PostgreSQL.",
            mode,
        )
    elif mode == "hybrid":
        # ADR-0018: ohne JWT-Konfiguration ist hybrid exakt legacy — das
        # soll im Log stehen, nicht erraten werden.
        logger.info(
            "Auth: AGORA_AUTH_BACKEND=hybrid ohne AGORA_SUPABASE_JWT_ISSUER — "
            "JWT-Zweig inaktiv, Verhalten wie legacy."
        )
    if mode == "supabase":
        return
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
