"""Quirks, tokens, and provider detection mixin for LLMClient."""

from typing import TYPE_CHECKING, Any, Dict, Literal, Optional
from .tokens import resolve_max_tokens, resolve_num_ctx_for_output
from .providers import base as _provider_base
from .providers import openai as _provider_openai


class LLMClientQuirksMixin:
    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...
        def __setattr__(self, name: str, value: Any) -> None: ...

    def _is_ollama(self) -> bool:
        """Determine whether the configured endpoint is an Ollama server.

        Returns:
            `true` if the configured base URL identifies an Ollama server, `false` otherwise.
        """
        # Issue #1405: codex_cli hat kein base_url — ohne diesen Kurzschluss
        # wuerde ein zufaellig Ollama-artiger ``Config.LLM_BASE_URL`` (den
        # ``self.base_url`` fuer codex_cli NICHT uebernimmt, aber diese
        # Methode wird trotzdem robust gehalten) den Force-Stream-Pfad in
        # ``chat()`` ausloesen, den der Codex-CLI-Shim nicht unterstuetzt.
        if self._codex_cli_active or self._claude_cli_active:
            return False
        return _provider_base.is_ollama(self.base_url)

    def _reasoning_effort_extra(
        self, *, force_no_thinking: bool = False
    ) -> Dict[str, Any]:
        """Top-level ``reasoning_effort`` fuer OpenAI-Reasoning-Modelle (#1738).

        Provider kommt aus der bestehenden Detection (``_detect_provider``),
        die Modell-/Wert-Logik steht in
        :func:`app.llm.providers.openai.reasoning_effort_kwargs`.
        """
        return _provider_openai.reasoning_effort_kwargs(
            provider=self._detect_provider(),
            model=self.model or "",
            effort=getattr(self, "reasoning_effort", None),
            force_no_thinking=force_no_thinking,
        )

    def _is_minimax(self) -> bool:
        """Determine whether the configured endpoint is a MiniMax service.

        Returns:
            bool: `true` if the endpoint uses MiniMax, `false` otherwise.
        """
        if self._codex_cli_active or self._claude_cli_active:
            return False
        return self._detect_provider() == "minimax"

    def _minimax_thinking_extra_body(
        self, *, force_no_thinking: bool = False
    ) -> Dict[str, Any]:
        """
        Builds the MiniMax thinking configuration for a request.
        
        Parameters:
            force_no_thinking (bool): Whether to disable reasoning regardless of the
                configured thinking preference.
        
        Returns:
            Dict[str, Any]: A request body containing ``thinking.type`` set to
                ``"adaptive"`` when reasoning is enabled or ``"disabled"`` otherwise.
        """
        think_on = self._think and not force_no_thinking
        return {"thinking": {"type": "adaptive" if think_on else "disabled"}}

    @staticmethod
    def _uses_max_completion_tokens(model: str) -> bool:
        """Determine whether a model uses the ``max_completion_tokens`` parameter.
        
        Parameters:
            model (str): Model name to inspect.
        
        Returns:
            bool: ``True`` if the model uses ``max_completion_tokens``, ``False`` otherwise.
        """
        return _provider_openai.uses_max_completion_tokens(model)

    @staticmethod
    def _is_token_key_400(exc: Exception) -> bool:
        """Siehe ``app.llm.providers.openai.is_token_key_400``."""
        return _provider_openai.is_token_key_400(exc)

    @staticmethod
    def _swap_token_kwargs(kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Siehe ``app.llm.providers.openai.swap_token_kwargs``."""
        return _provider_openai.swap_token_kwargs(kwargs)

    @staticmethod
    def _omits_temperature(model: str) -> bool:
        """Siehe ``app.llm.providers.openai.omits_temperature`` (#1096)."""
        return _provider_openai.omits_temperature(model)

    @staticmethod
    def _is_temperature_400(exc: Exception) -> bool:
        """Siehe ``app.llm.providers.openai.is_temperature_400`` (#1096)."""
        return _provider_openai.is_temperature_400(exc)

    def _effective_max_tokens(
        self,
        max_tokens: int,
        *,
        model: Optional[str] = None,
        enforce_floor: bool = True,
    ) -> int:
        """Siehe :func:`app.llm.tokens.resolve_max_tokens`.

        Jede öffentliche Methode, die ein ``max_tokens`` entgegennimmt, führt
        es hier durch — der Boden gilt damit unabhängig davon, was der
        einzelne Aufrufer angefordert hat.
        """
        return resolve_max_tokens(
            max_tokens,
            model=model if model is not None else self.model,
            enforce_floor=enforce_floor,
        )

    def _ollama_num_ctx_for(self, max_tokens: int, *, model: Optional[str] = None) -> Optional[int]:
        """``num_ctx``, angehoben auf das, was *max_tokens* Ausgabe braucht.

        Bei Ollama ist ``max_tokens`` das ``num_predict`` und teilt sich das
        Fenster mit dem Prompt — siehe
        :func:`app.llm.tokens.resolve_num_ctx_for_output`.
        """
        return resolve_num_ctx_for_output(
            self._num_ctx,
            max_tokens,
            model=model if model is not None else self.model,
        )

    def _completion_token_kwargs(
        self, max_tokens: int, model: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Build the token-limit parameter for the selected model.
        
        Parameters:
            max_tokens (int): Maximum number of completion tokens.
            model (Optional[str]): Model used to select the token-limit parameter; defaults to the client's model.
        
        Returns:
            Dict[str, int]: A mapping containing either ``max_completion_tokens`` or ``max_tokens`` with the requested limit.
        """
        target_model = model if model is not None else (self.model or "")
        key = (
            "max_completion_tokens"
            if self._uses_max_completion_tokens(target_model)
            else "max_tokens"
        )
        return {key: max_tokens}

    def _detect_provider(
        self, *, model: Optional[str] = None
    ) -> Literal[
        "ollama", "cloud", "minimax", "openai", "google", "anthropic", "openrouter", "unknown"
    ]:
        """
        Identify the LLM provider associated with the configured endpoint and model.

        ``model`` ueberschreibt ``self.model`` fuer diese eine Detection —
        noetig, damit Aufrufer mit einem abweichenden effektiven Modell
        (z. B. ``describe_image(model=...)``) denselben Modellwert an die
        Provider-Erkennung reichen, den sie auch fuer die Telemetrie nutzen
        (#1478 Codex P1, Runde 5). Default bleibt ``self.model``, damit alle
        bestehenden Aufrufer ohne Override unveraendertes Verhalten behalten.

        Returns:
            str: The provider name: ``"ollama"``, ``"cloud"``, ``"minimax"``,
                ``"openai"``, ``"google"``, ``"anthropic"``, ``"openrouter"``, or ``"unknown"``.
        """
        # codex_cli wird nie aus einer base_url erraten (verboten laut
        # AGENTS.md: keine Detection-Heuristik neben registry.py::
        # detect_provider) — es ist immer eine explizite Auswahl. "unknown"
        # ist das korrekte Label fuer dieses Vokabular, nicht ein neuer Wert.
        if self._codex_cli_active or self._claude_cli_active:
            return "unknown"
        effective_model = model if model is not None else self.model
        return _provider_base.detect_provider(self.base_url, effective_model)
