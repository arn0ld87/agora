"""Shim helper for resolving monkey-patched attributes from app.llm.client."""

from __future__ import annotations

import sys
from typing import Any

__all__ = ["get_client_attr", "_get_client_attr"]


def get_client_attr(name: str, default: Any = None) -> Any:
    """Resolve an attribute from the top-level ``app.llm.client`` module if present.

    Used by client mixins to support legacy tests and callers that patch
    symbols directly on ``app.llm.client`` (e.g., via
    ``unittest.mock.patch("app.llm.client.OpenAI")``).
    """
    mod = sys.modules.get("app.llm.client")
    if mod is not None and hasattr(mod, name):
        return getattr(mod, name)
    return default


_get_client_attr = get_client_attr
