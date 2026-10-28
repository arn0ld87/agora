"""CAMEL model parameter resolution and provider detection helpers."""

from typing import Any


def detect_oasis_platform(model: str, base_url: str):
    """Map model-name + base-url to the correct CAMEL ModelPlatformType."""
    from camel.types import ModelPlatformType  # type: ignore[import]
    from app.llm.providers.registry import detect_provider as _detect

    detected = _detect(base_url, model, mode="oasis")
    if detected == "google":
        return ModelPlatformType.GEMINI
    if detected == "ollama":
        return ModelPlatformType.OLLAMA
    return ModelPlatformType.OPENAI


def _is_ollama_route(model: str, base_url: str) -> bool:
    """True wenn das Modell über Ollama (lokal oder Cloud) läuft."""
    from app.llm.providers.registry import detect_provider

    return detect_provider(base_url, model, mode="oasis") == "ollama"


def resolve_camel_ollama_url(base_url: str | None) -> str | None:
    """Base-URL fuer CAMELs OllamaModel — mit erzwungenem /v1."""
    from app.llm.providers.registry import ensure_v1_suffix

    return ensure_v1_suffix(base_url)


def uses_max_completion_tokens(model: str) -> bool:
    """True wenn das Modell max_completion_tokens statt max_tokens verlangt."""
    from app.llm import model_capabilities

    return model_capabilities.uses_max_completion_tokens_hyphen_boundary(model)


def supports_reasoning_effort_none(model: str) -> bool:
    """True wenn das Modell reasoning_effort: 'none' akzeptiert."""
    from app.llm import model_capabilities

    return model_capabilities.supports_reasoning_effort_none(model)


def _is_openrouter_route(model: str, base_url: str | None) -> bool:
    """True wenn die Route laut zentraler Detection auf OpenRouter zeigt."""
    from app.llm.providers.registry import detect_provider

    return detect_provider(base_url, model, mode="http") == "openrouter"


def build_camel_completion_params(
    *,
    model: str,
    completion_max_tokens: int,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Baut den Token-Limit-Block für ModelFactory.create()."""
    key = "max_completion_tokens" if uses_max_completion_tokens(model) else "max_tokens"
    params: dict[str, Any] = {key: completion_max_tokens}
    if supports_reasoning_effort_none(model) or _is_openrouter_route(model, base_url):
        params["reasoning_effort"] = "none"
    return params


def build_camel_extra_body(
    *,
    model: str,
    base_url: str,
    num_ctx: int | None,
    think: bool,
) -> dict[str, Any]:
    """Builds Ollama-specific request parameters for the model factory."""
    if not _is_ollama_route(model, base_url):
        return {}

    body: dict[str, Any] = {"think": think}
    if num_ctx is not None:
        body["options"] = {"num_ctx": num_ctx}
    return body


def _is_minimax_route(model: str, base_url: str) -> bool:
    """Determine whether the request targets the MiniMax provider."""
    from app.llm.providers.registry import detect_provider

    return detect_provider(base_url, model, mode="http") == "minimax"


def build_minimax_extra_body(*, model: str, base_url: str, think: bool) -> dict[str, Any]:
    """Builds the MiniMax-specific thinking configuration for a request."""
    if not _is_minimax_route(model, base_url):
        return {}

    return {"thinking": {"type": "adaptive" if think else "disabled"}}
