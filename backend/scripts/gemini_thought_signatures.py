"""Gemini-3-Thought-Signaturen fuer CAMELs rekonstruierte Tool-Historie."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from camel.models.gemini_model import GeminiModel


THOUGHT_SIGNATURE_VALIDATOR_ESCAPE = "skip_thought_signature_validator"


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def extract_thought_signatures(response: Any) -> dict[str, dict[str, Any]]:
    """Liest Googles ``extra_content`` aus einer OpenAI-Compat-Antwort."""
    signatures: dict[str, dict[str, Any]] = {}
    for choice in _field(response, "choices") or []:
        message = _field(choice, "message")
        for tool_call in _field(message, "tool_calls") or []:
            tool_call_id = _field(tool_call, "id")
            extra_content = _field(tool_call, "extra_content")
            if extra_content is None:
                model_extra = _field(tool_call, "model_extra") or {}
                extra_content = _field(model_extra, "extra_content")
            google = _field(extra_content, "google")
            signature = _field(google, "thought_signature")
            if isinstance(tool_call_id, str) and isinstance(signature, str):
                signatures[tool_call_id] = {
                    "google": {"thought_signature": signature}
                }
    return signatures


def echo_thought_signatures(
    messages: list[dict[str, Any]],
    signatures: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fuegt jedem rekonstruierten Gemini-Tool-Schritt seine Signatur hinzu."""
    processed = deepcopy(messages)
    for message in processed:
        if message.get("role") != "assistant":
            continue
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            continue

        first_call = tool_calls[0]
        if not isinstance(first_call, dict) or first_call.get("extra_content"):
            continue
        tool_call_id = first_call.get("id")
        captured = signatures.get(tool_call_id) if isinstance(tool_call_id, str) else None
        first_call["extra_content"] = deepcopy(captured) if captured else {
            "google": {
                "thought_signature": THOUGHT_SIGNATURE_VALIDATOR_ESCAPE,
            }
        }
    return processed


class GeminiThoughtSignatureModel(GeminiModel):
    """CAMEL-Gemini-Modell mit verlustfreier Tool-Signatur-Historie."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._agora_thought_signatures: dict[str, dict[str, Any]] = {}
        super().__init__(*args, **kwargs)

    def _process_messages(self, messages: Any) -> list[dict[str, Any]]:
        processed = super()._process_messages(messages)
        return echo_thought_signatures(processed, self._agora_thought_signatures)

    def _request_chat_completion(self, messages: Any, tools: Any = None) -> Any:
        response = super()._request_chat_completion(messages, tools)
        self._agora_thought_signatures.update(extract_thought_signatures(response))
        return response

    async def _arequest_chat_completion(self, messages: Any, tools: Any = None) -> Any:
        response = await super()._arequest_chat_completion(messages, tools)
        self._agora_thought_signatures.update(extract_thought_signatures(response))
        return response


def create_gemini_thought_signature_model(
    *,
    model_type: str,
    model_config_dict: dict[str, Any],
    api_key: str,
) -> GeminiThoughtSignatureModel:
    return GeminiThoughtSignatureModel(
        model_type=model_type,
        model_config_dict=model_config_dict,
        api_key=api_key,
    )


__all__ = [
    "THOUGHT_SIGNATURE_VALIDATOR_ESCAPE",
    "GeminiThoughtSignatureModel",
    "create_gemini_thought_signature_model",
    "echo_thought_signatures",
    "extract_thought_signatures",
]
