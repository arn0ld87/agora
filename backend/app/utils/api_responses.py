"""
Centralised Flask response helpers and a decorator for uniform API error handling.

The goal is to remove the boilerplate that accreted across the API blueprints,
where every handler wrapped its body in ``try/except Exception`` and hand-rolled
the same ``{"success": False, "error": ..., "traceback": ...}`` response.

The behaviour preserved by this module (used by the existing API surface):

- Successful JSON responses are shaped as ``{"success": True, ...}`` and, unless
  explicitly overridden, carry a top-level ``data`` field.
- Validation errors (``ValueError``) map to HTTP 400.
- Timeouts map to HTTP 504.
- Any other exception logs the stack trace and returns HTTP 500, optionally
  including ``traceback`` when ``Config.DEBUG`` is true.

The decorator never swallows domain results — it only kicks in on exceptions.
Handlers may continue to return ``Response`` objects, ``(Response, status)``
tuples, or raw dicts; the dict form is forwarded to :func:`json_success`.
"""

from __future__ import annotations

import functools
import traceback
from typing import Any, Callable, Mapping

from flask import jsonify

from ..config import Config
from ..utils.logger import get_logger


_default_logger = get_logger("agora.api")


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
    message: str,
    status: int = 400,
    *,
    code: str | None = None,
    include_traceback: bool = False,
    extra: Mapping[str, Any] | None = None,
):
    """
    Build a standard error envelope.

    Keeps the ``traceback`` field opt-in so that internal server errors can
    surface the trace in debug mode without changing the shape for 4xx errors.
    """
    payload: dict[str, Any] = {"success": False, "error": message}
    if code:
        payload["code"] = code
    if include_traceback:
        payload["traceback"] = traceback.format_exc()
    if extra:
        payload.update(extra)
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
    - ``TimeoutError`` → HTTP 504.
    - any other ``Exception`` → HTTP 500 with optional traceback (Config.DEBUG).

    The decorator deliberately does not catch :class:`BaseException` subclasses
    like ``SystemExit`` / ``KeyboardInterrupt``.
    """

    def decorator(view: Callable) -> Callable:
        active_logger = logger or _default_logger
        prefix = log_prefix or f"{view.__name__} failed"

        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            try:
                return view(*args, **kwargs)
            except ValueError as exc:
                return json_error(str(exc), status=400)
            except TimeoutError as exc:
                return json_error(f"{prefix}: timeout — {exc}", status=504)
            except Exception as exc:
                active_logger.error(f"{prefix}: {exc}")
                return json_error(
                    str(exc),
                    status=500,
                    include_traceback=bool(Config.DEBUG),
                )

        return wrapper

    if func is not None and callable(func):
        # Allow usage as bare decorator: @handle_api_errors
        return decorator(func)
    return decorator
