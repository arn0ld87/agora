"""Kanonische, oeffentliche Provider-Metadaten ohne Secrets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from ..contracts import (
    PROVIDER_ANTHROPIC,
    PROVIDER_BEDROCK,
    PROVIDER_CODEX_CLI,
    PROVIDER_GITHUB_COPILOT,
    PROVIDER_GOOGLE,
    PROVIDER_MINIMAX,
    PROVIDER_OLLAMA,
    PROVIDER_OLLAMA_CLOUD,
    PROVIDER_OPENCODE_GO,
    PROVIDER_OPENAI,
    PROVIDER_OPENAI_COMPATIBLE,
)
from ..contracts.llm_routing_contract import ProviderDescriptor
from ..contracts.provider_types import ProviderType


def _copilot_models() -> tuple[str, ...]:
    # Lazy import keeps the historical import boundary cycle-free.
    from .llm_providers.github_copilot import GITHUB_COPILOT_MODELS

    return GITHUB_COPILOT_MODELS


@dataclass(frozen=True)
class ProviderConnectionDefinition:
    """Die einzige Matrix fuer Lifecycle-, Discovery- und Legacy-Metadaten."""

    provider_kind: ProviderType
    display_name: str
    transport: Literal["http", "local", "cli"]
    auth_mode: Literal["none", "api_key", "session"]
    default_base_url: str | None
    adapter_kind: str
    api_key_ref: str | None
    supports_tools: bool = False
    fallback_models: tuple[str, ...] = ()


_CONNECTION_DEFINITIONS: tuple[ProviderConnectionDefinition, ...] = (
    ProviderConnectionDefinition(
        PROVIDER_OPENAI, "OpenAI", "http", "api_key", "https://api.openai.com/v1",
        "openai", "OPENAI_API_KEY", True, ("gpt-4o", "gpt-4o-mini", "o1-preview"),
    ),
    ProviderConnectionDefinition(
        PROVIDER_ANTHROPIC, "Anthropic", "http", "api_key", "https://api.anthropic.com",
        "anthropic", "ANTHROPIC_API_KEY", True,
    ),
    ProviderConnectionDefinition(
        PROVIDER_GOOGLE, "Google Gemini", "http", "api_key",
        "https://generativelanguage.googleapis.com/v1beta/openai", "google",
        "GOOGLE_API_KEY", True, ("gemini-1.5-pro", "gemini-1.5-flash"),
    ),
    ProviderConnectionDefinition(
        PROVIDER_MINIMAX, "MiniMax", "http", "api_key", "https://api.minimax.io/v1",
        "minimax", "MINIMAX_API_KEY", True,
    ),
    # Issue #1072: Die Base-URL bleibt bewusst an der Server-Wurzel, OHNE
    # ``/v1``. Zwei Konsumenten teilen sie sich mit unvereinbaren Erwartungen:
    # die Modell-Discovery haengt ``/api/tags`` direkt an (``provider_
    # connections/adapters.py``), der OpenAI-SDK-Client dagegen braucht
    # ``/v1/chat/completions``. Ein ``/v1`` im Default wuerde die Discovery zu
    # ``/v1/api/tags`` verbiegen — 404. Die Kanonisierung fuer den Chat-Pfad
    # passiert deshalb erst beim Client-Aufbau
    # (``llm/providers/registry.py::openai_compat_base_url``).
    ProviderConnectionDefinition(
        PROVIDER_OLLAMA_CLOUD, "Ollama (Cloud)", "http", "api_key", "https://ollama.com",
        "ollama_cloud", "OLLAMA_API_KEY",
    ),
    ProviderConnectionDefinition(
        PROVIDER_OPENAI_COMPATIBLE, "OpenAI Compatible", "http", "api_key", None,
        "openai_compatible", "LLM_API_KEY", True,
    ),
    ProviderConnectionDefinition(
        PROVIDER_OLLAMA, "Ollama (lokal)", "local", "none", "http://localhost:11434",
        "ollama", None,
    ),
    # OpenCode Go publishes a model URL but no documented raw request-header
    # contract. See provider_connections.adapters: intentionally unsupported.
    ProviderConnectionDefinition(
        PROVIDER_OPENCODE_GO, "OpenCode Go", "http", "api_key",
        "https://opencode.ai/zen/go/v1", "unsupported", "OPENCODE_GO_API_KEY",
    ),
    ProviderConnectionDefinition(
        PROVIDER_GITHUB_COPILOT, "GitHub Copilot", "http", "api_key",
        "https://api.githubcopilot.com", "unsupported", "GH_AUTH_TOKEN", True,
        fallback_models=_copilot_models(),
    ),
    # Issue #1282 — Amazon Bedrock via OpenAI-kompatibler mantle-Pfad
    # (https://docs.aws.amazon.com/bedrock/latest/userguide/inference-chat-
    # completions-mantle.html). Auth via Bedrock-Bearer-API-Key
    # (AWS_BEARER_TOKEN_BEDROCK), kein boto3/SigV4.
    #
    # Default-Region eu-central-1 (Datenresidenz). ``fallback_models`` unten
    # ist an diese Region gekoppelt und NICHT frei waehlbar — zwei Gruende,
    # beide am 2026-08-13 gegen den Live-Endpunkt gemessen:
    #
    # 1. Der mantle-Katalog ist regional verschieden. us-east-1 fuehrt 55
    #    Modelle, eu-central-1 nur 33. Wer die Region wechselt, ohne die
    #    Modellwahl mitzuziehen, bekommt ``404 The model '<id>' does not
    #    exist``.
    # 2. Katalog-Praesenz heisst NICHT Chat-Faehigkeit. Der mantle-Pfad
    #    bedient nur einen Teil seiner eigenen Modelle ueber
    #    ``/v1/chat/completions``; in us-east-1 sind es 38 von 55. Die
    #    gesamte ``anthropic.*``-Familie und alle ``openai.gpt-5.x`` stehen
    #    zwar im Katalog, antworten aber mit ``400 does not support the
    #    '/v1/chat/completions' API`` — und ebenso auf ``/v1/responses``.
    #    Diese Modelle sind ueber den OpenAI-kompatiblen Pfad grundsaetzlich
    #    nicht erreichbar; sie brauchen die native Converse/InvokeModel-API
    #    mit SigV4 (bewusst ausserhalb dieses Slice, siehe Folge-Issue).
    #    ``GET /v1/models`` gibt kein Capability-Feld her, das man offline
    #    auswerten koennte — deshalb probt der netzgebundene Test
    #    ``tests/llm/test_bedrock_model_catalog.py`` jedes Preset mit einem
    #    echten Chat-Call statt nur die Katalog-Mitgliedschaft zu pruefen.
    #
    # Die Region ist Teil der Host-Subdomain. Sie im Connection-UI zu
    # aendern reicht derzeit NICHT: der Wert landet zwar in
    # ``ProviderConnection.base_url``, aber ``api/llm_active.py::
    # put_active_config`` schreibt beim Aktivieren den Registry-Default hier
    # aus der Definition in die Active-Config — und genau die steuert die
    # Laufzeit (``llm/client.py``). Wer die Region wirklich wechseln will,
    # aendert bis zur Behebung von #1289 diesen Default. Der Trugschluss hat
    # die Bedrock-Diagnose mehrere Runden gekostet.
    #
    # ``default_base_url`` enthaelt bereits
    # ``/v1``: die Discovery haengt ``/models`` an (→ ``…/v1/models``), und der
    # Chat-Client spricht ``…/v1/chat/completions``. Damit unterscheidet sich
    # Bedrock von Ollama (dessen Default bewusst OHNE ``/v1`` steht, weil
    # ``/api/tags`` an der Wurzel haengt) und gleicht dem OpenAI-Default.
    # Issue #1405: kein HTTP-Endpunkt, kein API-Key — spricht den lokal
    # eingeloggten `codex`-CLI-Prozess (ChatGPT-Abo) per Subprozess an.
    # ``auth_mode="session"`` heisst: die Authentifizierung lebt in der
    # lokalen CLI-Login-Session (``codex login``), nicht in einem hier
    # verwalteten Secret. ``transport="cli"`` weicht bewusst von "local"
    # ab — "local" heisst im Rest dieser Matrix "lokaler HTTP-Server"
    # (Ollama), nicht "kein HTTP". Siehe ``llm/providers/codex_cli.py``.
    ProviderConnectionDefinition(
        PROVIDER_CODEX_CLI, "Codex CLI (ChatGPT-Abo)", "cli", "session",
        None, "codex_cli", None,
    ),
    ProviderConnectionDefinition(
        PROVIDER_BEDROCK, "Amazon Bedrock", "http", "api_key",
        "https://bedrock-mantle.eu-central-1.api.aws/v1",
        "bedrock", "AWS_BEARER_TOKEN_BEDROCK", True,
        fallback_models=(
            "openai.gpt-oss-120b",
            "qwen.qwen3-235b-a22b-2507",
            "minimax.minimax-m2.5",
            "mistral.devstral-2-123b",
            "nvidia.nemotron-super-3-120b",
            "zai.glm-4.7-flash",
        ),
    ),
)


class LlmProviderRegistry:
    """Registry fuer statische, secret-freie Provider-Metadaten."""

    @staticmethod
    def connection_definitions() -> tuple[ProviderConnectionDefinition, ...]:
        return _CONNECTION_DEFINITIONS

    @staticmethod
    def connection_definition(provider_kind: str) -> ProviderConnectionDefinition | None:
        return next(
            (definition for definition in _CONNECTION_DEFINITIONS if definition.provider_kind == provider_kind),
            None,
        )

    def get_providers(
        self, session_api_keys: Optional[dict] = None
    ) -> list[ProviderDescriptor]:
        """Liefert Legacy-Deskriptoren aus derselben kanonischen Matrix."""
        del session_api_keys
        return [
            ProviderDescriptor(
                id=definition.provider_kind,
                label=definition.display_name,
                type=definition.provider_kind,
                base_url=definition.default_base_url,
                api_key_ref=definition.api_key_ref,
                supports_models_endpoint=definition.adapter_kind != "unsupported",
                supports_tools=definition.supports_tools,
                fallback_models=list(definition.fallback_models),
            )
            for definition in _CONNECTION_DEFINITIONS
        ]

    @staticmethod
    def is_model_tool_capable(model_id: str, provider_type: str) -> bool:
        """Heuristik fuer OpenAI-kompatibles Tool-Calling."""
        if not model_id:
            return False
        mid = model_id.lower()
        if "ministral" in mid:
            return False
        if provider_type in ("openai", "google", "anthropic", "github_copilot", "bedrock"):
            return True
        tool_capable_families = (
            "gpt-4", "gpt-3.5", "o1-", "o3-", "gemini-", "llama-3.1",
            "llama-3.2", "llama-3.3", "llama3.1", "llama3.2", "llama3.3",
            "qwen2.5", "qwen3", "deepseek-v3", "deepseek-v4", "deepseek-r1", "claude-3",
        )
        return any(family in mid for family in tool_capable_families)
