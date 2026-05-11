"""
LLM Provider Registry.
Public provider metadata only — no secrets.
"""

from typing import List, Optional
from ..contracts.llm_routing_contract import ProviderDescriptor
from ..config import Config

class LlmProviderRegistry:
    """Registry for LLM providers."""

    def __init__(self):
        # In a real app, this might be dynamic or from config.
        # For the first cut, we use a static list with auth status check.
        pass

    def get_providers(self, session_api_keys: Optional[dict] = None) -> List[ProviderDescriptor]:
        """Return list of available providers and their auth status."""
        providers = [
            ProviderDescriptor(
                id="ollama_local",
                name="Ollama (Local)",
                type="ollama_local",
                default_base_url="http://localhost:11434",
                auth_status="configured"  # Ollama local usually needs no key
            ),
            ProviderDescriptor(
                id="openai",
                name="OpenAI",
                type="openai",
                default_base_url="https://api.openai.com/v1",
                auth_status=self._check_auth("openai", session_api_keys)
            ),
            ProviderDescriptor(
                id="google",
                name="Google Gemini",
                type="google",
                default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                auth_status=self._check_auth("google", session_api_keys)
            ),
            ProviderDescriptor(
                id="openai_compatible",
                name="OpenAI Compatible",
                type="openai_compatible",
                auth_status=self._check_auth("openai_compatible", session_api_keys)
            )
        ]
        return providers

    def _check_auth(self, provider_id: str, session_api_keys: Optional[dict] = None) -> str:
        """Heuristic check for auth status."""
        # 1. Check session
        if session_api_keys and session_api_keys.get(provider_id):
            return "configured"

        # 2. Check environment (via Config)
        # Mapping provider_id to Config fields
        if provider_id == "openai":
            if Config.LLM_API_KEY and "openai" in (Config.LLM_BASE_URL or "").lower():
                 return "configured"
            if os.environ.get("OPENAI_API_KEY"):
                 return "configured"

        if provider_id == "google":
            if os.environ.get("GOOGLE_API_KEY"):
                return "configured"

        # Fallback
        return "missing"

import os
