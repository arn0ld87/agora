"""
Tests for ModelCatalogService thread-safety (Issue #584).

Acceptance criteria:
- All read/write access to _cache happens under the lock.
- 4 threads call get_models(provider_id) simultaneously → exactly 1 upstream call.
- Cache cleared in fork-handler via reset_pools_after_fork().
"""
from __future__ import annotations

import threading
import time
from threading import Lock
from typing import List
from unittest.mock import patch

from app.services.model_catalog_service import ModelCatalogService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service() -> ModelCatalogService:
    """Return a fresh ModelCatalogService with an empty class-level cache."""
    svc = ModelCatalogService()
    # Each test gets a clean slate.
    ModelCatalogService._cache.clear()
    return svc


FAKE_MODELS = ["model-a", "model-b"]


def _patch_fetch_live(svc: ModelCatalogService, models: List[str], call_counter: list):
    """Monkey-patch _fetch_live on the instance to count upstream calls."""
    def _fake_fetch_live(provider_type, base_url, api_key):
        call_counter.append(1)
        # Simulate slight latency so threads overlap.
        time.sleep(0.02)
        return models

    svc._fetch_live = _fake_fetch_live  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Test: thread-safe lock attribute exists on class
# ---------------------------------------------------------------------------

def test_cache_lock_exists():
    """ModelCatalogService must expose a threading.Lock (or RLock) as _cache_lock."""
    assert hasattr(ModelCatalogService, "_cache_lock"), (
        "ModelCatalogService must have a class-level _cache_lock attribute"
    )
    lock = ModelCatalogService._cache_lock
    assert isinstance(lock, type(Lock())), (
        "_cache_lock must be a threading.Lock instance"
    )


# ---------------------------------------------------------------------------
# Test: concurrent callers deduplicated to exactly one upstream fetch
# ---------------------------------------------------------------------------

def test_concurrent_single_upstream_call():
    """4 concurrent threads must trigger exactly 1 upstream _fetch_live call."""
    svc = _make_service()
    call_counter: list = []
    _patch_fetch_live(svc, FAKE_MODELS, call_counter)

    # Patch LlmProviderRegistry and heuristic to avoid import side-effects.
    with (
        patch("app.services.llm_provider_registry.LlmProviderRegistry.is_model_tool_capable", return_value=True),
        patch("app.utils.llm_client.heuristic_num_ctx_for_model", return_value=4096),
    ):
        results: list = []
        errors: list = []
        barrier = threading.Barrier(4)

        def _worker():
            try:
                barrier.wait()  # All threads start simultaneously.
                entries = svc.get_models(
                    provider_id="test-provider",
                    provider_type="openai",
                    base_url="http://fake",
                    api_key=None,
                )
                results.append(entries)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

    assert not errors, f"Thread errors: {errors}"
    assert len(results) == 4, "All 4 threads must return a result"
    assert len(call_counter) == 1, (
        f"Expected exactly 1 upstream call, got {len(call_counter)}"
    )
    # All threads must see the same model list.
    for entries in results:
        model_ids = [e.id for e in entries]
        assert model_ids == FAKE_MODELS


# ---------------------------------------------------------------------------
# Test: cache cleared in fork-handler AND lock re-initialized
# ---------------------------------------------------------------------------

def test_cache_cleared_after_fork():
    """reset_pools_after_fork must clear _cache and re-initialize _cache_lock.

    The handler must NOT acquire the inherited lock — if the lock was held at
    fork time the child would deadlock.  Instead it creates a brand-new Lock()
    (standard POSIX post-fork pattern).
    """
    import threading
    from app.extensions import reset_pools_after_fork

    _make_service()
    # Seed the cache manually.
    from app.contracts.llm_routing_contract import ModelEntry
    ModelCatalogService._cache["some-provider"] = [
        ModelEntry(
            id="m1",
            name="m1",
            provider_id="some-provider",
            source="live",
            refreshed_at=time.time(),
            supports_tools=False,
            supports_json_mode=False,
            context_window=4096,
        )
    ]
    assert "some-provider" in ModelCatalogService._cache

    old_lock = ModelCatalogService._cache_lock
    reset_pools_after_fork()

    assert ModelCatalogService._cache == {}, (
        "reset_pools_after_fork must clear ModelCatalogService._cache"
    )
    # A new Lock must have been created — not the inherited one.
    assert ModelCatalogService._cache_lock is not old_lock, (
        "reset_pools_after_fork must re-initialize _cache_lock (not acquire the inherited one)"
    )
    assert isinstance(ModelCatalogService._cache_lock, type(threading.Lock())), (
        "_cache_lock must be a threading.Lock after fork-reset"
    )


# ---------------------------------------------------------------------------
# Test: TTL hit still returns cached entries (no regression)
# ---------------------------------------------------------------------------

def test_cache_hit_no_upstream_call():
    """A fresh cache entry must be returned without calling _fetch_live."""
    svc = _make_service()
    call_counter: list = []
    _patch_fetch_live(svc, FAKE_MODELS, call_counter)

    with (
        patch("app.services.llm_provider_registry.LlmProviderRegistry.is_model_tool_capable", return_value=True),
        patch("app.utils.llm_client.heuristic_num_ctx_for_model", return_value=4096),
    ):
        # First call populates cache.
        svc.get_models("p1", "openai", "http://fake", None)
        assert len(call_counter) == 1

        # Second call must hit cache.
        svc.get_models("p1", "openai", "http://fake", None)
        assert len(call_counter) == 1, "Second call must not hit upstream"
