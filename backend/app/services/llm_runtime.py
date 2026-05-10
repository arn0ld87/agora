"""Per-request LLM runtime settings.

The UI may pass provider credentials for one run. API keys are intentionally
kept out of run metadata and simulation artifacts; only non-secret provider
data such as the OpenAI-compatible base URL may be persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import urlparse


PROVIDER_DEFAULT_BASE_URLS = {
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openai": "https://api.openai.com/v1",
}

_PROVIDER_ALIASES = {
    "default": "default",
    "server": "default",
    "google": "google",
    "gemini": "google",
    "openai": "openai",
    "custom": "custom_openai",
    "custom_openai": "custom_openai",
    "openai_compatible": "custom_openai",
}


@dataclass(frozen=True)
class RuntimeLlmConfig:
    """Validated runtime provider override for one request."""

    provider: str = "default"
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return self.provider != "default"

    def redacted_metadata(self) -> dict[str, Any]:
        if not self.enabled:
            return {}
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key_set": bool(self.api_key),
        }

    def client_kwargs(self, *, model: Optional[str] = None) -> dict[str, Optional[str]]:
        if not self.enabled:
            return {"model": model}
        return {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model": model,
        }

    def subprocess_env(self, *, model: Optional[str] = None) -> dict[str, str]:
        if not self.enabled:
            return {}
        env = {
            "LLM_API_KEY": self.api_key or "",
            "OPENAI_API_KEY": self.api_key or "",
        }
        if self.base_url:
            env["LLM_BASE_URL"] = self.base_url
            env["OPENAI_BASE_URL"] = self.base_url
            env["OPENAI_API_BASE"] = self.base_url
            env["OPENAI_API_BASE_URL"] = self.base_url
        if model:
            env["LLM_MODEL_NAME"] = model
        return env


def parse_runtime_llm_config(data: Mapping[str, Any]) -> RuntimeLlmConfig:
    raw = data.get("llm_provider") or data.get("llm_runtime") or None
    if not raw:
        return RuntimeLlmConfig()
    if not isinstance(raw, Mapping):
        raise ValueError("llm_provider must be an object")

    provider_raw = str(raw.get("provider") or "default").strip().lower()
    provider = _PROVIDER_ALIASES.get(provider_raw)
    if provider is None:
        raise ValueError(
            "llm_provider.provider must be one of: default, google, openai, custom_openai"
        )
    if provider == "default":
        return RuntimeLlmConfig()

    api_key = str(raw.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("llm_provider.api_key is required for non-default providers")

    base_url = str(raw.get("base_url") or "").strip()
    if not base_url:
        base_url = PROVIDER_DEFAULT_BASE_URLS.get(provider, "")
    if not base_url:
        raise ValueError("llm_provider.base_url is required for custom_openai")

    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("llm_provider.base_url must be an absolute http(s) URL")

    return RuntimeLlmConfig(provider=provider, api_key=api_key, base_url=base_url)
