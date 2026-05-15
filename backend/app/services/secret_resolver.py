"""
Secret Resolver.
Resolves API keys from session, persistent store, or environment without
exposing them in serializable objects.

Resolution order:
  1. Session-only override (höchste Priorität, für ad-hoc Tests)
  2. Persistenter Fernet-encrypted Store (vom Frontend befüllt)
  3. Provider-spezifische Environment-Variablen
  4. Globaler Fallback (Config.LLM_API_KEY)
"""

import logging
import os
from typing import Optional, Dict

from ..config import Config
from .llm_provider_secrets_store import get_llm_provider_secrets_store

logger = logging.getLogger("agora.secret_resolver")


class SecretResolver:
    """Resolves secrets for LLM providers."""

    def __init__(self, session_api_keys: Optional[Dict[str, str]] = None):
        self._session_keys = session_api_keys or {}

    def get_api_key(self, provider_id: str, provider_type: str) -> Optional[str]:
        """Resolve API key for a provider."""
        # 1. Session-only override
        if provider_id in self._session_keys:
            return self._session_keys[provider_id]

        # 2. Persistenter Store (Fernet-encrypted, vom Frontend befüllt)
        try:
            stored = get_llm_provider_secrets_store().get_plaintext(provider_id)
            if stored:
                return stored
        except RuntimeError as exc:
            # AGORA_SECRET_KEY fehlt o. ä. — auf env-Fallback weiterleiten.
            # Hier explizit ohne Key-Werte loggen.
            logger.warning("Secret-Store-Zugriff fehlgeschlagen, fallback auf env: %s", exc)

        # 3. Provider-spezifische Environment-Variablen
        if provider_type == "openai":
            return os.environ.get("OPENAI_API_KEY") or Config.LLM_API_KEY
        if provider_type == "google":
            return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if provider_type == "github_copilot":
            # GitHub Copilot: Token-Auflösung über separates Modul (Slice B).
            try:
                from .llm_providers.github_copilot import resolve_copilot_token
            except ImportError:
                return None
            return resolve_copilot_token()

        # 4. Global fallback
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
