"""Haltung je Beitrag und Positionierungsquote (Issue #1778, Schritt 1.8).

Vor dem Schreiben der Abschnitte wird jeder Simulationsbeitrag einmal nach
seiner Haltung zur Streitfrage klassifiziert. Daraus entstehen die
Positionierungsquote (Anteil der Stimmen, die in der Simulation Stellung
beziehen) und die Lagerverteilung. Liegt die Quote unter der Schwelle, weist
``run_degradation`` das als Degradation aus.

Hat der Lauf keine Streitfrage, gibt es nichts zu klassifizieren: die Analyse
ist dann nicht anwendbar und löst keinen LLM-Aufruf aus.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any, Dict, List, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from ...contracts.stance_analysis_contract import (
    ClassifiedContribution,
    StanceAnalysis,
    StanceClass,
    VoiceStance,
)
from ...utils.logger import get_logger
from ..run_budget import reraise_if_budget_exceeded
from .action_search import build_action_evidence_item, text_contributions
from .sections import action_content
from .storage import write_json_atomic

logger = get_logger("agora.report_agent.stance_analysis")

#: Dateiname der Analyse im Berichtsverzeichnis.
STANCE_ANALYSIS_FILENAME = "stance_analysis.json"

#: Höchstlänge eines Beitrags im Klassifikations-Prompt.
_POST_TEXT_LIMIT = 500

#: ``agent_configs[].stance`` → Haltung zur Streitfrage. Alles andere
#: (``neutral``, ``observer``, unbekannt) ist ``undecided``.
_START_CLASS_BY_CONFIG_STANCE: Dict[str, StanceClass] = {
    "supportive": "in_favour",
    "opposing": "opposed",
}

_SYSTEM_PROMPT = "You classify short social media posts. Answer only with the requested JSON."

_USER_PROMPT_TEMPLATE = """Statement: "{contested_statement}"
For each numbered post decide the author's position on the statement:
- in_favour: the post clearly wants the statement to come true or defends it.
- opposed: the post clearly wants to prevent it or rejects it.
- undecided: the post weighs up, asks for more data, reports neutrally, or does not address the statement.
Judge only what the post says. When in doubt choose undecided.
Posts:
{posts}"""


class StanceBatchItem(BaseModel):
    """Haltung eines nummerierten Beitrags in der LLM-Antwort."""

    model_config = ConfigDict(extra="forbid")

    index: int
    stance: StanceClass


class StanceBatchResponse(BaseModel):
    """LLM-Antwort für einen Batch von Beiträgen."""

    model_config = ConfigDict(extra="forbid")

    items: List[StanceBatchItem]


def _post_line(index: int, action: Mapping[str, Any]) -> str:
    # Einzeilig, damit die Nummerierung im Prompt eindeutig bleibt. Gekürzt
    # wird hart auf die Höchstlänge, ohne angehängte Auslassungszeichen.
    text = " ".join(action_content(dict(action)).split())
    return f"{index}. {text[:_POST_TEXT_LIMIT]}"


def _classify_batch(
    llm_client: Any,
    contested_statement: str,
    batch: Sequence[Mapping[str, Any]],
) -> List[Optional[StanceClass]]:
    prompt = _USER_PROMPT_TEMPLATE.format(
        contested_statement=contested_statement,
        posts="\n".join(_post_line(index, action) for index, action in enumerate(batch, 1)),
    )
    try:
        raw = llm_client.chat_json(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            schema=StanceBatchResponse,
            schema_name="stance_batch",
            context="report",
        )
        response = StanceBatchResponse.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 -- ein ausgefallener Batch bleibt sichtbar unklassifiziert
        # Ein hartes Budget ist das Ende des Laufs, kein Fallback-Fall.
        reraise_if_budget_exceeded(exc)
        logger.warning(
            "Haltungsklassifikation: Batch mit %d Beiträgen fehlgeschlagen: %r",
            len(batch),
            exc,
        )
        return [None] * len(batch)

    # Nennt das Modell einen Index mehrfach mit verschiedenen Haltungen, ist
    # die Antwort für diesen Beitrag widersprüchlich: er gilt als nicht
    # klassifiziert statt still die letzte Nennung zu übernehmen.
    by_index: Dict[int, StanceClass] = {}
    contradictory: set[int] = set()
    for item in response.items:
        if item.index in by_index and by_index[item.index] != item.stance:
            contradictory.add(item.index)
        by_index[item.index] = item.stance
    classes: List[Optional[StanceClass]] = [
        None if index in contradictory else by_index.get(index)
        for index in range(1, len(batch) + 1)
    ]
    missing = sum(1 for stance in classes if stance is None)
    if missing:
        logger.warning(
            "Haltungsklassifikation: %d von %d Beiträgen fehlen in der Antwort",
            missing,
            len(batch),
        )
    return classes


def classify_contributions(
    llm_client: Any,
    contested_statement: str,
    contributions: Sequence[Mapping[str, Any]],
    batch_size: int = 25,
) -> List[Optional[StanceClass]]:
    """Klassifiziert jeden Beitrag nach seiner Haltung zur Streitfrage.

    Je Batch ein Aufruf von ``llm_client.chat_json``. Fehlt ein Beitrag in der
    Antwort oder schlägt der Batch fehl, steht an seiner Stelle ``None``.
    ``BudgetExceededError`` wird durchgereicht.
    """
    size = max(1, int(batch_size))
    classes: List[Optional[StanceClass]] = []
    for start in range(0, len(contributions), size):
        classes.extend(
            _classify_batch(llm_client, contested_statement, contributions[start : start + size])
        )
    return classes


def _contested_statement(simulation_config: Optional[Mapping[str, Any]]) -> Optional[str]:
    contested = (simulation_config or {}).get("contested_question")
    if not isinstance(contested, Mapping):
        return None
    statement = contested.get("statement")
    return statement.strip() if isinstance(statement, str) and statement.strip() else None


def contested_statement_of(simulation_config: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Die Streitfrage des Laufs als Aussage, sonst ``None``."""
    return _contested_statement(simulation_config)


def has_contested_statement(simulation_config: Optional[Mapping[str, Any]]) -> bool:
    """Ob der Lauf eine Streitfrage hat, die Analyse also anwendbar ist."""
    return _contested_statement(simulation_config) is not None


def _camp_of(contribution_classes: Sequence[StanceClass]) -> StanceClass:
    """Lager einer Stimme: die häufigere Seite, bei Gleichstand ``undecided``."""
    counts = Counter(contribution_classes)
    if counts["in_favour"] > counts["opposed"]:
        return "in_favour"
    if counts["opposed"] > counts["in_favour"]:
        return "opposed"
    return "undecided"


def _classified_contributions(
    contributions: Sequence[Mapping[str, Any]],
    classes: Sequence[Optional[StanceClass]],
) -> List[ClassifiedContribution]:
    """Beiträge mit klassifizierter Haltung; ausgefallene Klassifikationen fehlen."""
    classified: List[ClassifiedContribution] = []
    for action, stance in zip(contributions, classes):
        agent_id = action.get("agent_id")
        if stance is None or not isinstance(agent_id, int):
            continue
        round_num = action.get("round_num")
        classified.append(
            ClassifiedContribution(
                agent_id=agent_id,
                agent_name=str(action.get("agent_name") or f"Agent {agent_id}"),
                platform=str(action.get("platform") or "unknown"),
                round_num=round_num if isinstance(round_num, int) else 0,
                action_type=str(action.get("action_type") or "action"),
                producer_key=str(
                    build_action_evidence_item(dict(action)).get("producer_key") or ""
                ),
                stance_class=stance,
            )
        )
    return classified


def _voices(
    simulation_config: Optional[Mapping[str, Any]],
    classified: Sequence[ClassifiedContribution],
) -> List[VoiceStance]:
    """Eine Stimme je Agent der Konfiguration, mit Startwert und Beitragshaltungen."""
    classes_by_agent: Dict[int, List[StanceClass]] = {}
    for contribution in classified:
        classes_by_agent.setdefault(contribution.agent_id, []).append(contribution.stance_class)

    agent_configs = (simulation_config or {}).get("agent_configs")
    voices: List[VoiceStance] = []
    for agent_config in agent_configs if isinstance(agent_configs, list) else []:
        if not isinstance(agent_config, Mapping):
            continue
        agent_id = agent_config.get("agent_id")
        if not isinstance(agent_id, int):
            continue
        voices.append(
            VoiceStance(
                voice_key=f"agent:{agent_id}",
                agent_name=str(agent_config.get("entity_name") or f"Agent {agent_id}"),
                role_family=agent_config.get("role_family") or None,
                start_class=_START_CLASS_BY_CONFIG_STANCE.get(
                    str(agent_config.get("stance") or "").strip().lower(), "undecided"
                ),
                contribution_classes=classes_by_agent.get(agent_id, []),
            )
        )
    return voices


def _camps(voices: Sequence[VoiceStance]) -> tuple[Dict[StanceClass, int], int]:
    """Lagerverteilung und Zahl der positionierten Stimmen.

    Positioniert ist eine Stimme mit mindestens einem Beitrag ``in_favour``
    oder ``opposed``; alle anderen zählen im Lager ``undecided``.
    """
    camp_distribution: Dict[StanceClass, int] = {"in_favour": 0, "opposed": 0, "undecided": 0}
    voices_positioned = 0
    for voice in voices:
        positioned = any(stance != "undecided" for stance in voice.contribution_classes)
        if positioned:
            voices_positioned += 1
            camp_distribution[_camp_of(voice.contribution_classes)] += 1
        else:
            camp_distribution["undecided"] += 1
    return camp_distribution, voices_positioned


def build_stance_analysis(
    simulation_id: str,
    simulation_config: Optional[Mapping[str, Any]],
    actions: Sequence[Mapping[str, Any]],
    interview_stances: Optional[Mapping[str, StanceClass]],
    llm_client: Any,
) -> StanceAnalysis:
    """Baut Positionierungsquote und Lagerverteilung eines Laufs.

    ``interview_stances`` bleibt in dieser Etappe ungenutzt;
    ``VoiceStance.interview_class`` ist ``None``.
    """
    statement = _contested_statement(simulation_config)
    if statement is None:
        return StanceAnalysis(applicable=False)

    contributions = text_contributions(dict(action) for action in actions)
    classes = classify_contributions(llm_client, statement, contributions)

    classified = _classified_contributions(contributions, classes)
    voices = _voices(simulation_config, classified)
    camp_distribution, voices_positioned = _camps(voices)

    voices_total = len(voices)
    analysis = StanceAnalysis(
        contested_statement=statement,
        applicable=True,
        voices_total=voices_total,
        voices_positioned=voices_positioned,
        positioning_ratio=voices_positioned / voices_total if voices_total else None,
        camp_distribution=camp_distribution,
        voices=voices,
        contributions=classified,
        classified_total=len(classified),
        classification_failed=len(contributions) - len(classified),
    )
    logger.info(
        "Haltungsanalyse %s: %d von %d Stimmen positioniert, %d Beiträge klassifiziert, %d ohne Klassifikation",
        simulation_id,
        voices_positioned,
        voices_total,
        analysis.classified_total,
        analysis.classification_failed,
    )
    return analysis


def load_stance_analysis(report_folder: str) -> Optional[StanceAnalysis]:
    """Liest eine bereits gespeicherte Analyse; ``None``, wenn keine gültige vorliegt."""
    path = os.path.join(report_folder, STANCE_ANALYSIS_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return StanceAnalysis.model_validate(json.load(handle))
    except (OSError, ValueError) as exc:
        logger.warning("Gespeicherte Haltungsanalyse nicht lesbar (%s): %r", path, exc)
        return None


def save_stance_analysis(report_folder: str, analysis: StanceAnalysis) -> str:
    """Schreibt die Analyse atomar als ``stance_analysis.json`` und liefert den Pfad."""
    path = os.path.join(report_folder, STANCE_ANALYSIS_FILENAME)
    write_json_atomic(path, analysis.model_dump(mode="json"))
    return path


__all__ = [
    "STANCE_ANALYSIS_FILENAME",
    "load_stance_analysis",
    "StanceBatchResponse",
    "build_stance_analysis",
    "classify_contributions",
    "save_stance_analysis",
]
