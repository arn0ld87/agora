"""
Secret Resolver.
Resolves API keys from environment or session without exposing them in serializable objects.
"""

import os
from typing import Optional, Dict
from ..config import Config

class SecretResolver:
    """Resolves secrets for LLM providers."""

    def __init__(self, session_api_keys: Optional[Dict[str, str]] = None):
        self._session_keys = session_api_keys or {}

    def get_api_key(self, provider_id: str, provider_type: str) -> Optional[str]:
        """Resolve API key for a provider."""
        # 1. Session-only override
        if provider_id in self._session_keys:
            return self._session_keys[provider_id]

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
