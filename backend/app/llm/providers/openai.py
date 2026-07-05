"""
OpenAI-specific request quirks: token-limit-key naming
(``max_tokens`` vs. ``max_completion_tokens``) and 400-response detection.

Extracted verbatim from ``LLMClient`` staticmethods in
``app/utils/llm_client.py`` as part of issue #582 (mechanical split — no
behavior change).
"""

from typing import Any, Dict, Optional


def uses_max_completion_tokens(model: str) -> bool:
    """Whether *model* requires ``max_completion_tokens`` instead of ``max_tokens``.

    GPT-5 / o1 / o3 / o4 verlangen max_completion_tokens; OpenAI antwortet
    sonst 400 "Unsupported parameter: 'max_tokens'". Heuristik gespiegelt
    aus backend/scripts/_sim_common.py::uses_max_completion_tokens —
    Single Source of Truth bleibt dort, hier nur die zweite Stelle.
    Striktes Prefix-Matching ("gpt-5", "gpt-5-…") verhindert
    Mismatches wie hypothetisches "gpt-500".
    """
    lowered = (model or "").strip().lower()
    for prefix in ("gpt-5", "o1", "o3", "o4"):
        if lowered == prefix or lowered.startswith(f"{prefix}-") or lowered.startswith(f"{prefix}."):
            return True
    return False


def is_token_key_400(exc: Exception) -> bool:
    """True wenn ein OpenAI-/Proxy-400 auf eine Token-Limit-Key-Inkompatibilität hindeutet.

    Erkennt beide Richtungen, je nachdem welcher Schlüssel im Request stand:
    - „'max_tokens' is not supported with this model. Use 'max_completion_tokens'"
    - „'max_completion_tokens' is not supported …" / Unsupported parameter

    Wird von ``chat()`` als Fallback-Retry-Trigger genutzt — Heuristik
    kann z. B. bei einem neuen OpenAI-kompatiblen Proxy daneben liegen,
    und dann reicht der Wortlaut der Antwort als Fallback.
    """
    try:
        from openai import APIStatusError
    except ImportError:
        APIStatusError = ()  # type: ignore[assignment]

    if APIStatusError and isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        if status is None:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
        if status != 400:
            return False
    msg = str(exc).lower()
    if "max_tokens" not in msg and "max_completion_tokens" not in msg:
        return False
    return (
        "not supported" in msg
        or "unsupported parameter" in msg
        or "use 'max_completion_tokens'" in msg
        or "use 'max_tokens'" in msg
        or "use max_completion_tokens" in msg
        or "use max_tokens" in msg
    )


def swap_token_kwargs(kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Liefert eine Kopie von *kwargs* mit getauschtem Token-Limit-Schlüssel,
    oder ``None`` wenn keiner der beiden Schlüssel gesetzt ist.
    """
    swapped = dict(kwargs)
    if "max_tokens" in swapped:
        value = swapped.pop("max_tokens")
        swapped["max_completion_tokens"] = value
        return swapped
    if "max_completion_tokens" in swapped:
        value = swapped.pop("max_completion_tokens")
        swapped["max_tokens"] = value
        return swapped
    return None
