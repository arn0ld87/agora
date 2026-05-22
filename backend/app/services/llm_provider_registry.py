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
                id="ollama_cloud",
                label="Ollama (Cloud)",
                type="ollama_cloud",
                # OpenAI-kompatibler Ollama-Cloud-Endpoint. Auth via Bearer-Token
                # (``OLLAMA_API_KEY``). Doku: https://docs.ollama.com/cloud
                base_url="https://ollama.com/v1",
                api_key_ref="OLLAMA_API_KEY",
                supports_models_endpoint=True,
                fallback_models=[
                    "qwen3-coder-next:cloud",
                    "deepseek-v4-flash:cloud",
                    "gpt-oss-128:cloud",
                    "kimi-k2.6:cloud",
                ],
            ),
            ProviderDescriptor(
                id="openai",
                label="OpenAI",
                type="openai",
                base_url="https://api.openai.com/v1",
                api_key_ref="OPENAI_API_KEY",
                supports_models_endpoint=True,
                supports_tools=True,
                fallback_models=["gpt-4o", "gpt-4o-mini", "o1-preview"],
            ),
            ProviderDescriptor(
                id="google",
                label="Google Gemini",
                type="google",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key_ref="GOOGLE_API_KEY",
                supports_models_endpoint=True,
                supports_tools=True,
                fallback_models=["gemini-1.5-pro", "gemini-1.5-flash"],
            ),
            ProviderDescriptor(
                id="openai_compatible",
                label="OpenAI Compatible",
                type="openai_compatible",
                api_key_ref="LLM_API_KEY",
                supports_models_endpoint=True,
                fallback_models=[],
            ),
            ProviderDescriptor(
                id="github_copilot",
                label="GitHub Copilot",
                type="github_copilot",
                base_url="https://api.githubcopilot.com",
                api_key_ref="GH_AUTH_TOKEN",
                supports_models_endpoint=False,
                supports_tools=True,
                fallback_models=list(_copilot_models()),
            ),
        ]
        return providers

    @staticmethod
    def is_model_tool_capable(model_id: str, provider_type: str) -> bool:
        """Heuristic check if a model supports OpenAI-compatible tool calling."""
        if not model_id:
            return False

        mid = model_id.lower()

        # Explicit gate for known broken models (Issue #557)
        if "ministral" in mid:
            return False

        # Natively capable providers (where we trust almost any modern model)
        if provider_type in ("openai", "google", "github_copilot"):
            return True

        # Whitelist for Ollama/OpenAI-compatible model families
        tool_capable_families = (
            "gpt-4",
            "gpt-3.5",
            "o1-",
            "o3-",
            "gemini-",
            "llama-3.1",
            "llama-3.2",
            "llama-3.3",
            "llama3.1",
            "llama3.2",
            "llama3.3",
            "qwen2.5",
            "qwen3",
            "deepseek-v3",
            "deepseek-v4",
            "deepseek-r1",
            "claude-3",
        )
        return any(f in mid for f in tool_capable_families)


def _copilot_models() -> tuple[str, ...]:
    # Lazy-Import vermeidet Zirkularität wenn das Submodul später wächst.
    from .llm_providers.github_copilot import GITHUB_COPILOT_MODELS
    return GITHUB_COPILOT_MODELS
