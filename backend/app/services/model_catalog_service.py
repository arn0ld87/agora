"""
Model Catalog Service.
Live /models discovery, normalization, cache, source-badge.
"""

import time
import requests
from typing import List, Optional, Dict, Any, Literal
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

from typing import Literal

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
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if provider_type == "ollama_local":
            # Ollama has /api/tags (native) and /v1/models (OpenAI compatible)
            models = set()

            # 1. Try OpenAI compatible /v1/models
            try:
                v1_url = f"{base_url.rstrip('/')}/v1/models"
                resp = requests.get(v1_url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    for m in data.get("data", []):
                        models.add(m["id"])
            except Exception as e:
                logger.debug("Ollama /v1/models failed: %s", e)

            # 2. Try native Ollama /api/tags
            try:
                native_url = base_url.replace("/v1", "").rstrip("/") + "/api/tags"
                resp = requests.get(native_url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    for m in data.get("models", []):
                        models.add(m["name"])
            except Exception as e:
                logger.debug("Ollama /api/tags failed: %s", e)

            return sorted(list(models))

        elif provider_type in ("openai", "google", "openai_compatible"):
            # Normalize OpenAI/Gemini/OpenAI-compatible data[] model responses
            endpoints = [
                f"{base_url.rstrip('/')}/models",
                f"{base_url.rstrip('/')}/v1/models"
            ]

            for url in endpoints:
                try:
                    resp = requests.get(url, headers=headers, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        # Both OpenAI and Gemini-OpenAI-shim use "data" list
                        if "data" in data and isinstance(data["data"], list):
                            return [m["id"] for m in data["data"] if "id" in m]
                except Exception as e:
                    logger.debug("Discovery failed for %s: %s", url, e)

        return []

    def _get_fallbacks(self, provider_type: str) -> List[str]:
        if provider_type == "ollama_local":
            return ["qwen2.5:32b", "llama3.1:8b", "phi3"]
        if provider_type == "openai":
            return ["gpt-4o", "gpt-4o-mini", "o1-preview"]
        if provider_type == "google":
            return ["gemini-1.5-pro", "gemini-1.5-flash"]
        return []
