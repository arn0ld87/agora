"""Auth endpoints — short-lived signed tickets for URL-bound flows (P0.2b).

Browsers cannot set custom headers on ``EventSource`` or anchor downloads,
so the API guard historically accepted ``?token=<bearer>`` as a fallback.
That leaks the long-lived bearer into proxy logs, browser history, and
Referer chains. ``POST /api/auth/ticket`` mints a 60s, scope-bound,
single-use ticket that the client appends to those URLs instead. The
ticket itself carries no secret — it is HMAC-signed with ``SECRET_KEY``.
"""

from __future__ import annotations

from flask import Blueprint, current_app, request

from ..utils import signed_ticket
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import json_error, json_success
from ..utils.rate_limit import build_rate_limit_key, ticket_rate_limiter

auth_bp = Blueprint("auth", __name__)

_DEFAULT_TTL_SECONDS = 60
_MAX_TTL_SECONDS = 300

_ALLOWED_SCOPE_PREFIXES = (
    "sse:",
    "settings-stream",
    "download:report:",
    "download:simulation_config:",
    "download:simulation_script:",
    "llm-stream",  # Slice E.1 (#213): model-active SSE stream
)


def _scope_is_allowed(scope: str) -> bool:
    if not scope or "." in scope:
        return False
    return any(scope.startswith(prefix) for prefix in _ALLOWED_SCOPE_PREFIXES)


def _ticket_rate_limit_key() -> str:
    return build_rate_limit_key("auth-ticket")


@auth_bp.before_request
def _limit_ticket_endpoint():
    if request.endpoint != "auth.issue_ticket" or request.method != "POST":
        return None

    result = ticket_rate_limiter.check(
        _ticket_rate_limit_key(),
        max_requests=current_app.config["AGORA_TICKET_RATE_LIMIT_MAX"],
        window_seconds=current_app.config["AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS"],
    )
    if result.allowed:
        return None

    response, status = json_error(
        ApiErrorCode.RATE_LIMITED,
        status=429,
        extra={"retry_after_seconds": result.retry_after_seconds},
    )
    response.headers["Retry-After"] = str(result.retry_after_seconds)
    return response, status


@auth_bp.route("/ticket", methods=["POST"])
def issue_ticket():
    payload = request.get_json(silent=True) or {}
    scope = (payload.get("scope") or "").strip()
    if not _scope_is_allowed(scope):
        return json_error("invalid scope", status=400, code="invalid_scope")

    ttl_raw = payload.get("ttl_seconds", _DEFAULT_TTL_SECONDS)
    try:
        ttl = int(ttl_raw)
    except (TypeError, ValueError):
        return json_error("ttl_seconds must be an integer", status=400, code="invalid_ttl")
    if ttl <= 0 or ttl > _MAX_TTL_SECONDS:
        return json_error(
            f"ttl_seconds must be in (0, {_MAX_TTL_SECONDS}]",
            status=400,
            code="invalid_ttl",
        )

    secret = current_app.config.get("SECRET_KEY") or ""
    if not secret:
        return json_error("server misconfigured: SECRET_KEY missing", status=500, code="no_secret")

    ticket = signed_ticket.issue(secret, scope, ttl_seconds=ttl)
    # Re-derive expiry locally so the client doesn't have to parse the ticket.
    parsed = signed_ticket._parse(ticket)
    exp = parsed[1] if parsed else None
    return json_success({"ticket": ticket, "exp": exp, "scope": scope})
