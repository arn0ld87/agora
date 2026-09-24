"""Port fuer kleine typisierte Entscheidungen (f005, ADR-0016/0017).

Nach dem Muster von ``llm_profile_repository.py``: ein ``Protocol``, keine
ABC. Ein ``DecisionProvider`` beantwortet genau eine ``DecisionQuestion``
je Aufruf gegen einen ``DecisionState`` — Choice, Score oder Noul, nie
freien Text (dafuer bleibt ``LLMClient.chat_json`` zustaendig, ADR-0017).

Was dieser Port NICHT tut: Fallback-Ketten, Confidence-Schwellen oder
Budget-Durchsetzung. Das ist Aufgabe des Aufrufers (des jeweiligen Use
Case) — ein Provider kennt nur sich selbst, keine Kette.

Keine generische Provider-Factory: Anders als bei ``LlmProfileRepository``
(genau eine Ablage aktiv, ausgewaehlt ueber einen Backend-String) braucht
ein Use Case hier mehrere Provider GLEICHZEITIG (Rule als Bestandspfad,
Jev im Shadow-Modus daneben) statt eines einzigen ausgewaehlten Adapters
— eine Factory, die "den einen richtigen Provider" liefert, waere die
falsche Abstraktion. Aufrufer konstruieren die Referenzadapter aus
``services.decisions`` direkt; ``Config.DECISION_LAYER_MODE`` ist die
einzige zentrale Auflösung, und sie beantwortet nur die Frage "ueberhaupt
aktiv?" (ADR-0016: Flag-off behaelt den aktuellen Pfad unveraendert).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts.decision_contract import DecisionQuestion, DecisionResult, DecisionState


@runtime_checkable
class DecisionProvider(Protocol):
    """Beantwortet eine typisierte Entscheidung. Siehe Moduldocstring."""

    def decide(self, state: DecisionState, question: DecisionQuestion) -> DecisionResult:
        """Liefert ein ``DecisionResult`` oder wirft.

        Provider werfen bei Fehlern (Timeout, Rate Limit, Schemafehler,
        Verbindungsfehler) — sie liefern nie selbst ein
        ``provider="unresolved"``-Ergebnis. Das Zusammenfuehren mehrerer
        Provider zu einer Fallback-Kette mit diesem Terminalzustand ist
        Aufgabe des Aufrufers (ADR-0016).
        """
        ...


def decision_layer_mode(use_case_id: str) -> str:
    """``"disabled"``, ``"shadow"`` oder ``"authoritative"``.

    Aktuell global ueber ``Config.DECISION_LAYER_MODE`` (ein einziger
    Pilot-Use-Case in dieser Slice). ``use_case_id`` ist bereits Teil der
    Signatur, damit ein Aufrufer nicht direkt auf ``Config`` zugreift und
    der Umstieg auf je-Use-Case-Granularitaet (ADR-0016, "Was dieser
    Entwurf nicht entscheidet") diese eine Stelle aendert statt jeden
    Aufrufer.
    """
    from ..config import Config

    return Config.DECISION_LAYER_MODE


__all__ = ["DecisionProvider", "decision_layer_mode"]
