import httpx
import openai
from unittest import mock

from app.contracts.provider_types import PROVIDER_OLLAMA, PROVIDER_OPENAI
from app.llm.errors import normalize_provider_error


class DummyRequest:
    pass


class DummyResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.request = DummyRequest()
        self.headers = {}


class DummyExceptionWithStatus(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__("DummyExceptionWithStatus")


def test_normalize_openai_timeout():
    exc = openai.APITimeoutError(request=DummyRequest())
    err = normalize_provider_error(exc, provider=PROVIDER_OPENAI)
    assert err.provider == PROVIDER_OPENAI
    assert err.code == "timeout"
    assert err.retryable is True


def test_normalize_openai_connection():
    exc = openai.APIConnectionError(request=DummyRequest())
    err = normalize_provider_error(exc, provider=PROVIDER_OPENAI)
    assert err.provider == PROVIDER_OPENAI
    assert err.code == "connection_error"
    assert err.retryable is True


def test_normalize_openai_rate_limit():
    exc = openai.RateLimitError(
        message="Too Many Requests", response=DummyResponse(429), body=None
    )
    err = normalize_provider_error(exc, provider=PROVIDER_OPENAI)
    assert err.provider == PROVIDER_OPENAI
    assert err.code == "rate_limited"
    assert err.status == 429
    assert err.retryable is True


def test_normalize_openai_server_error():
    exc = openai.APIStatusError(
        message="Internal Server Error", response=DummyResponse(500), body=None
    )
    err = normalize_provider_error(exc, provider=PROVIDER_OPENAI)
    assert err.provider == PROVIDER_OPENAI
    assert err.code == "server_error"
    assert err.status == 500
    assert err.retryable is True


def test_normalize_openai_client_error():
    exc = openai.APIStatusError(
        message="Bad Request", response=DummyResponse(400), body=None
    )
    err = normalize_provider_error(exc, provider=PROVIDER_OPENAI)
    assert err.provider == PROVIDER_OPENAI
    assert err.code == "client_error"
    assert err.status == 400
    assert err.retryable is False


def test_normalize_openai_status_408():
    exc = openai.APIStatusError(
        message="Request Timeout", response=DummyResponse(408), body=None
    )
    err = normalize_provider_error(exc, provider=PROVIDER_OPENAI)
    assert err.provider == PROVIDER_OPENAI
    assert err.code == "client_error"
    assert err.status == 408
    assert err.retryable is True


def test_normalize_httpx_timeout():
    exc = httpx.TimeoutException("timeout")
    err = normalize_provider_error(exc, provider=PROVIDER_OLLAMA)
    assert err.provider == PROVIDER_OLLAMA
    assert err.code == "timeout"
    assert err.retryable is True


def test_normalize_httpx_error():
    exc = httpx.ConnectError("connection failed")
    err = normalize_provider_error(exc, provider=PROVIDER_OLLAMA)
    assert err.provider == PROVIDER_OLLAMA
    assert err.code == "connection_error"
    assert err.retryable is True


def test_normalize_unknown_error():
    exc = ValueError("unknown error")
    err = normalize_provider_error(exc, provider=PROVIDER_OPENAI)
    assert err.provider == PROVIDER_OPENAI
    assert err.code == "unknown"
    assert err.retryable is False


def test_status_extraction_from_status_code_property():
    exc = DummyExceptionWithStatus(418)

    original_isinstance = isinstance

    def mock_isinstance(obj, class_or_tuple):
        if class_or_tuple == openai.APIStatusError and isinstance(
            obj, DummyExceptionWithStatus
        ):
            return True
        return original_isinstance(obj, class_or_tuple)

    with mock.patch("app.llm.errors.isinstance", side_effect=mock_isinstance, create=True):
        err = normalize_provider_error(exc, provider=PROVIDER_OPENAI)
        assert err.status == 418


def test_status_extraction_from_response_status_code_property():
    class DummyExceptionWithResponse(Exception):
        def __init__(self, response):
            self.response = response
            super().__init__("DummyExceptionWithResponse")

    exc = DummyExceptionWithResponse(DummyResponse(419))

    original_isinstance = isinstance

    def mock_isinstance(obj, class_or_tuple):
        if class_or_tuple == openai.APIStatusError and isinstance(
            obj, DummyExceptionWithResponse
        ):
            return True
        return original_isinstance(obj, class_or_tuple)

    with mock.patch("app.llm.errors.isinstance", side_effect=mock_isinstance, create=True):
        err = normalize_provider_error(exc, provider=PROVIDER_OPENAI)
        assert err.status == 419


def test_llm_provider_error_exception():
    from app.contracts.llm_request import NormalizedLlmError
    from app.llm.errors import LlmProviderError

    normalized = NormalizedLlmError(
        provider=PROVIDER_OPENAI,
        code="rate_limited",
        message="Too many requests",
        retryable=True,
    )

    exc = LlmProviderError(normalized)
    assert str(exc) == "[openai:rate_limited] Too many requests"
    assert exc.normalized == normalized
