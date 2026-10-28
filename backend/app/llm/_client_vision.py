"""Vision / multimodal describe_image mixin for LLMClient."""

import os
import re
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple
from ..utils.retry import llm_call_with_retry
from .request_plan import build_request, execute, thinking_extra_body, TOKEN_KEY_QUIRK


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
        vision_model = model or os.environ.get('VISION_MODEL_NAME') or self.model
        max_tokens = self._effective_max_tokens(max_tokens, model=vision_model)
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
            ],
        }]
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

        def _create_vision(call_kwargs: Dict[str, Any]) -> Tuple[Any, float]:
            """Ein physischer Providerattempt mit transient-retry.

            Issue #1478 (Codex P1): Budget-Check, Failure-Telemetrie und
            -Record laufen INNERHALB von ``_provider_attempt`` — analog zu
            ``chat()``. Vorher lag der Guard um die gesamte ``execute()``-
            Operation, sodass ein Retry oder ein ``TOKEN_KEY_QUIRK``-
            Korrekturversuch nur EINEN Budget-Check/Event/Record erzeugte,
            obwohl mehrere physische Requests abgesetzt wurden. Jeder
            Retried-Attempt (transient retry, Token-Key-Fallback) bekommt
            damit sein eigenes Check/Event/Record-Triplet.

            Issue #1478 (Codex P1, Runde 4): ``model=vision_model`` wird
            durchgereicht, damit die Failure-Telemetrie das tatsaechlich
            angefragte Modell traegt, wenn ``model=``-Override oder
            ``VISION_MODEL_NAME`` von ``self.model`` abweichen — sonst
            gruppiert/bepreist das Ledger die Usage unter dem falschen Modell.
            """
            return llm_call_with_retry(
                lambda: self._provider_attempt(
                    call_kwargs, context="vision", model=vision_model
                ),
                max_retries=self._max_retries,
                initial_delay=self._retry_initial_delay,
                max_delay=self._retry_max_delay,
            )

        # Analog zu ``chat()``: ``execute`` sieht keinen eigenen Budget-Check
        # mehr — jeder physische Request (erster Call, Retry, Token-Key-
        # Fallback) bekommt seinen ueber ``_provider_attempt``.
        response, latency_ms = execute(
            plan, _create_vision, quirks=(TOKEN_KEY_QUIRK,), label="vision"
        )
        # Issue #1478 (Codex P1, Runde 7): die Antwort VOR dem Success-Record
        # parsen — analog zum bereits abgesicherten Textpfad (``chat()``).
        # Eine HTTP-erfolgreiche, aber kaputte Antwort (leeres ``choices``,
        # eine Choice ohne ``message.content``) darf keinen Erfolg im
        # Ledger/in der Telemetrie hinterlassen, bevor der lokale Parse-
        # Schritt selbst gelungen ist.
        try:
            content = response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 — Failure-Telemetrie, dann weiterreichen
            usage = getattr(response, "usage", None)
            prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
            completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
            self._log_invocation_event(
                stage="vision",
                latency_ms=latency_ms,
                success=False,
                error_type=type(exc).__name__,
                prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
                completion_tokens=completion_tokens if isinstance(completion_tokens, int) else None,
                model=vision_model,
            )
            self._budget_record()
            raise
        self._record_provider_success(
            response, latency_ms, context="vision", model=vision_model
        )
        content = re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE).strip()
        return content
