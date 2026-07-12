"""
Centralised Flask response helpers and a decorator for uniform API error handling.

The goal is to remove the boilerplate that accreted across the API blueprints,
where every handler wrapped its body in ``try/except Exception`` and hand-rolled
the same ``{"success": False, "error": ...}`` response.

The behaviour preserved by this module (used by the existing API surface):

- Successful JSON responses are shaped as ``{"success": True, ...}`` and, unless
  explicitly overridden, carry a top-level ``data`` field.
- Validation errors (``ValueError``) map to HTTP 400.
- Timeouts map to HTTP 504.
- Any other exception logs the stack trace and returns a security-safe HTTP 500
  envelope. Production responses do not expose exception strings.

The decorator never swallows domain results — it only kicks in on exceptions.
Handlers may continue to return ``Response`` objects, ``(Response, status)``
tuples, or raw dicts; the dict form is forwarded to :func:`json_success`.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from typing import Any, Callable

from flask import jsonify, request
from pydantic_core import to_jsonable_python
from werkzeug.exceptions import HTTPException

from ..config import Config
from ..utils.logger import get_logger
from .api_errors import DEFAULT_MESSAGES, ApiErrorCode


_default_logger = get_logger("agora.api")
_INTERNAL_ERROR_MESSAGE = "internal server error"
_TIMEOUT_ERROR_MESSAGE = "request timed out"

# Map ApiErrorCode → semantic HTTP status when raised through the service
# exception path. Anything not listed keeps the caller-supplied default
# (400 for ValueError, 500 for RuntimeError). The map is deliberately small:
# direct ``json_error(code, status=...)`` calls pick their status explicitly,
# and adding entries here can silently change the API contract for existing
# endpoints — only add a mapping when the previous contract was also a bug.
_API_ERROR_STATUS_MAP: dict[ApiErrorCode, int] = {
    ApiErrorCode.NOT_FOUND: 404,
    ApiErrorCode.GRAPH_BUILD_IN_PROGRESS: 409,
}


def _extract_api_error_code(exc: BaseException) -> ApiErrorCode | None:
    """Return the ``ApiErrorCode`` carried by a service exception, if any.

    Supports both ``raise ValueError(ApiErrorCode.NOT_FOUND)`` and the legacy
    ``raise ValueError("not_found")`` style, where the string matches an enum
    value.
    """
    if not exc.args:
        return None
    first = exc.args[0]
    if isinstance(first, ApiErrorCode):
        return first
    if isinstance(first, str):
        try:
            return ApiErrorCode(first)
        except ValueError:
            return None
    return None


def json_error_from_exception(
    exc: BaseException,
    *,
    fallback_status: int = 400,
):
    """Translate a service-raised exception into a uniform error response.

    - ``Exception(ApiErrorCode.X)`` → looks up the semantic HTTP status in
      ``_API_ERROR_STATUS_MAP`` and returns ``json_error(code, status=mapped)``.
    - Legacy string messages → ``json_error(str(exc), status=fallback_status)``
      without a ``code`` field, preserving the historical wire format.
    """
    code = _extract_api_error_code(exc)
    if code is not None:
        status = _API_ERROR_STATUS_MAP.get(code, fallback_status)
        return json_error(code, status=status)
    return json_error(str(exc), status=fallback_status)


def _debug_extra(exc: Exception) -> dict[str, Any] | None:
    if not Config.DEBUG:
        return None
    return {"debug_error": str(exc)}


def _http_error_code(error: HTTPException) -> str:
    return (error.name or "http_error").lower().replace(" ", "_")


def _to_jsonable(value: Any) -> Any:
    """Recursively coerce ``value`` into something :func:`flask.jsonify` accepts.

    Pydantic v2 ``ValidationError.errors()`` returns dicts whose ``ctx`` field
    can carry a live ``ValueError`` instance — and Flask's default JSON encoder
    rejects those, turning a 400 into a 500. This helper walks the value with
    :func:`pydantic_core.to_jsonable_python`, which knows how to coerce
    Pydantic-specific types (``SecretStr``, ``Url``, ``datetime``,
    ``Decimal`` …) and arbitrary exceptions to JSON-safe forms
    (``Exception`` → ``str(exc)``).

    Keeping the helper local to ``api_responses`` makes the contract explicit:
    every envelope produced by this module is guaranteed to be serializable
    by Flask without further munging.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, BaseException):
        return str(value)
    # ``fallback=str`` ist die letzte Verteidigungslinie: wenn weder
    # Pydantics eingebauter Coercer noch die obige Exception-Klausel
    # greifen, wird der Wert in seinen String-Repr überführt, statt eine
    # ``PydanticSerializationError``-Escalation in einen HTTP 500 zu
    # verwandeln.
    return to_jsonable_python(value, fallback=str)


def json_success(data: Any = None, *, status: int = 200, **extra: Any):
    """
    Build a standard success envelope.

    ``data`` — when provided — is attached as the ``"data"`` field. Additional
    keyword arguments (e.g. ``count=3``) are merged into the top-level envelope
    so handlers can keep returning existing shapes unchanged.
    """
    payload: dict[str, Any] = {"success": True}
    if data is not None:
        payload["data"] = data
    if extra:
        payload.update(extra)
    return jsonify(payload), status


def json_error(
    error: str | ApiErrorCode,
    status: int = 400,
    *,
    code: str | None = None,
    message: str | None = None,
    include_traceback: bool = False,
    extra: Mapping[str, Any] | None = None,
):
    """
    Build a standard error envelope.

    Two call styles:

    - ``json_error("Frei formulierter Text", status=400)`` — Legacy-Pfad,
      Body ohne ``code`` (oder mit explizit übergebenem ``code=...``).
    - ``json_error(ApiErrorCode.INVALID_ID, status=400)`` — Code-Pfad,
      ``code`` und Default-Message werden aus dem Katalog gezogen. Über
      ``message="..."`` lässt sich die Default-Message punktuell überschreiben,
      ohne den Code zu verlieren.

    ``include_traceback`` is kept for call-site compatibility but intentionally
    ignored: stack traces stay in server logs and are never serialized to JSON.
    """
    if isinstance(error, ApiErrorCode):
        resolved_code = code or error.value
        resolved_text = message if message is not None else DEFAULT_MESSAGES[error]
    else:
        resolved_code = code
        resolved_text = message if message is not None else error

    payload: dict[str, Any] = {"success": False, "error": resolved_text}
    if resolved_code:
        payload["code"] = resolved_code
    if extra:
        # ``extra`` may carry Pydantic ``ValidationError.errors()`` payloads
        # whose ``ctx`` field contains live ``ValueError`` instances. We
        # sanitize defensively so that any 4xx stays a 4xx instead of
        # being downgraded to a 500 by Flask's JSON encoder.
        payload.update(_to_jsonable(dict(extra)))
    return jsonify(payload), status


def handle_api_errors(
    func: Callable | None = None,
    *,
    logger=None,
    log_prefix: str | None = None,
):
    """
    Decorator that centralises error handling for Flask view functions.

    Usage::

        @simulation_bp.route('/foo', methods=['POST'])
        @handle_api_errors(log_prefix="Failed to foo")
        def foo():
            ...
            return json_success(result)

    - ``ValueError`` → HTTP 400 with ``{"success": False, "error": str(exc)}``.
    - ``TimeoutError`` → HTTP 504 with a safe public message.
    - any other ``Exception`` → HTTP 500 with a safe public message.

    The decorator deliberately does not catch :class:`BaseException` subclasses
    like ``SystemExit`` / ``KeyboardInterrupt``.
    """

    def decorator(view: Callable) -> Callable:
        active_logger = logger or _default_logger
        prefix = log_prefix or f"{view.__name__} failed"

        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            try:
                result = view(*args, **kwargs)
                if isinstance(result, Mapping):
                    return json_success(dict(result))
                return result
            except ValueError as exc:
                return json_error_from_exception(exc, fallback_status=400)
            except RuntimeError as exc:
                # Domain-level conflicts (e.g. GRAPH_BUILD_IN_PROGRESS) raise
                # RuntimeError(ApiErrorCode.X). Anything without an ApiErrorCode
                # payload still degrades to a 500.
                if _extract_api_error_code(exc) is not None:
                    return json_error_from_exception(exc, fallback_status=500)
                active_logger.exception(f"{prefix}: {exc}")
                return json_error(
                    _INTERNAL_ERROR_MESSAGE,
                    status=500,
                    code="internal_error",
                    include_traceback=bool(Config.DEBUG),
                    extra=_debug_extra(exc),
                )
            except TimeoutError as exc:
                active_logger.warning(f"{prefix}: timeout: {exc}")
                return json_error(
                    _TIMEOUT_ERROR_MESSAGE,
                    status=504,
                    code="timeout",
                    extra=_debug_extra(exc),
                )
            except Exception as exc:
                active_logger.exception(f"{prefix}: {exc}")
                return json_error(
                    _INTERNAL_ERROR_MESSAGE,
                    status=500,
                    code="internal_error",
                    include_traceback=bool(Config.DEBUG),
                    extra=_debug_extra(exc),
                )

        return wrapper

    if func is not None and callable(func):
        # Allow usage as bare decorator: @handle_api_errors
        return decorator(func)
    return decorator


def install_api_error_handlers(app) -> None:
    """Install app-level JSON envelopes for framework-raised API errors."""

    @app.errorhandler(404)
    def _api_not_found(error):
        if request.path.startswith("/api/"):
            return json_error("not found", status=404, code="not_found")
        return error

    @app.errorhandler(405)
    def _api_method_not_allowed(error):
        if request.path.startswith("/api/"):
            return json_error("method not allowed", status=405, code="method_not_allowed")
        return error

    @app.errorhandler(HTTPException)
    def _api_http_exception(error):
        if request.path.startswith("/api/"):
            if (error.code or 500) >= 500:
                return json_error(
                    _INTERNAL_ERROR_MESSAGE,
                    status=error.code or 500,
                    code=_http_error_code(error),
                )
            return json_error(
                error.description or error.name or "request failed",
                status=error.code or 400,
                code=_http_error_code(error),
            )
        return error

    @app.errorhandler(Exception)
    def _api_unhandled_exception(error):
        if isinstance(error, HTTPException):
            return error
        if request.path.startswith("/api/"):
            _default_logger.exception("Unhandled API exception: %s", error)
            return json_error(
                _INTERNAL_ERROR_MESSAGE,
                status=500,
                code="internal_error",
                include_traceback=bool(Config.DEBUG),
                extra=_debug_extra(error),
            )
        raise error
