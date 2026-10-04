"""Streitfrage eines Laufs ermitteln (Issue #1778, Schritt 1.4).

Der Konfigurations-Assistent leitet aus der Simulationsanforderung die eine
Streitfrage ab (siehe CONTEXT.md, Abschnitt Streitfrage). Das Ergebnis ist
der Vertrag ``ContestedQuestion``. Ein harter Budgetabbruch
(``BudgetExceededError``) wird durchgereicht; jeder andere Fehler führt auf
die sichtbare Angabe, dass keine Streitfrage ermittelt werden konnte.
"""

from __future__ import annotations

from typing import Any, Callable

from ..contracts.contested_question_contract import ContestedQuestion
from ..utils.logger import get_logger
from .run_budget import reraise_if_budget_exceeded
from .simulation_config_schemas import ContestedQuestionResponse

logger = get_logger("agora.simulation_config_contested_question")

_SYSTEM_PROMPT = (
    "You derive the single contested question of a stakeholder simulation. "
    "Answer in the language of the simulation requirement."
)

_USER_PROMPT_TEMPLATE = """Simulation requirement:
{simulation_requirement}

Task: State the ONE proposition that the stakeholders in this scenario are for or against.
Rules:
- It must be a full declarative sentence that can be affirmed or denied, e.g. "Die Geburtshilfe in Brenkhausen wird zum 30. Juni 2027 geschlossen."
- Phrase it as the measure or decision itself, never as its negation. "In favour" must mean: the measure happens.
- If the requirement contains several contested points, choose the one the requirement is mainly about.
- If the requirement contains no decidable proposition (for example an open perception question), set has_contested_question=false and give absence_reason in one sentence."""


def generate_contested_question(
    call_llm: Callable[[str, str, Any], dict],
    simulation_requirement: str,
) -> ContestedQuestion:
    """Bestimmt die Streitfrage des Laufs über einen LLM-Aufruf.

    ``call_llm`` ist z. B. ``SimulationConfigGenerator._call_llm_with_retry``
    mit der Signatur ``(prompt, system_prompt, schema)`` und liefert ein
    validiertes Dict zurück.
    """
    prompt = _USER_PROMPT_TEMPLATE.format(simulation_requirement=simulation_requirement)
    try:
        result = call_llm(prompt, _SYSTEM_PROMPT, ContestedQuestionResponse)
        response = ContestedQuestionResponse.model_validate(result)
    except Exception as exc:  # noqa: BLE001 -- bewusst breit: Fehlschlagen ist sichtbarer "none"-Fall
        # Ein hartes Budget ist kein Fallback-Fall, sondern das Laufende (siehe
        # ``reraise_if_budget_exceeded``): durchreichen, nicht schlucken.
        reraise_if_budget_exceeded(exc)
        logger.warning("Streitfrage konnte nicht ermittelt werden: %s", exc)
        return ContestedQuestion(
            origin="none",
            absence_reason="Streitfrage konnte nicht ermittelt werden.",
        )
    if response.has_contested_question and response.statement:
        return ContestedQuestion(statement=response.statement, origin="assistant")
    return ContestedQuestion(origin="none", absence_reason=response.absence_reason)
