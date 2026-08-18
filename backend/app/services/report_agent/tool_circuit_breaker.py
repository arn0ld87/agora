"""Ein terminal ausgefallenes Tool wird abgeschaltet, nicht abgeraten.

Im Referenzlauf ``report_cc2ef45da5e9`` meldete der erste
``interview_agents``-Aufruf:

    Interview tool TERMINALLY UNAVAILABLE for this report run.
    Do NOT call interview_agents again.

Danach wurde das Tool sieben weitere Male aufgerufen. Acht Aufrufe, null
erfolgreiche Interviews, jedes Mal derselbe Ausfall — und jedes Mal Zeit und
Budget dafür.

Der Fehler liegt nicht beim Modell. Ein Satz im Tool-Ergebnis ist eine Bitte,
und eine Bitte in einem Prompt ist keine Zusicherung: das Tool stand in jeder
Iteration unverändert im angebotenen Schema, und ein Modell, das etwas über
Stakeholder-Reaktionen wissen will, greift zum offensichtlich dafür gedachten
Werkzeug. Wer verhindern will, dass ein Tool erneut aufgerufen wird, muss es
wegnehmen.

Der Breaker ist bewusst eng: nur terminale, nicht erneut versuchbare Ausfälle
schalten ab. Ein einzelner Timeout ist keiner — er darf wiederholt werden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class ToolExecutionState:
    """Warum ein Tool für den Rest des Laufs nicht mehr zur Verfügung steht."""

    tool_name: str
    terminal_failure: bool
    retryable: bool
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "terminal_failure": self.terminal_failure,
            "retryable": self.retryable,
            "reason": self.reason,
        }


@dataclass
class ToolCircuitBreaker:
    """Welche Tools in diesem Report-Lauf abgeschaltet sind.

    Der Zustand gilt für den gesamten Lauf, nicht für eine Iteration oder eine
    Section. Genau daran scheiterte der Hinweistext: er stand im
    Nachrichtenverlauf *einer* Section und war spätestens beim nächsten
    Abschnitt aus dem Kontext gefallen.
    """

    _states: Dict[str, ToolExecutionState] = field(default_factory=dict)
    #: Wie oft ein Tool angefordert wurde — abgewiesene Aufrufe eingeschlossen.
    #: Die Anforderung bezeugt, dass der Bericht das Werkzeug vorsah; ohne diese
    #: Zahl ließe sich "acht Aufrufe, null Interviews" nachträglich nicht mehr
    #: feststellen.
    _requests: Dict[str, int] = field(default_factory=dict)

    def record_request(self, tool_name: str) -> None:
        name = (tool_name or "").strip()
        if name:
            self._requests[name] = self._requests.get(name, 0) + 1

    def request_count(self, tool_name: str) -> int:
        return self._requests.get((tool_name or "").strip(), 0)

    def trip(self, tool_name: str, reason: str, *, retryable: bool = False) -> None:
        """Schaltet ein Tool ab. Ein erneuter Ausfall überschreibt den Grund nicht."""
        name = (tool_name or "").strip()
        if not name or name in self._states:
            return
        self._states[name] = ToolExecutionState(
            tool_name=name,
            terminal_failure=not retryable,
            retryable=retryable,
            reason=(reason or "").strip()[:300] or "terminaler Ausfall",
        )

    def is_disabled(self, tool_name: str) -> bool:
        state = self._states.get((tool_name or "").strip())
        return bool(state and state.terminal_failure)

    @property
    def disabled_tools(self) -> frozenset[str]:
        return frozenset(
            name for name, state in self._states.items() if state.terminal_failure
        )

    def reason_for(self, tool_name: str) -> str:
        state = self._states.get((tool_name or "").strip())
        return state.reason if state else ""

    def filter_tools(self, tools: Iterable[Any], *, name_of: Any = None) -> List[Any]:
        """Entfernt abgeschaltete Tools aus einem Angebot ans Modell.

        ``name_of`` liest den Tool-Namen aus einem Eintrag. Ohne Angabe wird
        der Eintrag selbst als Name gelesen — das deckt reine Namenslisten ab.
        """
        resolve = name_of or (lambda entry: entry)
        return [tool for tool in tools if not self.is_disabled(str(resolve(tool)))]

    def as_payload(self) -> List[Dict[str, Any]]:
        return [state.as_dict() for state in self._states.values()]

    def __bool__(self) -> bool:
        return bool(self._states)


def breaker_for(agent: Any) -> ToolCircuitBreaker:
    """Der Breaker dieses Report-Laufs, bei Bedarf angelegt.

    Freie Funktion aus demselben Grund wie beim Coverage-Ledger: mehrere
    Aufrufer reichen ein fremdes Objekt als ``self`` in die Agent-Methoden.
    """
    breaker = getattr(agent, "_tool_circuit_breaker", None)
    if isinstance(breaker, ToolCircuitBreaker):
        return breaker
    breaker = ToolCircuitBreaker()
    try:
        agent._tool_circuit_breaker = breaker
    except AttributeError:  # pragma: no cover — __slots__-Objekte
        pass
    return breaker


__all__ = ["ToolCircuitBreaker", "ToolExecutionState", "breaker_for"]
