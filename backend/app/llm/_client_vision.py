"""Vision / multimodal describe_image mixin for LLMClient."""

import os
from typing import TYPE_CHECKING, Any, Optional
from ..utils.retry import llm_call_with_retry
from .request_plan import (
    VISION_QUIRKS,
    build_request,
    execute_with_retry,
    extract_int_token_usage,
    extract_non_stream_chat_choice,
    strip_thinking_tags,
    thinking_extra_body,
)


class LLMClientVisionMixin:
    if TYPE_CHECKING:

        def __getattr__(self, name: str) -> Any: ...
        def __setattr__(self, name: str, value: Any) -> None: ...

    def describe_image(
        self,
        image_b64: str,
        prompt: str,
        model: Optional[str] = None,
        mime: str = "image/png",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """
        Send a single image + prompt to a vision-capable model and return a
        plain-text description.

        Uses the OpenAI-compatible multimodal message shape:
            {"role": "user", "content": [
                {"type": "text", "text": ...},
                {"type": "image_url", "image_url": {"url": "data:<mime>;base64,<b64>"}}
            ]}

        Works against Ollama Cloud vision models (e.g. gemini-3-flash-preview:cloud).
        """
        vision_model = model or os.environ.get("VISION_MODEL_NAME") or self.model
        max_tokens = self._effective_max_tokens(max_tokens, model=vision_model)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                ],
            }
        ]
        plan = build_request(
            model=vision_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=thinking_extra_body(
                ollama=self._is_ollama(),
                # MiniMax-M3 ist vision-faehig (image_url-Content-Parts) und
                # schaltet Reasoning AN, wenn das thinking-Feld fehlt (#1229)
                # — genau das Rauschen, das dieser Pfad vermeiden will.
                # disabled ist bei M3 wirksam; M2.x akzeptiert es ohne Wirkung.
                minimax=self._is_minimax(),
                # Vision-Boden: ein Bild belegt das Kontextfenster spürbar,
                # deshalb hier mehr als das, was max_tokens allein verlangt.
                num_ctx=max(
                    self._ollama_num_ctx_for(max_tokens, model=vision_model) or 0,
                    8192,
                ),
                # never want reasoning noise in vision output
                think=False,
            ),
        )

        response, latency_ms = execute_with_retry(
            plan,
            provider_attempt=lambda call_kwargs: self._provider_attempt(
                call_kwargs, context="vision", model=vision_model
            ),
            retry_runner=llm_call_with_retry,
            max_retries=self._max_retries,
            initial_delay=self._retry_initial_delay,
            max_delay=self._retry_max_delay,
            quirks=VISION_QUIRKS,
            label="vision",
        )
        try:
            content, _finish_reason, _completion_tokens, _usage = extract_non_stream_chat_choice(
                response
            )
        except Exception as exc:  # noqa: BLE001 — Failure-Telemetrie, dann weiterreichen
            prompt_tokens, completion_tokens = extract_int_token_usage(
                getattr(response, "usage", None)
            )
            self._log_invocation_event(
                stage="vision",
                latency_ms=latency_ms,
                success=False,
                error_type=type(exc).__name__,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=vision_model,
            )
            self._budget_record()
            raise
        self._record_provider_success(response, latency_ms, context="vision", model=vision_model)
        return strip_thinking_tags(content)
