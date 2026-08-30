from typing import Literal

PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI = "openai"
PROVIDER_GOOGLE = "google"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_CUSTOM = "custom"
PROVIDER_OLLAMA_CLOUD = "ollama_cloud"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
PROVIDER_MINIMAX = "minimax"
PROVIDER_OPENCODE_GO = "opencode_go"
PROVIDER_GITHUB_COPILOT = "github_copilot"
PROVIDER_BEDROCK = "bedrock"
PROVIDER_CLOUD = "cloud"
PROVIDER_UNKNOWN = "unknown"
# Issue #1405: Subprozess-Bridge zur lokal eingeloggten Codex-CLI (ChatGPT-
# Abo). Anders als OpenCode Go (rein HTTP, nur ohne dokumentierten Header-
# Vertrag) spricht dieser Provider gar kein HTTP — ``transport="cli"`` in
# ``ProviderConnectionDefinition``/``ProviderTransport``. Deshalb bewusst
# NICHT vom ``_reject_unsupported_connection_provider``-Guard in
# ``ai_provider_contract.py`` erfasst.
PROVIDER_CODEX_CLI = "codex_cli"

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
    "minimax",
    "opencode_go",
    "github_copilot",
    "bedrock",
    "cloud",
    "codex_cli",
    "unknown",
]

# Connection lifecycle ist HTTP/local/cli. OpenCode Go bleibt ausgeschlossen
# (kein dokumentierter Request-Vertrag). ``codex_cli`` ist der erste
# ``transport="cli"``-Provider (#1405).
ProviderConnectionKind = Literal[
    "ollama",
    "openai",
    "google",
    "anthropic",
    "custom",
    "ollama_cloud",
    "openai_compatible",
    "minimax",
    "github_copilot",
    "bedrock",
    "cloud",
    "codex_cli",
    "unknown",
]

# Herkunft einer vom UI geschickten (Connection, Modell)-Wahl.
#
# Liegt hier und nicht in ``ai_provider_contract`` (Issue #901): seit
# ``StageLLMRoute`` die Herkunft mitführt, brauchen beide Contract-Module das
# Literal. ``ai_provider_contract`` importiert bereits aus
# ``llm_routing_contract`` — der Gegenimport wäre ein Zyklus.
#
# Bewusst getrennt von ``RouteSource`` in ``ai_provider_contract``: dieses
# Vokabular beschreibt, was das UI ausgewählt hat, jenes den aufgelösten
# Routing-Zustand. Die Abbildung steht in ``_AI_MODEL_REF_SOURCE_TO_ROUTE``.
AiModelRefSource = Literal[
    "stage-override",
    "run-override",
    "project-default",
    "workspace-default",
    "explicit",
    "fallback",
]

# NOTE: typed as tuple[str, ...] (not tuple[ProviderType, ...]) because
# the constants above are inferred as `str`, not as specific Literal[...].
# Promoting each to `Final[Literal[...]]` would be cleaner but is a
# follow-up cleanup — this keeps mypy quiet without runtime impact.
ALL_PROVIDER_TYPES: tuple[str, ...] = (
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    PROVIDER_GOOGLE,
    PROVIDER_ANTHROPIC,
    PROVIDER_CUSTOM,
    PROVIDER_OLLAMA_CLOUD,
    PROVIDER_OPENAI_COMPATIBLE,
    PROVIDER_MINIMAX,
    PROVIDER_OPENCODE_GO,
    PROVIDER_GITHUB_COPILOT,
    PROVIDER_BEDROCK,
    PROVIDER_CLOUD,
    PROVIDER_CODEX_CLI,
    PROVIDER_UNKNOWN,
)
