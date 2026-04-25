"""
API Call Retry Mechanism
Handles retry logic for external API calls like LLM and Neo4j.
Consolidated to use a single core loop logic for sync and async.
"""

import time
import random
import functools
import asyncio
from typing import Callable, Any, Optional, Type, Tuple
from ..utils.logger import get_logger

logger = get_logger('agora.retry')

# ---------------------------------------------------------------------------
# Core retry logic (internal)
# ---------------------------------------------------------------------------

class _RetryState:
    """Internal state tracker for a retry loop to ensure consistent behavior."""
    def __init__(
        self,
        max_retries: int,
        initial_delay: float,
        max_delay: float,
        backoff_factor: float,
        jitter: bool,
        func_name: str,
        on_retry: Optional[Callable[[Exception, int], None]] = None,
        logger_instance=None
    ):
        self.max_retries = max_retries
        self.delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.func_name = func_name
        self.on_retry = on_retry
        self.logger = logger_instance or logger

    def handle_failure(self, attempt: int, exc: Exception) -> float:
        """
        Handle a failed attempt. Logs appropriately and returns wait time.
        Raises the exception if retries are exhausted.
        """
        if attempt >= self.max_retries:
            self.logger.error(
                "%s still failed after %d retries: %s",
                self.func_name,
                self.max_retries,
                str(exc)
            )
            raise exc

        # Calculate delay
        wait_time = min(self.delay, self.max_delay)
        if self.jitter:
            # Jitter: multiply by a random factor in [0.5, 1.5]
            wait_time *= (0.5 + random.random())

        self.logger.warning(
            "%s (attempt %d/%d) failed: %s, retrying in %.1fs...",
            self.func_name,
            attempt + 1,
            self.max_retries + 1,
            str(exc),
            wait_time
        )

        if self.on_retry:
            self.on_retry(exc, attempt + 1)

        self.delay *= self.backoff_factor
        return wait_time


# ---------------------------------------------------------------------------
# Neo4j transient-failure retry helper
# ---------------------------------------------------------------------------

_NEO4J_TRANSIENT_EXCEPTIONS: Optional[Tuple[Type[Exception], ...]] = None


def _neo4j_transient_exceptions() -> Tuple[Type[Exception], ...]:
    """Return the tuple of Neo4j exception types that are safe to retry."""
    global _NEO4J_TRANSIENT_EXCEPTIONS
    if _NEO4J_TRANSIENT_EXCEPTIONS is None:
        try:
            from neo4j.exceptions import ServiceUnavailable, SessionExpired, TransientError
            _NEO4J_TRANSIENT_EXCEPTIONS = (ServiceUnavailable, SessionExpired, TransientError)
        except ImportError:
            # Fallback if neo4j is not installed
            _NEO4J_TRANSIENT_EXCEPTIONS = ()
    return _NEO4J_TRANSIENT_EXCEPTIONS


def neo4j_call_with_retry(
    func: Callable,
    *args,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    **kwargs,
) -> Any:
    """
    Execute *func* with retry logic tuned for Neo4j transient errors.

    Retries on ``ServiceUnavailable``, ``SessionExpired``, and
    ``TransientError``. Uses exponential backoff with jitter.

    Args:
        func:           Callable to execute.
        *args:          Positional arguments forwarded to *func*.
        max_retries:    Number of retries after the first attempt (default 3, total 4 attempts).
        initial_delay:  Base delay in seconds before the first retry (default 1.0).
        max_delay:      Upper cap on delay (default 10.0).
        backoff_factor: Multiplier applied to delay after each attempt (default 2.0).
        **kwargs:       Keyword arguments forwarded to *func*.

    Returns:
        The return value of *func* on success.
    """
    state = _RetryState(
        max_retries=max_retries,
        initial_delay=initial_delay,
        max_delay=max_delay,
        backoff_factor=backoff_factor,
        jitter=True,
        func_name="Neo4j call"
    )
    exceptions = _neo4j_transient_exceptions()

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            wait_time = state.handle_failure(attempt, e)
            time.sleep(wait_time)


# ---------------------------------------------------------------------------
# LLM transient-failure retry helper
# ---------------------------------------------------------------------------

_LLM_TRANSIENT_EXCEPTIONS: Optional[Tuple[Type[Exception], ...]] = None


def _llm_transient_exceptions() -> Tuple[Type[Exception], ...]:
    """Return the tuple of openai exception types that signal transient failure.

    Connection drops, timeouts and rate-limit responses are always retried.
    Generic ``APIStatusError`` is included so the per-call filter can decide
    based on ``status_code`` (only 5xx / 408 are treated as transient).
    """
    global _LLM_TRANSIENT_EXCEPTIONS
    if _LLM_TRANSIENT_EXCEPTIONS is None:
        try:
            from openai import (
                APIConnectionError,
                APITimeoutError,
                APIStatusError,
                RateLimitError,
            )
            _LLM_TRANSIENT_EXCEPTIONS = (
                APIConnectionError,
                APITimeoutError,
                RateLimitError,
                APIStatusError,
            )
        except ImportError:
            _LLM_TRANSIENT_EXCEPTIONS = ()
    return _LLM_TRANSIENT_EXCEPTIONS


def _is_transient_llm_error(exc: Exception) -> bool:
    """Return True iff *exc* is a retry-worthy LLM upstream failure.

    APIStatusError is only transient for 5xx and 408 (request timeout); 4xx
    client errors (400/401/403/404/422) must not be retried.
    """
    try:
        from openai import APIStatusError
    except ImportError:
        return True

    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        if status is None:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
        if status is None:
            return False
        return status >= 500 or status == 408 or status == 429
    return True


def llm_call_with_retry(
    func: Callable,
    *args,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    **kwargs,
) -> Any:
    """Execute *func* with retry logic tuned for OpenAI-compatible LLM calls.

    Retries on connection errors, timeouts, rate limits (429) and 5xx / 408
    responses. 4xx client errors fall through immediately. Uses exponential
    backoff with jitter — same shape as :func:`neo4j_call_with_retry`.
    """
    state = _RetryState(
        max_retries=max_retries,
        initial_delay=initial_delay,
        max_delay=max_delay,
        backoff_factor=backoff_factor,
        jitter=True,
        func_name="LLM call",
    )
    exceptions = _llm_transient_exceptions()

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            if not _is_transient_llm_error(e):
                raise
            wait_time = state.handle_failure(attempt, e)
            time.sleep(wait_time)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Retry decorator with exponential backoff.

    Args:
        max_retries: Number of retries after the first attempt (total attempts = max_retries + 1).
        initial_delay: Initial delay (seconds).
        max_delay: Max delay (seconds).
        backoff_factor: Backoff factor.
        jitter: Whether to add random jitter.
        exceptions: Exception types to retry.
        on_retry: Callback on retry (exception, retry_count).
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            state = _RetryState(
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay,
                backoff_factor=backoff_factor,
                jitter=jitter,
                func_name=f"Function {func.__name__}",
                on_retry=on_retry
            )
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    wait_time = state.handle_failure(attempt, e)
                    time.sleep(wait_time)
        return wrapper
    return decorator


def retry_with_backoff_async(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """Async version of retry decorator."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            state = _RetryState(
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay,
                backoff_factor=backoff_factor,
                jitter=jitter,
                func_name=f"Async function {func.__name__}",
                on_retry=on_retry
            )
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    wait_time = state.handle_failure(attempt, e)
                    await asyncio.sleep(wait_time)
        return wrapper
    return decorator


class RetryableAPIClient:
    """
    Retryable API client wrapper.
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

    def call_with_retry(
        self,
        func: Callable,
        *args,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        jitter: bool = True,
        on_retry: Optional[Callable[[Exception, int], None]] = None,
        func_name: str = "API call",
        **kwargs
    ) -> Any:
        """Execute function call with retry on failure."""
        state = _RetryState(
            max_retries=self.max_retries,
            initial_delay=self.initial_delay,
            max_delay=self.max_delay,
            backoff_factor=self.backoff_factor,
            jitter=jitter,
            func_name=func_name,
            on_retry=on_retry
        )
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                wait_time = state.handle_failure(attempt, e)
                time.sleep(wait_time)

    def call_batch_with_retry(
        self,
        items: list,
        process_func: Callable,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        continue_on_failure: bool = True
    ) -> Tuple[list, list]:
        """Batch call with individual retry for each failed item."""
        results = []
        failures = []

        for idx, item in enumerate(items):
            try:
                result = self.call_with_retry(
                    process_func,
                    item,
                    exceptions=exceptions,
                    func_name=f"Batch item {idx + 1}"
                )
                results.append(result)
            except Exception as e:
                logger.error("Failed to process item %d: %s", idx + 1, str(e))
                failures.append({
                    "index": idx,
                    "item": item,
                    "error": str(e)
                })
                if not continue_on_failure:
                    raise

        return results, failures
