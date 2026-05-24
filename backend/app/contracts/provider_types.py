from typing import Literal

PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI = "openai"
PROVIDER_GOOGLE = "google"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_CUSTOM = "custom"
PROVIDER_OLLAMA_CLOUD = "ollama_cloud"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
PROVIDER_GITHUB_COPILOT = "github_copilot"
PROVIDER_CLOUD = "cloud"
PROVIDER_UNKNOWN = "unknown"

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
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    PROVIDER_GOOGLE,
    PROVIDER_ANTHROPIC,
    PROVIDER_CUSTOM,
    PROVIDER_OLLAMA_CLOUD,
    PROVIDER_OPENAI_COMPATIBLE,
    PROVIDER_GITHUB_COPILOT,
    PROVIDER_CLOUD,
    PROVIDER_UNKNOWN,
)
