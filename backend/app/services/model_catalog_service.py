"""
Model Catalog Service.
Live /models discovery, normalization, cache, source-badge.

HTTP-Layer: ``urllib3`` (statt ``requests``) — Hintergrund: unter
``gunicorn+gevent`` triggert die OTel ``RequestsInstrumentor`` eine
Endlos-Rekursion in ``requests.adapters.HTTPAdapter.send`` (Issue #529).
``urllib3`` umgeht den instrumentierten Codepfad vollständig und ist
sowieso die Transport-Schicht unter ``requests`` — wir verlieren also
nichts ausser dem ``requests``-Convenience-Wrapper.
"""

import json
import time
from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Mapping, Optional

import urllib3

from ..contracts import (
    PROVIDER_GITHUB_COPILOT,
    PROVIDER_GOOGLE,
    PROVIDER_OLLAMA_CLOUD,
    PROVIDER_OPENAI,
    PROVIDER_OPENAI_COMPATIBLE,
)
from ..contracts.llm_routing_contract import ModelEntry
from ..utils.logger import get_logger

logger = get_logger("agora.model_catalog")

# Modul-globaler PoolManager — Connection-Reuse über Calls hinweg.
# Wichtig: KEIN ``requests.Session`` — die wäre instrumentiert.
# retries=False, weil ``requests.get`` default 0 Retries hat und Model-Discovery
# ein blockierender UI-Call ist; 3x Retry mit Backoff würde den UI-Spinner
# 10-30 s hängen lassen, wenn ein Provider unten ist (Gemini-MEDIUM auf PR #530).
_HTTP = urllib3.PoolManager(
    timeout=urllib3.Timeout(connect=5.0, read=5.0),
    retries=False,
)


@dataclass(frozen=True)
class CatalogHttpResponse:
    """Secret-freie HTTP-Antwort fuer die gemeinsame Modell-Discovery-Schicht."""

    status_code: int | None
    payload: dict | None


def fetch_catalog_json(
    url: str, *, headers: Mapping[str, str] | None = None
) -> CatalogHttpResponse:
    """Liest JSON fuer Discovery-Adapter ueber den einzigen urllib3-Transport.

    Die Aufrufer liefern bereits die anbieterbezogenen Header; diese Funktion
    loggt weder Header noch Response-Body und verhindert damit Secret-Leaks.
    """
    request_headers = {"Accept": "application/json", **(headers or {})}
    try:
        response = _HTTP.request("GET", url, headers=request_headers)
    except urllib3.exceptions.HTTPError:
        logger.debug("HTTP error fetching model catalog from %s", url)
        return CatalogHttpResponse(status_code=None, payload=None)
    try:
        payload = json.loads(response.data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.debug("JSON parse error fetching model catalog from %s", url)
        payload = None
    return CatalogHttpResponse(status_code=response.status, payload=payload)


def _http_get_json(url: str, *, api_key: Optional[str] = None) -> Optional[dict]:
    """GET ``url`` und parse JSON. Gibt ``None`` zurück bei Non-2xx oder Parse-Fehler.

    Nutzt das Modul-PoolManager (``_HTTP``) — Tests patchen entweder diesen
    Helper direkt oder ``_HTTP.request``. Wichtig: keine Verwendung von
    ``requests`` (siehe Modul-Docstring, OTel-Rekursion #529).
    """
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = fetch_catalog_json(url, headers=headers)
    if response.status_code != 200:
        logger.debug("Non-200 status %s from %s", response.status_code, url)
        return None
    return response.payload


class ModelCatalogService:
    """Service for discovering and normalizing models from different providers."""

    _cache: Dict[str, List[ModelEntry]] = {}
    _cache_ttl = 300  # 5 minutes
    _cache_lock: Lock = Lock()

    def get_models(self, provider_id: str, provider_type: str, base_url: str, api_key: Optional[str]) -> List[ModelEntry]:
        """Fetch models from provider, with caching and fallback.

        Thread-safe: all reads and writes to ``_cache`` happen under
        ``_cache_lock`` to prevent the TOCTOU race where two concurrent
        callers both observe a stale entry and fan out two upstream requests
        (Issue #584).
        """
        now = time.time()
        from .llm_provider_registry import LlmProviderRegistry
        from ..utils.llm_client import heuristic_num_ctx_for_model

        # Acquire lock for the full check-fetch-write cycle so that concurrent
        # callers block until the first thread has populated the cache.  This
        # guarantees "exactly 1 upstream call per stale provider" (Issue #584
        # acceptance criterion).  Model-discovery is a rare, admin-triggered
        # action; the latency cost of serialisation is acceptable.
        with self._cache_lock:
            # 1. Check cache (inside lock — TOCTOU-safe).
            if provider_id in self._cache:
                entries = self._cache[provider_id]
                if entries and (now - entries[0].refreshed_at < self._cache_ttl):
                    return entries

            # 2. Try live discovery
            try:
                live_models = self._fetch_live(provider_type, base_url, api_key)
                if live_models:
                    entries = []
                    for m in live_models:
                        supports_tools = LlmProviderRegistry.is_model_tool_capable(m, provider_type)
                        entries.append(
                            ModelEntry(
                                id=m,
                                name=m,
                                provider_id=provider_id,
                                source="live",
                                refreshed_at=now,
                                supports_tools=supports_tools,
                                supports_json_mode=supports_tools,  # Heuristik: Tool-Modelle können meist auch JSON
                                context_window=heuristic_num_ctx_for_model(m),
                            )
                        )
                    self._cache[provider_id] = entries
                    return entries
            except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
                logger.warning("Failed to fetch live models from %s: %s", provider_id, exc)

            # 3. Fallback to cached (even if expired)
            if provider_id in self._cache:
                entries = self._cache[provider_id]
                for e in entries:
                    e.source = "cached"
                return entries

        # 4. Fallback to hardcoded defaults
        fallback_models = self._get_fallbacks(provider_type)

        entries = []
        for m in fallback_models:
            supports_tools = LlmProviderRegistry.is_model_tool_capable(m, provider_type)
            entries.append(
                ModelEntry(
                    id=m,
                    name=m,
                    provider_id=provider_id,
                    source="fallback",
                    refreshed_at=now,
                    supports_tools=supports_tools,
                    supports_json_mode=supports_tools,
                    context_window=heuristic_num_ctx_for_model(m),
                )
            )
        return entries

    def _fetch_live(self, provider_type: str, base_url: str, api_key: Optional[str]) -> List[str]:
        """Discovery implementation per provider type."""
        if provider_type == PROVIDER_GITHUB_COPILOT:
            # Phase 1: kein Live-Discovery — statische Liste über _get_fallbacks.
            return []

        if provider_type == PROVIDER_OLLAMA_CLOUD:
            # Ollama Cloud (ollama.com) BRAUCHT Bearer-Token am /v1/models-Endpoint.
            # Vorher fehlte der Header — Ergebnis war ein stiller 401 → leere Liste
            # (PR #528 Follow-up).
            data = _http_get_json(f"{base_url.rstrip('/')}/v1/models", api_key=api_key)
            if data:
                return [m["id"] for m in data.get("data", [])]
            # Native /api/tags als Fallback (lokales Ollama ohne /v1-Suffix).
            # removesuffix statt replace: greift nur am Ende der URL und
            # zerstört nicht zufällig "/v1" mitten in der Domain
            # (Gemini-MEDIUM auf PR #530).
            native_url = base_url.rstrip("/").removesuffix("/v1")
            data = _http_get_json(f"{native_url}/api/tags", api_key=api_key)
            if data:
                return [m["name"] for m in data.get("models", [])]
            return []

        if provider_type in (PROVIDER_OPENAI, PROVIDER_GOOGLE, PROVIDER_OPENAI_COMPATIBLE):
            # OpenAI-shape: data[].id. Erst /models, dann /v1/models als Fallback,
            # falls die base_url nicht schon /v1 enthält.
            data = _http_get_json(f"{base_url.rstrip('/')}/models", api_key=api_key)
            if data is None:
                data = _http_get_json(f"{base_url.rstrip('/')}/v1/models", api_key=api_key)
            if data:
                return [m["id"] for m in data.get("data", [])]
            return []

        return []

    def _get_fallbacks(self, provider_type: str) -> List[str]:
        # Why leer für ollama_cloud: ein hardcoded ["qwen2.5:32b", "llama3.1:8b",
        # "phi3"] erscheint als "verfügbares Modell" im UI, ist aber lokal nicht
        # zwingend installiert (User-Bericht 2026-05-16: halluzinierte Einträge
        # im Dashboard-Picker). Lieber leeres Catalog + sichtbarer Fehlerzustand
        # als Ehrlichkeits-Lüge mit nicht-existenten Modellen.
        if provider_type == PROVIDER_OLLAMA_CLOUD:
            return []
        if provider_type == PROVIDER_OPENAI:
            return ["gpt-4o", "gpt-4o-mini", "o1-preview"]
        if provider_type == PROVIDER_GOOGLE:
            return ["gemini-1.5-pro", "gemini-1.5-flash"]
        if provider_type == PROVIDER_GITHUB_COPILOT:
            from .llm_providers.github_copilot import GITHUB_COPILOT_MODELS
            return list(GITHUB_COPILOT_MODELS)
        return []
