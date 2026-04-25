import pytest
from unittest.mock import Mock, patch
from app.utils.retry import (
    retry_with_backoff,
    retry_with_backoff_async,
    RetryableAPIClient,
    neo4j_call_with_retry,
    llm_call_with_retry,
)

class TestRetryUtilities:
    """Test suite for consolidated retry utilities."""

    def test_sync_retry_success_immediate(self):
        """Test sync decorator succeeds on first try."""
        mock_func = Mock(return_value="success")

        @retry_with_backoff(max_retries=3)
        def decorated():
            return mock_func()

        result = decorated()
        assert result == "success"
        assert mock_func.call_count == 1

    def test_sync_retry_success_after_retries(self):
        """Test sync decorator succeeds after some failures."""
        mock_func = Mock(side_effect=[ValueError("fail1"), ValueError("fail2"), "success"])

        @retry_with_backoff(max_retries=3, initial_delay=0.01, jitter=False)
        def decorated():
            return mock_func()

        result = decorated()
        assert result == "success"
        assert mock_func.call_count == 3

    def test_sync_retry_permanent_failure(self):
        """Test sync decorator raises after exhausting retries."""
        mock_func = Mock(side_effect=ValueError("permanent fail"))

        @retry_with_backoff(max_retries=2, initial_delay=0.01, jitter=False)
        def decorated():
            return mock_func()

        with pytest.raises(ValueError, match="permanent fail"):
            decorated()
        assert mock_func.call_count == 3 # 1 initial + 2 retries

    def test_sync_retry_non_retryable_exception(self):
        """Test sync decorator propagates non-whitelisted exceptions immediately."""
        mock_func = Mock(side_effect=TypeError("not retryable"))

        @retry_with_backoff(max_retries=3, exceptions=(ValueError,))
        def decorated():
            return mock_func()

        with pytest.raises(TypeError, match="not retryable"):
            decorated()
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_success_after_retries(self):
        """Test async decorator succeeds after some failures."""
        mock_func = Mock(side_effect=[ValueError("fail1"), "success"])

        @retry_with_backoff_async(max_retries=3, initial_delay=0.01, jitter=False)
        async def decorated_async():
            return mock_func()

        result = await decorated_async()
        assert result == "success"
        assert mock_func.call_count == 2

    @pytest.mark.asyncio
    async def test_async_retry_permanent_failure(self):
        """Test async decorator raises after exhausting retries."""
        mock_func = Mock(side_effect=ValueError("permanent fail"))

        @retry_with_backoff_async(max_retries=2, initial_delay=0.01, jitter=False)
        async def decorated_async():
            return mock_func()

        with pytest.raises(ValueError, match="permanent fail"):
            await decorated_async()
        assert mock_func.call_count == 3

    def test_retryable_api_client_batch(self):
        """Test OO wrapper batch processing with retries."""
        client = RetryableAPIClient(max_retries=1, initial_delay=0.01)

        def process(item):
            if item == "fail":
                raise ValueError("item fail")
            return f"ok_{item}"

        items = ["a", "fail", "b"]
        # We don't have jitter param in client constructor, so we might get jitter if we don't pass it to call_with_retry
        # But for test it doesn't matter much if it's small delay
        results, failures = client.call_batch_with_retry(items, process)

        assert results == ["ok_a", "ok_b"]
        assert len(failures) == 1
        assert failures[0]["item"] == "fail"
        assert "item fail" in failures[0]["error"]

    def test_neo4j_retry_logic(self):
        """Test Neo4j specific retry helper."""
        from neo4j.exceptions import ServiceUnavailable

        mock_func = Mock(side_effect=[ServiceUnavailable("down"), "connected"])

        # We need to mock _neo4j_transient_exceptions to ensure ServiceUnavailable is included
        # even if neo4j package is not fully functional in test env
        with patch('app.utils.retry._neo4j_transient_exceptions', return_value=(ServiceUnavailable,)):
            result = neo4j_call_with_retry(mock_func, max_retries=2, initial_delay=0.01)

        assert result == "connected"
        assert mock_func.call_count == 2

    def test_neo4j_retry_permanent_failure(self):
        """Test Neo4j helper exhausts retries."""
        from neo4j.exceptions import TransientError

        mock_func = Mock(side_effect=TransientError("still transient"))

        with patch('app.utils.retry._neo4j_transient_exceptions', return_value=(TransientError,)):
            with pytest.raises(TransientError):
                neo4j_call_with_retry(mock_func, max_retries=1, initial_delay=0.01)

        assert mock_func.call_count == 2

    def test_llm_retry_on_5xx_then_success(self):
        """LLM helper retries on 5xx APIStatusError and recovers."""
        from openai import APIStatusError
        import httpx

        request = httpx.Request("POST", "http://x/v1/chat/completions")
        response = httpx.Response(500, request=request)
        err = APIStatusError("upstream 500", response=response, body=None)

        mock_func = Mock(side_effect=[err, "ok"])
        result = llm_call_with_retry(mock_func, max_retries=2, initial_delay=0.01)

        assert result == "ok"
        assert mock_func.call_count == 2

    def test_llm_retry_does_not_retry_on_4xx(self):
        """LLM helper must NOT retry on 4xx client errors (auth/bad request)."""
        from openai import APIStatusError
        import httpx

        request = httpx.Request("POST", "http://x/v1/chat/completions")
        response = httpx.Response(400, request=request)
        err = APIStatusError("bad request", response=response, body=None)

        mock_func = Mock(side_effect=err)
        with pytest.raises(APIStatusError):
            llm_call_with_retry(mock_func, max_retries=3, initial_delay=0.01)

        assert mock_func.call_count == 1

    def test_llm_retry_on_connection_error(self):
        """LLM helper retries on APIConnectionError (network drop)."""
        from openai import APIConnectionError
        import httpx

        request = httpx.Request("POST", "http://x/v1/chat/completions")
        err = APIConnectionError(request=request)

        mock_func = Mock(side_effect=[err, err, "ok"])
        result = llm_call_with_retry(mock_func, max_retries=3, initial_delay=0.01)

        assert result == "ok"
        assert mock_func.call_count == 3

    def test_llm_retry_exhausted_raises(self):
        """LLM helper re-raises after exhausting retries on persistent 5xx."""
        from openai import APIStatusError
        import httpx

        request = httpx.Request("POST", "http://x/v1/chat/completions")
        response = httpx.Response(503, request=request)
        err = APIStatusError("persistent 503", response=response, body=None)

        mock_func = Mock(side_effect=err)
        with pytest.raises(APIStatusError):
            llm_call_with_retry(mock_func, max_retries=2, initial_delay=0.01)

        assert mock_func.call_count == 3
