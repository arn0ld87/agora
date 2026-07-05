"""
Native OpenAI Function-Calling (chat_with_tools).

Extracted verbatim from ``app/utils/llm_client.py`` as part of issue #582
(mechanical split — no behavior change). ``_chat_with_tools`` stays a plain
function bound onto ``LLMClient`` at import time in ``client.py`` (exactly as
in the original module) so this module never needs to import ``LLMClient``
itself (no circular import).
"""

import json
import os
import re
from typing import Any, Dict, List, Literal, TypedDict

from ..utils.logger import get_logger
from ..utils.retry import llm_call_with_retry

logger = get_logger("agora.llm_client")


class ToolCallItem(TypedDict):
    id: str
    name: str
    arguments: dict


class ToolCallResponse(TypedDict):
    content: str
    tool_calls: List[ToolCallItem]
    finish_reason: str
    raw_response: Any


def _extract_tool_calls_from_message(message: Any) -> List[ToolCallItem]:
    """Normalisiert OpenAI-SDK ToolCall-Objekte zu ``ToolCallItem``-Dicts."""
    result: List[ToolCallItem] = []
    tool_calls = getattr(message, "tool_calls", None)
    if not tool_calls:
        return result
    for tc in tool_calls:
        tc_id = getattr(tc, "id", "") or ""
        func = getattr(tc, "function", None)
        name = getattr(func, "name", "") or ""
        args_raw = getattr(func, "arguments", "") or ""
        try:
            arguments: dict = json.loads(args_raw) if args_raw else {}
        except json.JSONDecodeError:
            logger.warning(
                "LLMClient: failed to parse tool arguments as JSON (tool=%s): %s",
                name,
                args_raw[:200],
            )
            arguments = {}
        result.append(ToolCallItem(id=tc_id, name=name, arguments=arguments))
    return result


def _accumulate_streaming_tool_calls(
    chunks: Any,
) -> tuple[str, List[ToolCallItem], str]:
    """Akkumuliert Streaming-Chunks und baut content + tool_calls zusammen.

    Gibt ``(content, tool_calls, finish_reason)`` zurück.
    """
    content_parts: List[str] = []
    finish_reason: str = "stop"

    # Indexed accumulator: index → {id, name, arguments_parts}
    tc_acc: dict[int, dict] = {}

    for chunk in chunks:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if choice.finish_reason:
            finish_reason = choice.finish_reason
        delta = choice.delta

        # Textinhalt akkumulieren
        piece = getattr(delta, "content", None)
        if piece:
            content_parts.append(piece)

        # Tool-Call-Deltas akkumulieren
        tc_deltas = getattr(delta, "tool_calls", None)
        if tc_deltas:
            for tc_delta in tc_deltas:
                idx = getattr(tc_delta, "index", 0) or 0
                if idx not in tc_acc:
                    tc_acc[idx] = {"id": "", "name": "", "arguments_parts": []}
                entry = tc_acc[idx]
                tc_id = getattr(tc_delta, "id", None)
                if tc_id:
                    entry["id"] = tc_id
                func_delta = getattr(tc_delta, "function", None)
                if func_delta:
                    fname = getattr(func_delta, "name", None)
                    if fname:
                        entry["name"] = fname
                    fargs = getattr(func_delta, "arguments", None)
                    if fargs:
                        entry["arguments_parts"].append(fargs)

    content = "".join(content_parts)

    tool_calls: List[ToolCallItem] = []
    for idx in sorted(tc_acc.keys()):
        entry = tc_acc[idx]
        args_str = "".join(entry["arguments_parts"])
        try:
            arguments = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError:
            logger.warning(
                "LLMClient: failed to parse streaming tool arguments (tool=%s): %s",
                entry["name"],
                args_str[:200],
            )
            arguments = {}
        tool_calls.append(
            ToolCallItem(id=entry["id"], name=entry["name"], arguments=arguments)
        )

    return content, tool_calls, finish_reason


# P5.4: Native OpenAI function-calling method
# Wird in LLMClient eingebunden als Methode — hier als Funktion definiert,
# damit der TypedDict-Import nicht in der Klasse wiederholt werden muss.


def _chat_with_tools(
    self: "Any",
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    tool_choice: str = "auto",
    temperature: float = 0.5,
    max_tokens: int = 4096,
    context: Literal[
        "chat", "chat_json", "embedding", "report", "persona", "graph", "unknown"
    ] = "report",
) -> ToolCallResponse:
    """Native OpenAI function-calling: sendet ``tools=`` + ``tool_choice=`` an die API.

    Streaming-Pfad (Ollama): Tool-Call-Deltas werden akkumuliert.
    Nicht-Streaming-Pfad: ``message.tool_calls`` direkt normalisiert.

    Bei Provider ``unknown`` oder wenn die API keine ``tool_calls`` zurückgibt,
    bleibt ``tool_calls=[]`` und ``content`` enthält den Freitext — der Caller
    kann dann auf den XML-Fallback-Parser zurückgreifen.

    E2E-Stub-Pfad: analog zu ``chat()`` via ``AGORA_E2E_LLM_MODE=stub``.
    """
    self._publish_model_active(context, max_tokens=max_tokens, temperature=temperature)

    # E2E-Stub-Pfad
    if os.environ.get("AGORA_E2E_LLM_MODE") == "stub":
        from app.utils.llm_e2e_stub import e2e_stub_chat_with_tools_response
        logger.info(
            "LLMClient.chat_with_tools: E2E-Stub aktiv — ueberspringe LLM-Call (context=%s)",
            context,
        )
        return e2e_stub_chat_with_tools_response(messages=messages, tools=tools)

    # Provider-Unknown-Short-Circuit: für nicht eindeutig identifizierbare Provider
    # (weder Ollama lokal noch Ollama-Cloud noch OpenAI) können wir nicht garantieren,
    # dass das Backend ``tools=``/``tool_choice=`` versteht. Statt einen 400er zu
    # provozieren, fallen wir auf einen ``chat()``-Call ohne Tools zurück und liefern
    # ``tool_calls=[]`` — der Caller (workflow.generate_section_react) erkennt das
    # und nutzt den XML-Fallback-Parser. So bleibt das ReACT-Loop-Verhalten stabil.
    provider = self._detect_provider()
    if provider == "unknown":
        logger.info(
            "LLMClient.chat_with_tools: provider=unknown (model=%s, base=%s) — "
            "skipping tools= and falling back to chat() for XML-tool-call parsing",
            self.model,
            self.base_url,
        )
        fallback_content = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            context=context,
        ) or ""
        return ToolCallResponse(
            content=fallback_content,
            tool_calls=[],
            finish_reason="stop",
            raw_response=None,
        )

    import time as _time
    _t0 = _time.monotonic()

    kwargs: Dict[str, Any] = {
        "model": self.model,
        "messages": messages,
        "temperature": temperature,
        "tools": tools,
        "tool_choice": tool_choice,
    }
    kwargs.update(self._completion_token_kwargs(max_tokens))

    if self._is_ollama():
        extra_body: Dict[str, Any] = {}
        if self._num_ctx:
            extra_body["options"] = {"num_ctx": self._num_ctx}
        extra_body["think"] = self._think
        kwargs["extra_body"] = extra_body

    force_stream = (
        self._is_ollama()
        and os.environ.get("LLM_FORCE_STREAM", "true").lower() in ("1", "true", "yes")
    )

    def _create(call_kwargs: Dict[str, Any]) -> Any:
        return llm_call_with_retry(
            self.client.chat.completions.create,
            max_retries=self._max_retries,
            initial_delay=self._retry_initial_delay,
            max_delay=self._retry_max_delay,
            **call_kwargs,
        )

    def _create_with_fallback(call_kwargs: Dict[str, Any]) -> Any:
        try:
            return _create(call_kwargs)
        except Exception as exc:  # noqa: BLE001
            if not self._is_token_key_400(exc):
                raise
            swapped = self._swap_token_kwargs(call_kwargs)
            if swapped is None:
                raise
            logger.warning(
                "LLM 400 on token-limit key (tools path) — retrying once with swapped key "
                "(model=%s, msg=%s)",
                self.model,
                str(exc)[:200],
            )
            return _create(swapped)

    content: str = ""
    tool_calls: List[ToolCallItem] = []
    finish_reason: str = "stop"
    raw_response: Any = None

    try:
        if force_stream:
            kwargs["stream"] = True
            stream = _create_with_fallback(kwargs)
            content, tool_calls, finish_reason = _accumulate_streaming_tool_calls(stream)
        else:
            raw_response = _create_with_fallback(kwargs)
            choice = raw_response.choices[0]
            finish_reason = getattr(choice, "finish_reason", "stop") or "stop"
            message = choice.message
            content = getattr(message, "content", None) or ""
            tool_calls = _extract_tool_calls_from_message(message)
    except Exception as exc:  # noqa: BLE001
        elapsed = _time.monotonic() - _t0
        self._log_invocation_event(
            stage=context,
            latency_ms=elapsed * 1000,
            success=False,
            error_type=exc.__class__.__name__,
            http_status=getattr(exc, "status_code", None),
        )
        raise

    elapsed = _time.monotonic() - _t0
    logger.info(
        "LLM chat_with_tools returned model=%s finish=%s tool_call_count=%d elapsed=%.1fs stream=%s",
        self.model,
        finish_reason,
        len(tool_calls),
        elapsed,
        force_stream,
    )
    self._log_invocation_event(
        stage=context,
        latency_ms=elapsed * 1000,
        success=True,
    )

    # <think>...</think> aus Textinhalt entfernen (analog zu chat())
    content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.IGNORECASE).strip()

    return ToolCallResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        raw_response=raw_response,
    )
