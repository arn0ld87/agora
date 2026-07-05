"""Gemeinsamer Retry-/Timeout-Layer der LLM-Runtime (Issue #590).

Re-Export von :func:`app.utils.retry.llm_call_with_retry` — die eine
Retry-Implementierung fuer alle Provider-Adapter und den ``LLMClient``.
Exponentielles Backoff mit Jitter; transient sind Verbindungsabbrueche,
Timeouts, HTTP 429 sowie 5xx/408 (siehe ``_is_transient_llm_error``).
"""
from __future__ import annotations

from app.utils.retry import llm_call_with_retry

__all__ = ["llm_call_with_retry"]