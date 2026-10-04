"""Gekürzte Providermeldungen ohne erkennbare Secrets (#1738, #1772).

Aus ``services/report_agent/workflow.py`` herausgelöst, damit der
Simulations-Subprozess (``scripts/sim_runtime/budget_guard.py``) dieselbe
Redaktion nutzt, ohne das Report-Workflow-Modul samt seiner Importe zu laden.
Das Verhalten ist unverändert; ``max_chars`` ist der einzige neue Parameter.
"""
from __future__ import annotations

import re

DEFAULT_PROVIDER_MESSAGE_MAX_CHARS = 240

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-*]{4,}"),
    re.compile(r"\bago_[A-Za-z0-9_\-]{4,}"),
    # Bis zum naechsten Trennzeichen: Base64-Token enthalten auch ``+``, ``/``, ``=``.
    re.compile(r"(?i)\bbearer\s+[^\s'\",;]+"),
    re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password)\b(['\"]?\s*[:=]\s*)['\"]?[^\s'\",;]+"
    ),
)


def redacted_provider_message(
    exc: BaseException,
    *,
    max_chars: int = DEFAULT_PROVIDER_MESSAGE_MAX_CHARS,
) -> str:
    """Gekürzte Providermeldung ohne erkennbare Secrets.

    Bevorzugt ``exc.body["message"]`` (OpenAI-SDK), sonst ``str(exc)``.
    Whitespace wird zusammengezogen, Schlüssel (``sk-…``, ``ago_…``,
    ``Bearer …``, ``api_key=…``) werden durch ``[redacted]`` ersetzt, danach
    auf ``max_chars`` gekürzt. Request-Header und Prompt werden nie gelesen.
    """
    body = getattr(exc, "body", None)
    raw = ""
    if isinstance(body, dict):
        raw = str(body.get("message") or "")
    if not raw:
        raw = str(exc)
    text = " ".join(raw.split())
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", text)
        else:
            text = pattern.sub("[redacted]", text)
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text
