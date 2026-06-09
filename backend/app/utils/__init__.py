"""
Utilities Module
"""

from typing import Any

from .file_parser import FileParser

__all__ = ['FileParser', 'LLMClient']


def __getattr__(name: str) -> Any:
    # Lazy Re-Export (PEP 562): app.utils.llm_client importiert app.llm.* —
    # ein eager Import hier wuerde beim Import von app.llm.providers.* einen
    # Zirkular-Import ueber app.llm.retry → app.utils.retry ausloesen
    # (#582/#590). FileParser bleibt eager, LLMClient wird erst bei Zugriff
    # aufgeloest.
    if name == 'LLMClient':
        from .llm_client import LLMClient

        return LLMClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
