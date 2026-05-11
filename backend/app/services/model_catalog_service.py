"""
Model Catalog Service.
Live /models discovery, normalization, cache, source-badge.
"""

import time
import requests
from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, ConfigDict
from ..utils.logger import get_logger

logger = get_logger("agora.model_catalog")

class ModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    provider_id: str
    source: Literal["live", "cached", "fallback", "custom"]
    refreshed_at: float

class ModelCatalogService:
    """Service for discovering and normalizing models from different providers."""

    _cache: Dict[str, List[ModelEntry]] = {}
    _cache_ttl = 300 # 5 minutes

    def get_models(self, provider_id: str, provider_type: str, base_url: str, api_key: Optional[str]) -> List[ModelEntry]:
        """Fetch models from provider, with caching and fallback."""
        now = time.time()

        # 1. Check cache
        if provider_id in self._cache:
            entries = self._cache[provider_id]
            if entries and (now - entries[0].refreshed_at < self._cache_ttl):
                return entries

        # 2. Try live discovery
        try:
            live_models = self._fetch_live(provider_type, base_url, api_key)
            if live_models:
                entries = [
                    ModelEntry(
                        id=m,
                        name=m,
                        provider_id=provider_id,
                        source="live",
                        refreshed_at=now
                    ) for m in live_models
                ]
                self._cache[provider_id] = entries
                return entries
        except Exception as exc:
            logger.warning("Failed to fetch live models from %s: %s", provider_id, exc)

        # 3. Fallback to cached (even if expired)
        if provider_id in self._cache:
            entries = self._cache[provider_id]
            # Update source to cached
            for e in entries:
                e.source = "cached"
            return entries

        # 4. Fallback to hardcoded defaults
        fallback_models = self._get_fallbacks(provider_type)
        return [
            ModelEntry(
                id=m,
                name=m,
                provider_id=provider_id,
                source="fallback",
                refreshed_at=now
            ) for m in fallback_models
        ]

    def _fetch_live(self, provider_type: str, base_url: str, api_key: Optional[str]) -> List[str]:
        """Discovery implementation per provider type."""
        if provider_type == "ollama_local":
            # Ollama has /api/tags (native) and /v1/models (OpenAI compatible)
            # We prefer /api/tags for full metadata if available
            try:
                # Try OpenAI compatible first as it's the standard Agora uses
                resp = requests.get(f"{base_url.rstrip('/')}/v1/models", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    return [m["id"] for m in data.get("data", [])]
            except Exception as exc:
                logger.debug("OpenAI-compatible /v1/models discovery failed: %s", exc)

            # Try native Ollama /api/tags as fallback
            # We need to strip /v1 if it was added to base_url for OpenAI compat
            native_url = base_url.replace("/v1", "").rstrip("/")
            resp = requests.get(f"{native_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]

        elif provider_type in ("openai", "google", "openai_compatible"):
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            resp = requests.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=5)
            if resp.status_code != 200:
                 # Try /v1/models if /models failed
                 resp = requests.get(f"{base_url.rstrip('/')}/v1/models", headers=headers, timeout=5)

            if resp.status_code == 200:
                data = resp.json()
                # OpenAI and Google (OpenAI-shim) both use data[]
                return [m["id"] for m in data.get("data", [])]

        return []

    def _get_fallbacks(self, provider_type: str) -> List[str]:
        if provider_type == "ollama_local":
            return ["qwen2.5:32b", "llama3.1:8b", "phi3"]
        if provider_type == "openai":
            return ["gpt-4o", "gpt-4o-mini", "o1-preview"]
        if provider_type == "google":
            return ["gemini-1.5-pro", "gemini-1.5-flash"]
        return []
