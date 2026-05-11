"""
Secret Resolver.
Resolves API keys from environment or session without exposing them in serializable objects.
"""

import os
import threading
from typing import Optional, Dict
from ..config import Config

_RUN_API_KEYS: Dict[str, Dict[str, str]] = {}
_RUN_API_KEYS_LOCK = threading.Lock()


def register_run_api_key(run_id: str, provider_id: str, api_key: Optional[str]) -> None:
    """Keep a per-run API key in memory only.

    Runtime routes are persisted without secrets; this transient store lets the
    request that supplied the key use the same provider during async execution.
    """
    if not run_id or not provider_id or not api_key:
        return
    with _RUN_API_KEYS_LOCK:
        _RUN_API_KEYS.setdefault(run_id, {})[provider_id] = api_key


def clear_run_api_keys(run_id: str) -> None:
    """Drop transient API keys for a run."""
    with _RUN_API_KEYS_LOCK:
        _RUN_API_KEYS.pop(run_id, None)


class SecretResolver:
    """Resolves secrets for LLM providers."""

    def __init__(self, session_api_keys: Optional[Dict[str, str]] = None, run_id: Optional[str] = None):
        self._session_keys = session_api_keys or {}
        self._run_id = run_id

    def get_api_key(self, provider_id: str, provider_type: str) -> Optional[str]:
        """Resolve API key for a provider."""
        # 1. Session-only override
        if provider_id in self._session_keys:
            return self._session_keys[provider_id]

        if self._run_id:
            with _RUN_API_KEYS_LOCK:
                run_keys = _RUN_API_KEYS.get(self._run_id, {})
                if provider_id in run_keys:
                    return run_keys[provider_id]

        # 2. Provider-specific environment variables
        if provider_type == "openai":
            return os.environ.get("OPENAI_API_KEY") or Config.LLM_API_KEY
        if provider_type == "google":
            return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

        # 3. Global fallback
        return Config.LLM_API_KEY

    def sanitize_url(self, url: Optional[str]) -> Optional[str]:
        """Remove secrets from URL (no userinfo, no query string)."""
        if not url:
            return url
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        # Remove user:pass and query/fragment
        sanitized = parsed._replace(netloc=parsed.hostname + (f":{parsed.port}" if parsed.port else ""), query="", fragment="")
        return urlunparse(sanitized)
