"""LLM latency instrumentation.

`@measure_llm_latency` wraps any callable that performs an LLM round-trip
and emits a structured log line on completion (success or exception).
Used to baseline persona generation, report generation and other LLM-heavy
hot paths (Issue #217 Stufe 1: Messung vor Optimierung).
"""
from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger('agora.llm_latency')

F = TypeVar('F', bound=Callable[..., Any])


def measure_llm_latency(
    *,
    operation: Optional[str] = None,
    extract_model: Optional[Callable[..., Optional[str]]] = None,
    extract_prompt_chars: Optional[Callable[..., Optional[int]]] = None,
) -> Callable[[F], F]:
    """Decorator that emits a structured latency log per LLM-bearing call.

    Args:
        operation: Optional logical operation name (e.g. "persona_generation").
            Defaults to the wrapped function's qualname.
        extract_model: Optional callable (*args, **kwargs) -> Optional[str]
            that returns the model name from the call site.
        extract_prompt_chars: Optional callable (*args, **kwargs) -> Optional[int]
            that returns the total prompt character count from the call site.

    Logged keys: operation, function, latency_ms, roundtrips, success, model,
    prompt_chars, error_type (when success=False). Logger: 'agora.llm_latency'.
    """

    def _decorator(func: F) -> F:
        op_name = operation or func.__qualname__

        @functools.wraps(func)
        def _wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            success = True
            error_type: Optional[str] = None
            try:
                return func(*args, **kwargs)
            except BaseException as exc:
                success = False
                error_type = type(exc).__name__
                raise
            finally:
                latency_ms = (time.perf_counter() - start) * 1000.0
                model: Optional[str] = None
                prompt_chars: Optional[int] = None
                try:
                    if extract_model is not None:
                        model = extract_model(*args, **kwargs)
                except Exception:  # noqa: BLE001 — metrics collection; exc discarded
                    model = None
                try:
                    if extract_prompt_chars is not None:
                        prompt_chars = extract_prompt_chars(*args, **kwargs)
                except Exception:  # noqa: BLE001 — metrics collection; exc discarded
                    prompt_chars = None

                logger.info(
                    "llm_latency",
                    extra={
                        'operation': op_name,
                        'function': func.__qualname__,
                        'latency_ms': round(latency_ms, 2),
                        'roundtrips': 1,
                        'success': success,
                        'model': model,
                        'prompt_chars': prompt_chars,
                        'error_type': error_type,
                    },
                )

        return _wrapper  # type: ignore[return-value]

    return _decorator
