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
    Coalition,
    PositionShift,
    StanceAnalysis,
    StanceClass,
    StanceDeviation,
    VoiceStance,
)
from ...utils.logger import get_logger
from ..run_budget import reraise_if_budget_exceeded
from .action_search import build_action_evidence_item, text_contributions
from .artifact_read import read_contract_artifact
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
        role_family_raw = agent_config.get("role_family") or agent_config.get("entity_type")
        role_family = str(role_family_raw).strip() if role_family_raw else None
        voices.append(
            VoiceStance(
                voice_key=f"agent:{agent_id}",
                agent_name=str(agent_config.get("entity_name") or f"Agent {agent_id}"),
                role_family=role_family or None,
                start_class=_START_CLASS_BY_CONFIG_STANCE.get(
                    str(agent_config.get("stance") or "").strip().lower(), "undecided"
                ),
                contribution_classes=classes_by_agent.get(agent_id, []),
            )
        )
    return voices


def _compute_interview_classes(
    interviews: Sequence[Mapping[str, Any]],
) -> Dict[str, StanceClass]:
    """Berechnet die Haltungsklasse je Stimme aus den Interview-Belegen."""
    stances_by_voice: Dict[str, List[float]] = {}
    for item in interviews:
        vkey = item.get("voice_key")
        if not vkey and item.get("agent_id") is not None:
            vkey = f"agent:{item['agent_id']}"
        raw = item.get("raw")
        if not vkey and isinstance(raw, Mapping) and raw.get("agent_id") is not None:
            vkey = f"agent:{raw['agent_id']}"
        if not vkey:
            continue

        stance_val = item.get("topic_stance")
        if stance_val is None and isinstance(raw, Mapping):
            stance_val = raw.get("topic_stance")
        if isinstance(stance_val, (int, float)) and not isinstance(stance_val, bool):
            stances_by_voice.setdefault(str(vkey), []).append(float(stance_val))

    result: Dict[str, StanceClass] = {}
    for vkey, stances in stances_by_voice.items():
        if not stances:
            continue
        mean_val = sum(stances) / len(stances)
        if mean_val >= 0.25:
            result[vkey] = "in_favour"
        elif mean_val <= -0.25:
            result[vkey] = "opposed"
        else:
            result[vkey] = "undecided"
    return result


def _camps(voices: Sequence[VoiceStance]) -> tuple[Dict[StanceClass, int], int]:
    """Lagerverteilung und Zahl der positionierten Stimmen.

    Positioniert ist eine Stimme mit mindestens einem Beitrag ``in_favour``
    oder ``opposed`` oder einer Interviewhaltung ``in_favour`` oder ``opposed``;
    alle anderen zählen im Lager ``undecided``.
    """
    camp_distribution: Dict[StanceClass, int] = {"in_favour": 0, "opposed": 0, "undecided": 0}
    voices_positioned = 0
    for voice in voices:
        all_classes = list(voice.contribution_classes)
        if voice.interview_class:
            all_classes.append(voice.interview_class)
        positioned = any(stance != "undecided" for stance in all_classes)
        if positioned:
            voices_positioned += 1
            camp_distribution[_camp_of(all_classes)] += 1
        else:
            camp_distribution["undecided"] += 1
    return camp_distribution, voices_positioned


def _compute_position_shifts(
    voices: Sequence[VoiceStance],
    contributions: Sequence[ClassifiedContribution],
) -> List[PositionShift]:
    """Positionswechsel: Startklasse weicht von der Endklasse im letzten Drittel ab."""
    if not contributions:
        return []
    max_round = max((c.round_num for c in contributions), default=0)
    cutoff = max_round * (2.0 / 3.0)

    by_agent_id: Dict[int, List[ClassifiedContribution]] = {}
    for c in contributions:
        by_agent_id.setdefault(c.agent_id, []).append(c)

    shifts: List[PositionShift] = []
    for voice in voices:
        try:
            agent_id = int(voice.voice_key.split(":")[-1])
        except (ValueError, IndexError):
            continue

        agent_contributions = sorted(by_agent_id.get(agent_id, []), key=lambda c: c.round_num)
        late_contributions = [c for c in agent_contributions if c.round_num > cutoff]
        late_classes = [c.stance_class for c in late_contributions]
        in_favour_count = sum(1 for s in late_classes if s == "in_favour")
        opposed_count = sum(1 for s in late_classes if s == "opposed")

        if in_favour_count > opposed_count:
            end_class: StanceClass = "in_favour"
        elif opposed_count > in_favour_count:
            end_class = "opposed"
        else:
            end_class = "undecided"

        if voice.start_class != end_class and end_class in ("in_favour", "opposed"):
            matching = [c for c in agent_contributions if c.stance_class == end_class]
            if matching:
                first = matching[0]
                shifts.append(
                    PositionShift(
                        voice_key=voice.voice_key,
                        agent_name=voice.agent_name,
                        from_class=voice.start_class,
                        to_class=end_class,
                        first_round=first.round_num,
                        evidence_producer_key=first.producer_key,
                    )
                )
    return shifts


def _compute_stance_deviations(
    voices: Sequence[VoiceStance],
    contributions: Sequence[ClassifiedContribution],
    position_shift_voice_keys: set[str],
) -> List[StanceDeviation]:
    """Haltungsabweichungen zwischen Start und Interview ohne passenden Beitrag."""
    by_agent_id: Dict[int, List[ClassifiedContribution]] = {}
    for c in contributions:
        by_agent_id.setdefault(c.agent_id, []).append(c)

    deviations: List[StanceDeviation] = []
    for voice in voices:
        if voice.voice_key in position_shift_voice_keys:
            continue
        if voice.interview_class is None:
            continue
        if voice.interview_class == voice.start_class:
            continue

        try:
            agent_id = int(voice.voice_key.split(":")[-1])
        except (ValueError, IndexError):
            continue

        agent_contributions = by_agent_id.get(agent_id, [])
        has_matching_contrib = any(
            c.stance_class == voice.interview_class for c in agent_contributions
        )
        if not has_matching_contrib:
            deviations.append(
                StanceDeviation(
                    voice_key=voice.voice_key,
                    agent_name=voice.agent_name,
                    start_class=voice.start_class,
                    interview_class=voice.interview_class,
                )
            )
    return deviations


_SUPPORTING_ACTION_TYPES = frozenset({"LIKE_POST", "LIKE_COMMENT", "REPOST", "QUOTE_POST"})


def _compute_late_end_classes(
    voices: Sequence[VoiceStance],
    contributions: Sequence[ClassifiedContribution],
) -> Dict[str, StanceClass]:
    """Bestimmt die Haltung je Stimme im letzten Drittel der Runden."""
    max_round = max((c.round_num for c in contributions), default=0)
    cutoff = max_round * (2.0 / 3.0)

    by_agent_id: Dict[int, List[ClassifiedContribution]] = {}
    for c in contributions:
        if c.round_num > cutoff:
            by_agent_id.setdefault(c.agent_id, []).append(c)

    end_classes: Dict[str, StanceClass] = {}
    for voice in voices:
        try:
            aid = int(voice.voice_key.split(":")[-1])
        except (ValueError, IndexError):
            continue
        late_classes = [c.stance_class for c in by_agent_id.get(aid, [])]
        in_favour_count = sum(1 for s in late_classes if s == "in_favour")
        opposed_count = sum(1 for s in late_classes if s == "opposed")
        if in_favour_count > opposed_count:
            end_classes[voice.voice_key] = "in_favour"
        elif opposed_count > in_favour_count:
            end_classes[voice.voice_key] = "opposed"
        else:
            end_classes[voice.voice_key] = "undecided"
    return end_classes


def _resolve_supporting_interaction_pair(
    action: Mapping[str, Any],
    camp_voice_keys: Mapping[str, VoiceStance],
    name_to_id: Dict[str, int],
    comment_to_author: Dict[int, int],
) -> Optional[tuple[str, str]]:
    """Löst Quelle und Ziel einer zustimmenden Aktion innerhalb desselben Lagers auf."""
    from ..network_analytics import _extract_target_agent

    atype = str(action.get("action_type") or "").upper()
    if atype not in _SUPPORTING_ACTION_TYPES:
        return None
    src = action.get("agent_id")
    if src is None:
        return None
    try:
        src_id = int(src)
    except (TypeError, ValueError):
        return None
    src_key = f"agent:{src_id}"
    if src_key not in camp_voice_keys:
        return None

    tgt_id = _extract_target_agent(dict(action), name_to_id, comment_to_author)
    if tgt_id is None or tgt_id == src_id:
        return None
    tgt_key = f"agent:{tgt_id}"
    if tgt_key not in camp_voice_keys:
        return None
    return (min(src_key, tgt_key), max(src_key, tgt_key))


def _build_camp_interaction_graph(
    camp_voice_keys: Mapping[str, VoiceStance],
    actions_list: Sequence[Dict[str, Any]],
    name_to_id: Dict[str, int],
    comment_to_author: Dict[int, int],
) -> tuple[Any, Dict[tuple[str, str], int], Dict[tuple[str, str], List[str]]]:
    """Baut den Interaktionsgraphen eines Lagers samt Kantenzählern und Belegschlüsseln."""
    import networkx as nx

    graph = nx.Graph()
    for vkey in camp_voice_keys:
        graph.add_node(vkey)

    edge_interactions: Dict[tuple[str, str], int] = Counter()
    edge_producers: Dict[tuple[str, str], List[str]] = {}

    for action in actions_list:
        edge = _resolve_supporting_interaction_pair(
            action, camp_voice_keys, name_to_id, comment_to_author
        )
        if edge is None:
            continue
        graph.add_edge(edge[0], edge[1])
        edge_interactions[edge] += 1
        pkey = str(build_action_evidence_item(action).get("producer_key") or "")
        if pkey:
            producers = edge_producers.setdefault(edge, [])
            if pkey not in producers:
                producers.append(pkey)

    return graph, edge_interactions, edge_producers


def _aggregate_component_interactions(
    comp: set[str],
    edge_interactions: Mapping[tuple[str, str], int],
    edge_producers: Mapping[tuple[str, str], List[str]],
) -> tuple[int, List[str]]:
    """Summiert Interaktionen und eindeutige Belegschlüssel einer Zusammenhangskomponente."""
    total_interactions = 0
    comp_producers: List[str] = []
    sorted_nodes = sorted(comp)
    for idx, u in enumerate(sorted_nodes):
        for v in sorted_nodes[idx + 1 :]:
            edge = (u, v)
            total_interactions += edge_interactions.get(edge, 0)
            for pkey in edge_producers.get(edge, []):
                if pkey not in comp_producers:
                    comp_producers.append(pkey)
    return total_interactions, comp_producers


def _extract_camp_coalitions(
    target_stance: StanceClass,
    camp_voice_keys: Mapping[str, VoiceStance],
    actions_list: Sequence[Dict[str, Any]],
    name_to_id: Dict[str, int],
    comment_to_author: Dict[int, int],
) -> List[Coalition]:
    """Extrahiert Koalitionen für ein einzelnes Lager."""
    import networkx as nx

    if len(camp_voice_keys) < 2:
        return []

    graph, edge_interactions, edge_producers = _build_camp_interaction_graph(
        camp_voice_keys, actions_list, name_to_id, comment_to_author
    )

    coalitions: List[Coalition] = []
    for comp in nx.connected_components(graph):
        if len(comp) < 2:
            continue
        role_families_set = {
            family for vkey in comp if (family := camp_voice_keys[vkey].role_family)
        }
        if len(role_families_set) < 2:
            continue

        sorted_members = sorted(
            comp,
            key=lambda k: int(k.split(":")[-1]) if k.split(":")[-1].isdigit() else k,
        )
        total_interactions, comp_producers = _aggregate_component_interactions(
            comp, edge_interactions, edge_producers
        )
        coalitions.append(
            Coalition(
                stance_class=target_stance,
                members=sorted_members,
                role_families=sorted(role_families_set),
                supporting_interactions=total_interactions,
                example_producer_keys=comp_producers[:5],
            )
        )
    return coalitions


def _compute_coalitions(
    voices: Sequence[VoiceStance],
    contributions: Sequence[ClassifiedContribution],
    actions: Sequence[Mapping[str, Any]],
) -> List[Coalition]:
    """Koalitionen: Akteure gleicher Endklasse mit zustimmenden Interaktionen über Rollenfamilien."""
    if not actions:
        return []

    from ..network_analytics import _build_lookup_indexes

    end_classes = _compute_late_end_classes(voices, contributions)
    actions_list = [dict(a) for a in actions]
    name_to_id, comment_to_author = _build_lookup_indexes(actions_list)

    coalitions: List[Coalition] = []
    for target_stance in ("in_favour", "opposed"):
        camp_voice_keys = {
            voice.voice_key: voice
            for voice in voices
            if end_classes.get(voice.voice_key) == target_stance
        }
        coalitions.extend(
            _extract_camp_coalitions(
                target_stance, camp_voice_keys, actions_list, name_to_id, comment_to_author
            )
        )

    coalitions.sort(
        key=lambda c: (
            0 if c.stance_class == "in_favour" else 1,
            -c.supporting_interactions,
            c.members,
        )
    )
    return coalitions


def build_stance_analysis(
    simulation_id: str,
    simulation_config: Optional[Mapping[str, Any]],
    actions: Sequence[Mapping[str, Any]],
    interview_stances: Optional[Mapping[str, StanceClass]],
    llm_client: Any,
) -> StanceAnalysis:
    """Baut Positionierungsquote und Lagerverteilung eines Laufs."""
    statement = _contested_statement(simulation_config)
    if statement is None:
        return StanceAnalysis(applicable=False)

    contributions = text_contributions(dict(action) for action in actions)
    classes = classify_contributions(llm_client, statement, contributions)

    classified = _classified_contributions(contributions, classes)
    voices = _voices(simulation_config, classified)

    if interview_stances:
        for voice in voices:
            if voice.voice_key in interview_stances:
                voice.interview_class = interview_stances[voice.voice_key]

    camp_distribution, voices_positioned = _camps(voices)
    shifts = _compute_position_shifts(voices, classified)
    shift_keys = {s.voice_key for s in shifts}
    deviations = _compute_stance_deviations(voices, classified, shift_keys)
    coalitions = _compute_coalitions(voices, classified, actions)

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
        position_shifts=shifts,
        stance_deviations=deviations,
        coalitions=coalitions,
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


def update_stance_analysis_with_interviews(
    report_folder: str,
    interview_items: Sequence[Mapping[str, Any]],
    actions: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Optional[StanceAnalysis]:
    """Aktualisiert die Haltungsanalyse nach Abschluss der Interviews."""
    analysis = load_stance_analysis(report_folder)
    if analysis is None or not analysis.applicable:
        return analysis

    interview_classes = _compute_interview_classes(interview_items)
    if not interview_classes:
        return analysis

    for voice in analysis.voices:
        if voice.voice_key in interview_classes:
            voice.interview_class = interview_classes[voice.voice_key]

    camp_distribution, voices_positioned = _camps(analysis.voices)
    analysis.camp_distribution = camp_distribution
    analysis.voices_positioned = voices_positioned
    analysis.positioning_ratio = (
        voices_positioned / analysis.voices_total if analysis.voices_total else None
    )

    shifts = _compute_position_shifts(analysis.voices, analysis.contributions)
    analysis.position_shifts = shifts
    shift_keys = {s.voice_key for s in shifts}
    analysis.stance_deviations = _compute_stance_deviations(
        analysis.voices, analysis.contributions, shift_keys
    )

    if actions is not None:
        analysis.coalitions = _compute_coalitions(
            analysis.voices, analysis.contributions, actions
        )

    save_stance_analysis(report_folder, analysis)
    return analysis


def voices_match_config(
    analysis: StanceAnalysis, simulation_config: Optional[Mapping[str, Any]]
) -> bool:
    """Ob die gespeicherten Stimmen zur (angeglichenen) Konfiguration gehören.

    Issue #1778: Eine Analyse aus der Zeit vor der Angleichung der
    Agenten-Nummern trägt je ``voice_key`` Namen und Starthaltung eines
    anderen Agenten. Ein Resume darf sie dann nicht übernehmen.
    """
    expected = {
        voice.voice_key: (voice.agent_name, voice.start_class)
        for voice in _voices(simulation_config, [])
    }
    stored = {
        voice.voice_key: (voice.agent_name, voice.start_class) for voice in analysis.voices
    }
    return stored == expected


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


def read_stance_analysis(report_folder: str) -> Optional[StanceAnalysis]:
    """Strenges Lesen für den Lese-Endpunkt (Issue #1804).

    ``None``, wenn keine Datei vorliegt; ``ArtifactContractViolation``, wenn sie
    den Vertrag verletzt. ``load_stance_analysis`` bleibt der tolerante
    Resume-Pfad.
    """
    return read_contract_artifact(
        os.path.join(report_folder, STANCE_ANALYSIS_FILENAME), StanceAnalysis
    )


def save_stance_analysis(report_folder: str, analysis: StanceAnalysis) -> str:
    """Schreibt die Analyse atomar als ``stance_analysis.json`` und liefert den Pfad."""
    path = os.path.join(report_folder, STANCE_ANALYSIS_FILENAME)
    write_json_atomic(path, analysis.model_dump(mode="json"))
    return path


__all__ = [
    "STANCE_ANALYSIS_FILENAME",
    "load_stance_analysis",
    "read_stance_analysis",
    "StanceBatchResponse",
    "build_stance_analysis",
    "classify_contributions",
    "save_stance_analysis",
    "update_stance_analysis_with_interviews",
    "PositionShift",
    "StanceDeviation",
    "Coalition",
]
