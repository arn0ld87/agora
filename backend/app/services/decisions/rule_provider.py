"""RuleProvider — deterministischer ``DecisionProvider``-Referenzadapter.

Kapselt Timing, Kosten (immer 0) und Fehlerbehandlung um eine injizierte
Regelfunktion, damit eine bestehende Code-Regel (z. B. die heutige
Persona-Eligibility-Typblockliste) gegen denselben Vertrag laeuft wie ein
LLM- oder Jev-Provider, ohne dass die Regel selbst etwas vom
Decision-Layer-Vertrag wissen muss.

``shadow`` steht auf jedem Ergebnis auf ``False``: ein Provider kennt
seine Rolle in einer Fallback-Kette nicht (ADR-0016). Ein Aufrufer, der
dieses Ergebnis nur zu Kalibrationszwecken ermittelt, markiert es explizit
mit ``result.model_copy(update={"shadow": True})``.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from ...contracts.decision_contract import (
    DecisionQuestion,
    DecisionResult,
    DecisionState,
    RuleOutcome,
)

RuleFn = Callable[[DecisionState, DecisionQuestion], RuleOutcome]


class RuleNotConfiguredError(RuntimeError):
    """``RuleProvider`` wurde ohne ``rule_fn`` konstruiert und aufgerufen.

    Kein stiller Fallback auf ein Platzhalterergebnis — ein Use Case, der
    einen Rule-Provider verdrahtet, aber keine Regel angibt, hat einen
    Konfigurationsfehler, den dieser Fehler laut macht statt ihn als
    "unresolved" zu tarnen.
    """


class RuleProvider:
    """Siehe Moduldocstring. ``rule_fn`` ist reiner Python-Code — kein
    Netzwerk, keine Retries, deshalb ``cost_micros=0`` immer korrekt."""

    def __init__(self, *, use_case_id: str, rule_fn: Optional[RuleFn]) -> None:
        self._use_case_id = use_case_id
        self._rule_fn = rule_fn

    def decide(self, state: DecisionState, question: DecisionQuestion) -> DecisionResult:
        if self._rule_fn is None:
            raise RuleNotConfiguredError(
                f"RuleProvider für use_case_id={self._use_case_id!r} wurde "
                "ohne rule_fn konstruiert."
            )
        t0 = time.monotonic()
        outcome = self._rule_fn(state, question)
        latency_ms = int((time.monotonic() - t0) * 1000)
        return DecisionResult(
            use_case_id=state.use_case_id,
            provider="rule",
            answer=outcome.answer,
            distribution=outcome.distribution,
            probability_yes=outcome.probability_yes,
            confidence=outcome.confidence,
            model_version=None,
            fallback_chain=[],
            request_id=None,
            cost_micros=0,
            latency_ms=latency_ms,
            shadow=False,
        )


__all__ = ["RuleProvider", "RuleOutcome", "RuleFn", "RuleNotConfiguredError"]
