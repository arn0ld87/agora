"""
LLM Provider Registry.
Public provider metadata only — no secrets.
"""

from typing import List, Optional
from ..contracts.llm_routing_contract import ProviderDescriptor

class LlmProviderRegistry:
    """Registry for LLM providers."""

    def __init__(self):
        # In a real app, this might be dynamic or from config.
        # For the first cut, we use a static list with auth status check.
        pass

    def get_providers(self, session_api_keys: Optional[dict] = None) -> List[ProviderDescriptor]:
        """Return static public provider metadata (no auth status computation)."""
        providers = [
            ProviderDescriptor(
                id="ollama_local",
                label="Ollama (Local)",
                type="ollama_local",
                base_url="http://localhost:11434",
                supports_models_endpoint=True,
                fallback_models=["qwen2.5:32b", "llama3.1:8b", "phi3"],
            ),
            ProviderDescriptor(
                id="openai",
                label="OpenAI",
                type="openai",
                base_url="https://api.openai.com/v1",
                api_key_ref="OPENAI_API_KEY",
                supports_models_endpoint=True,
                fallback_models=["gpt-4o", "gpt-4o-mini", "o1-preview"],
            ),
            ProviderDescriptor(
                id="google",
                label="Google Gemini",
                type="google",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key_ref="GOOGLE_API_KEY",
                supports_models_endpoint=True,
                fallback_models=["gemini-1.5-pro", "gemini-1.5-flash"],
            ),
            ProviderDescriptor(
                id="openai_compatible",
                label="OpenAI Compatible",
                type="openai_compatible",
                api_key_ref="LLM_API_KEY",
                supports_models_endpoint=True,
                fallback_models=[],
            )
        ]
        return providers
