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
from typing import Optional, Dict, Any

from ..config import Config
from .llm_provider_secrets_store import get_llm_provider_secrets_store

logger = logging.getLogger("agora.secret_resolver")


class SecretResolver:
    """Resolves secrets for LLM providers."""

    def __init__(self, session_api_keys: Optional[Dict[str, str]] = None):
        self._session_keys = session_api_keys or {}

    def get_base_url(self, provider_id: str, provider_type: str, provider_options: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Resolve the real base URL for a provider (including credentials)."""
        # 0. Try explicit provider_options (highest precedence)
        if provider_options and provider_options.get("base_url"):
            return provider_options["base_url"]

        # 1. Try ProviderRegistry
        try:
            from .llm_provider_registry import LlmProviderRegistry
            registry = LlmProviderRegistry()
            descriptor = next((p for p in registry.get_providers() if p.id == provider_id), None)
            if descriptor and descriptor.base_url:
                return descriptor.base_url
        except Exception:
            pass

        # 2. Try Workspace-Routing-Store (contains potential secrets, but is protected)
        try:
            from .workspace_routing_store import get_workspace_routing_store
            ws_store = get_workspace_routing_store()
            defaults = ws_store.load()

            # Check stage overrides first (more specific)
            for route in defaults.stage_overrides.values():
                if route.provider_id == provider_id:
                    url = route.provider_options.get("base_url")
                    if url:
                        return url

            # Check global default
            if defaults.global_default.provider_id == provider_id:
                url = defaults.global_default.provider_options.get("base_url")
                if url:
                    return url
        except Exception:
            pass

        # 3. Provider-specific Environment fallbacks
        if provider_type == "openai":
            return os.environ.get("OPENAI_BASE_URL") or os.environ.get("LLM_BASE_URL") or Config.LLM_BASE_URL
        if provider_type == "google":
            return "https://generativelanguage.googleapis.com/v1beta/openai/"
        if provider_type == "github_copilot":
            return "https://api.githubcopilot.com"
        if provider_type == "ollama_local":
            return os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"

        # 4. Global fallback
        return os.environ.get("LLM_BASE_URL") or Config.LLM_BASE_URL

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
            return os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY") or Config.LLM_API_KEY
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
        return os.environ.get("LLM_API_KEY") or Config.LLM_API_KEY

    def sanitize_url(self, url: Optional[str]) -> Optional[str]:
        """Remove secrets from URL (no userinfo, no query string)."""
        if not url:
            return url
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        # Remove user:pass and query/fragment
        sanitized = parsed._replace(netloc=parsed.hostname + (f":{parsed.port}" if parsed.port else ""), query="", fragment="")
        return urlunparse(sanitized)
