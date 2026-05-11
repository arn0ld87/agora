"""Session-State für den Multi-Provider-AI-Layer.

Hält den aktuell gewählten Provider/Modell, die User-Chat-Historie sowie ein
Audit-Log aller Switch-Ereignisse. Bewusst In-Memory — Persistierung passiert
auf der API-Ebene (Flask-Route oder Frontend-Store).
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .errors import UnknownProviderError
from .model_discovery import ModelInfo, discover_models
from .unified_client import ALLOWED_PROVIDERS, UnifiedLLMClient


@dataclass(frozen=True, slots=True)
class SwitchEvent:
    """Ein protokollierter Provider-/Modell-Wechsel."""

    timestamp: str
    step: int
    from_provider: str | None
    from_model: str | None
    to_provider: str
    to_model: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChatTurn:
    """Ein User-Prompt + LLM-Antwort, inkl. genutztem Setup."""

    step: int
    timestamp: str
    provider: str
    model: str
    prompt: str
    response: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AISession:
    """Stateful Multi-Provider-Chat-Session.

    Beispiel::

        sess = AISession()                 # liest AI_DEFAULT_PROVIDER
        await sess.bootstrap()             # nimmt Default-Modell für Provider
        reply = await sess.chat("Hallo")
        sess.switch(provider="openai", model="gpt-4o", reason="bessere Quali")
        reply = await sess.chat("Und nun?")
    """

    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        client: UnifiedLLMClient | None = None,
    ) -> None:
        initial_provider = (
            provider or os.environ.get("AI_DEFAULT_PROVIDER", "ollama")
        ).strip().lower()
        if initial_provider not in ALLOWED_PROVIDERS:
            raise UnknownProviderError(initial_provider)
        self._client = client or UnifiedLLMClient(provider=initial_provider)
        self._client.set_provider(initial_provider)
        self._provider: str = initial_provider
        self._model: str | None = model
        self._history: list[ChatTurn] = []
        self._switch_history: list[SwitchEvent] = []
        # Initialer Zustand wird als Switch #0 protokolliert, damit das
        # spätere Audit nahtlos ist.
        self._record_switch(
            from_provider=None,
            from_model=None,
            to_provider=initial_provider,
            to_model=model or self._client.default_model(initial_provider),
            reason="session-start",
        )
        if self._model is None:
            self._model = self._client.default_model(initial_provider)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model or ""

    @property
    def step(self) -> int:
        return len(self._history)

    @property
    def history(self) -> list[ChatTurn]:
        return list(self._history)

    @property
    def switch_history(self) -> list[SwitchEvent]:
        return list(self._switch_history)

    # ------------------------------------------------------------------
    # Setup / Discovery
    # ------------------------------------------------------------------

    async def bootstrap(self) -> list[ModelInfo]:
        """Lädt die verfügbaren Modelle für den aktuellen Provider und
        setzt das aktive Modell auf das ENV-Default, falls noch keins
        gewählt wurde."""

        models = await discover_models(self._provider)
        if not self._model:
            preferred = self._client.default_model(self._provider)
            if preferred and any(m.id == preferred for m in models):
                self._model = preferred
            elif models:
                self._model = models[0].id
        return models

    async def list_models(self, provider: str | None = None) -> list[ModelInfo]:
        return await discover_models((provider or self._provider).lower())

    # ------------------------------------------------------------------
    # Switching
    # ------------------------------------------------------------------

    def switch(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        reason: str | None = None,
    ) -> SwitchEvent:
        """Wechselt Provider und/oder Modell und protokolliert das Event."""

        if provider is None and model is None:
            raise ValueError("switch() braucht mindestens 'provider' oder 'model'")

        new_provider = (provider or self._provider).strip().lower()
        if new_provider not in ALLOWED_PROVIDERS:
            raise UnknownProviderError(new_provider)

        # Default-Modell ziehen, wenn Provider wechselt und kein neues Modell angegeben ist.
        if provider and not model:
            new_model = self._client.default_model(new_provider)
        else:
            new_model = model or self._model or self._client.default_model(new_provider)

        from_provider = self._provider
        from_model = self._model

        if new_provider == from_provider and new_model == from_model:
            # No-Op explizit als „bestätigt" loggen, hilft beim Audit.
            return self._record_switch(
                from_provider, from_model, new_provider, new_model,
                reason=reason or "no-change",
            )

        self._provider = new_provider
        self._model = new_model
        self._client.set_provider(new_provider)
        return self._record_switch(
            from_provider, from_model, new_provider, new_model, reason=reason
        )

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    async def chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        if not self._model:
            await self.bootstrap()
        if not self._model:
            raise RuntimeError(
                f"Kein Modell für Provider '{self._provider}' verfügbar — "
                "ENV *_DEFAULT_MODEL setzen oder 'switch(model=...)' nutzen."
            )
        response = await self._client.complete(
            prompt,
            model=self._model,
            provider=self._provider,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        turn = ChatTurn(
            step=self.step + 1,
            timestamp=_now(),
            provider=self._provider,
            model=self._model,
            prompt=prompt,
            response=response,
        )
        self._history.append(turn)
        return response

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AISession":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Serialisierung
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Komplett-Dump für UI/Persistenz (keine Secrets enthalten)."""

        return {
            "provider": self._provider,
            "model": self._model,
            "step": self.step,
            "history": [turn.to_dict() for turn in self._history],
            "switchHistory": [event.to_dict() for event in self._switch_history],
        }

    # ------------------------------------------------------------------
    # Intern
    # ------------------------------------------------------------------

    def _record_switch(
        self,
        from_provider: str | None,
        from_model: str | None,
        to_provider: str,
        to_model: str,
        *,
        reason: str | None = None,
    ) -> SwitchEvent:
        event = SwitchEvent(
            timestamp=_now(),
            step=self.step,
            from_provider=from_provider,
            from_model=from_model,
            to_provider=to_provider,
            to_model=to_model,
            reason=reason,
        )
        self._switch_history.append(event)
        return event


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
