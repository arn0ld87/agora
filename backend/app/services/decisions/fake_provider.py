"""FakeProvider — programmierbarer ``DecisionProvider`` für Tests.

Liefert vorprogrammierte ``DecisionResult``-Objekte der Reihe nach, oder
wirft eine vorprogrammierte Exception — für Tests von Aufrufern, die
gegen den ``DecisionProvider``-Port geschrieben sind (Fallback-Ketten,
Confidence-Schwellen, Timeout-/Fehlerbehandlung), ohne echte Rule-,
LLM- oder Jev-Aufrufe.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Union

from ...contracts.decision_contract import DecisionQuestion, DecisionResult, DecisionState


class FakeProviderExhaustedError(RuntimeError):
    """Mehr ``decide()``-Aufrufe als programmierte Antworten.

    Ein Test, der das erreicht, hat entweder zu wenige Antworten
    vorgegeben oder der Aufrufer ruft öfter auf als erwartet — beides
    gehört sichtbar zu scheitern, nicht in einer wiederholten letzten
    Antwort zu verschwinden."""


class FakeProvider:
    """``responses`` wird der Reihe nach abgearbeitet. Ein ``Exception``-
    Eintrag wird geworfen statt zurückgegeben — so lassen sich Fehlerfälle
    in derselben Sequenz wie Erfolge programmieren."""

    def __init__(self, responses: list[Union[DecisionResult, Exception]]) -> None:
        self._responses: Deque[Union[DecisionResult, Exception]] = deque(responses)
        self.calls: list[tuple[DecisionState, DecisionQuestion]] = []

    def decide(self, state: DecisionState, question: DecisionQuestion) -> DecisionResult:
        self.calls.append((state, question))
        if not self._responses:
            raise FakeProviderExhaustedError(
                f"FakeProvider: decide() Aufruf {len(self.calls)}, aber nur "
                f"{len(self.calls) - 1} Antworten programmiert."
            )
        next_item = self._responses.popleft()
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


__all__ = ["FakeProvider", "FakeProviderExhaustedError"]
