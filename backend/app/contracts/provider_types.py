from typing import Literal

PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI = "openai"
PROVIDER_GOOGLE = "google"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_CUSTOM = "custom"
PROVIDER_OLLAMA_CLOUD = "ollama_cloud"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
PROVIDER_GITHUB_COPILOT = "github_copilot"

# Legacy alias
LEGACY_GEMINI = "gemini"

ProviderType = Literal[
    "ollama",
    "openai",
    "google",
    "anthropic",
    "custom",
    "ollama_cloud",
    "openai_compatible",
    "github_copilot",
    "cloud",
    "unknown",
]

ALL_PROVIDER_TYPES: tuple[ProviderType, ...] = (
    "ollama",
    "openai",
    "google",
    "anthropic",
    "custom",
    "ollama_cloud",
    "openai_compatible",
    "github_copilot",
)
