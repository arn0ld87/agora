"""Graph-abgeleitete Stance und Startpost-Abgleich (Issue #1759, A6).

Im Referenzlauf entstand die Stance eines Agenten aus einem LLM-Batch, der keine
Graph-Kanten sah, und die Startposts wurden nur nach Typ zugeordnet — ein
Agent mit ``opposing`` bekam einen Pro-Startpost. Dieses Modul schließt beides:

* Hat eine Entität eine ausgehende Kante auf einen Knoten eines als
  ``contested_topic`` deklarierten Typs, bestimmt diese Kante die Stance.
* Die Polarität wird **nicht** aus festen Kantennamen (``SUPPORTS``/``OPPOSES``)
  geraten, sondern aus Kantenname *und* ``fact`` relativ zum Topic-Knoten
  gelesen. Ist sie nicht eindeutig (keine Wertung, gemischte Wertung,
  Verneinung, widersprüchliche Kanten), bleibt die LLM-Stance und der Fall wird
  protokolliert.
* Kein Startpost darf gegen die Stance seines Absenders laufen; eine im Graph
  belegte, aber von keinem Agenten vertretene Position wird sichtbar gemeldet.

Ohne Topic-Typ in der Ontologie ist jede Funktion hier ein No-op — es gilt das
bisherige Verhalten.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..contracts.ontology_type_contract import contested_topic_type_names
from ..contracts.pipeline_degradation_contract import DegradationKind, DegradationSeverity
from ..utils.logger import get_logger
from .degradation_collector import DegradationCollector
from .entity_reader import EntityNode
from .simulation_config_models import AgentActivityConfig, EventConfig

logger = get_logger("agora.simulation_config")

STANCE_SUPPORTIVE = "supportive"
STANCE_OPPOSING = "opposing"
_POLAR_STANCES = (STANCE_SUPPORTIVE, STANCE_OPPOSING)

SYNTHETIC_SKEPTIC_PREFIX = "synthetic-skeptic-"

_EDGE_FACT_LIMIT = 6
_EDGE_FACT_LENGTH = 200

# Wertende Wortstämme (DE/EN) am Wortanfang. Bewusst eng gehalten: ein
# unbekanntes Verb ist "keine Wertung" und führt zur LLM-Stance, nie zu einer
# geratenen Polarität.
_SUPPORT_CUES = re.compile(
    r"\b(?:support|endors|favou?r|advocat|champion|welcom|approv|befürwort|"
    r"unterstütz|begrüß|zustimm|setzt sich für)\w*",
    re.IGNORECASE,
)
_OPPOSE_CUES = re.compile(
    r"\b(?:oppos|reject|criticis|criticiz|condemn|protest|resist|disapprov|"
    r"ablehn|lehnt|kritisier|widerspr|widersetz|wendet sich gegen|"
    r"richtet sich gegen|kämpft gegen|against)\w*",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(?:not|no|never|without|nicht|kein\w*|nie|niemals|ohne)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GraphStanceDerivation:
    """Ergebnis der Stance-Ableitung für eine Entität."""

    stance: Optional[str]
    topic_edge_count: int


@dataclass(frozen=True)
class PostStanceConflict:
    """Startpost gegen die Stance seines Absenders."""

    post_index: int
    original_agent_id: int
    new_agent_id: Optional[int]
    post_stance: str
    agent_stance: str


def resolve_contested_topic_types(project_id: str) -> frozenset[str]:
    """Topic-Typen der Ontologie eines Projekts (leer ohne Projekt/Ontologie)."""
    from ..models.project import ProjectManager

    try:
        project = ProjectManager.get_project(project_id)
    except Exception as exc:  # noqa: BLE001 — Lesefehler darf die Config-Generierung nicht kippen
        logger.warning(
            "Topic-Typen nicht lesbar (project_id=%s): %s — Stance ohne Graph-Ableitung",
            project_id,
            exc,
        )
        return frozenset()
    if project is None:
        return frozenset()
    return contested_topic_type_names(project.ontology)


def _topic_node_uuids(entity: EntityNode, topic_types: Collection[str]) -> set[str]:
    return {
        str(node.get("uuid"))
        for node in entity.related_nodes
        if node.get("uuid") and any(label in topic_types for label in node.get("labels") or [])
    }


def _topic_name_by_uuid(entity: EntityNode, topic_types: Collection[str]) -> Dict[str, str]:
    uuids = _topic_node_uuids(entity, topic_types)
    return {
        str(node["uuid"]): str(node.get("name", ""))
        for node in entity.related_nodes
        if str(node.get("uuid")) in uuids
    }


def _edge_polarity(edge: Dict[str, Any]) -> Optional[str]:
    """Polarität einer Kante relativ zum Topic-Knoten, oder ``None`` bei Unklarheit."""
    text = f"{edge.get('edge_name', '')} {edge.get('fact', '')}".replace("_", " ")
    supportive = bool(_SUPPORT_CUES.search(text))
    opposing = bool(_OPPOSE_CUES.search(text))
    if supportive == opposing:
        return None
    if _NEGATION.search(text):
        return None
    return STANCE_SUPPORTIVE if supportive else STANCE_OPPOSING


def _outgoing_topic_edges(entity: EntityNode, topic_types: Collection[str]) -> List[Dict[str, Any]]:
    topic_uuids = _topic_node_uuids(entity, topic_types)
    return [
        edge
        for edge in entity.related_edges
        if edge.get("direction") == "outgoing" and str(edge.get("target_node_uuid")) in topic_uuids
    ]


def derive_graph_stance(entity: EntityNode, topic_types: Collection[str]) -> GraphStanceDerivation:
    """Leitet die Stance einer Entität aus ihren Kanten auf Topic-Knoten ab."""
    if not topic_types:
        return GraphStanceDerivation(stance=None, topic_edge_count=0)
    edges = _outgoing_topic_edges(entity, topic_types)
    polarities = {_edge_polarity(edge) for edge in edges}
    polarities.discard(None)
    stance = next(iter(polarities)) if len(polarities) == 1 else None
    return GraphStanceDerivation(stance=stance, topic_edge_count=len(edges))


def resolve_stance(entity: EntityNode, llm_stance: str, topic_types: Collection[str]) -> str:
    """Graph-Stance vor LLM-Stance; bei Unklarheit bleibt die LLM-Stance."""
    derivation = derive_graph_stance(entity, topic_types)
    if derivation.stance is None:
        if derivation.topic_edge_count:
            logger.info(
                "Graph-Stance uneindeutig (entity=%s, topic_edges=%d) — LLM-Stance '%s' bleibt",
                entity.name,
                derivation.topic_edge_count,
                llm_stance,
            )
        return llm_stance
    if derivation.stance != llm_stance:
        logger.info(
            "Graph-Stance überschreibt LLM-Stance (entity=%s): '%s' -> '%s'",
            entity.name,
            llm_stance,
            derivation.stance,
        )
    return derivation.stance


def graph_edge_facts(entity: EntityNode, topic_types: Collection[str]) -> List[Dict[str, str]]:
    """Kantenfakten für den Batch-Prompt; Kanten auf Topic-Knoten zuerst."""
    topic_names = _topic_name_by_uuid(entity, topic_types)
    facts: List[Dict[str, str]] = []
    for edge in entity.related_edges:
        other = str(edge.get("target_node_uuid") or edge.get("source_node_uuid") or "")
        item = {
            "direction": str(edge.get("direction", "")),
            "edge_name": str(edge.get("edge_name", "")),
            "fact": str(edge.get("fact", ""))[:_EDGE_FACT_LENGTH],
        }
        if other in topic_names:
            item["topic"] = topic_names[other]
        facts.append(item)
    facts.sort(key=lambda item: "topic" not in item)
    return facts[:_EDGE_FACT_LIMIT]


def _is_synthetic(agent: AgentActivityConfig) -> bool:
    return agent.entity_uuid.startswith(SYNTHETIC_SKEPTIC_PREFIX)


def warn_unrepresented_positions(
    entities: Iterable[EntityNode],
    agents: Iterable[AgentActivityConfig],
    topic_types: Collection[str],
    degradations: Optional[DegradationCollector] = None,
) -> List[str]:
    """Meldet im Graph belegte Positionen, die kein (echter) Agent vertritt.

    Synthetische Skeptiker aus der Quotenregel zählen nicht: sie sind nicht
    aus dem Graph belegt und würden eine fehlende ``opposing``-Position
    sonst verdecken.
    """
    if not topic_types:
        return []
    evidenced: Dict[str, List[str]] = {}
    for entity in entities:
        stance = derive_graph_stance(entity, topic_types).stance
        if stance is not None:
            evidenced.setdefault(stance, []).append(entity.name)
    held = {agent.stance for agent in agents if not _is_synthetic(agent)}
    warnings: List[str] = []
    for stance in _POLAR_STANCES:
        names = evidenced.get(stance)
        if not names or stance in held:
            continue
        message = (
            f"Im Graph belegte Position '{stance}' ({', '.join(sorted(names))}) "
            "wird von keinem Agenten vertreten."
        )
        logger.warning("Stance-Abgleich: %s", message)
        if degradations is not None:
            degradations.record(
                DegradationKind.STANCE_POSITION_UNREPRESENTED,
                DegradationSeverity.WARNING,
                message,
                context={"stance": stance, "evidenced_entities": len(names)},
            )
        warnings.append(message)
    return warnings


def _replacement_candidates(
    agents: List[AgentActivityConfig], stance: str, entity_type: str
) -> List[AgentActivityConfig]:
    matching = [agent for agent in agents if agent.stance == stance]
    return sorted(
        matching,
        key=lambda a: (
            _is_synthetic(a),
            a.entity_type.strip().lower() != entity_type.strip().lower(),
            -a.influence_weight,
            a.agent_id,
        ),
    )


def _post_conflict(
    post: Dict[str, Any], agents_by_id: Dict[int, AgentActivityConfig]
) -> Optional[tuple[str, AgentActivityConfig]]:
    """(Post-Stance, Absender), wenn der Startpost der Absender-Stance widerspricht."""
    post_stance = post.get("stance")
    sender = agents_by_id.get(post.get("poster_agent_id"))
    if post_stance not in _POLAR_STANCES or sender is None:
        return None
    if sender.stance in _POLAR_STANCES and sender.stance != post_stance:
        return post_stance, sender
    return None


def _pick_replacement(
    candidates: List[AgentActivityConfig], load: Counter[int]
) -> Optional[AgentActivityConfig]:
    if not candidates:
        return None
    return min(candidates, key=lambda a: (load[a.agent_id], candidates.index(a)))


def align_initial_posts_with_stance(
    event_config: EventConfig,
    agents: List[AgentActivityConfig],
    topic_types: Collection[str],
    degradations: Optional[DegradationCollector] = None,
) -> List[str]:
    """Legt Startposts, die der Stance ihres Absenders widersprechen, um.

    Maßgeblich ist die vom Event-Config-LLM angegebene ``stance`` des Posts
    (Position zum Streitgegenstand). Ein Post ohne Angabe wird nicht geprüft.
    Gibt es keinen Agenten mit der passenden Stance, bleibt der Absender und
    der Konflikt wird sichtbar gemeldet.
    """
    if not topic_types or not event_config.initial_posts:
        return []
    agents_by_id = {agent.agent_id: agent for agent in agents}
    load: Counter[int] = Counter(
        post.get("poster_agent_id") for post in event_config.initial_posts
    )
    warnings: List[str] = []
    for index, post in enumerate(event_config.initial_posts):
        conflict = _post_conflict(post, agents_by_id)
        if conflict is None:
            continue
        post_stance, sender = conflict
        replacement = _pick_replacement(
            _replacement_candidates(agents, post_stance, sender.entity_type), load
        )
        result = PostStanceConflict(
            post_index=index,
            original_agent_id=sender.agent_id,
            new_agent_id=replacement.agent_id if replacement else None,
            post_stance=post_stance,
            agent_stance=sender.stance,
        )
        if replacement is not None:
            post["poster_agent_id"] = replacement.agent_id
            load[replacement.agent_id] += 1
            logger.info(
                "Startpost %d gegen Stance des Absenders (agent_id=%d '%s', Post '%s') "
                "-> umgelegt auf agent_id=%d",
                index,
                sender.agent_id,
                sender.stance,
                post_stance,
                replacement.agent_id,
            )
            continue
        message = _unresolved_message(result)
        logger.warning("Stance-Abgleich: %s", message)
        if degradations is not None:
            degradations.record(
                DegradationKind.INITIAL_POST_STANCE_CONFLICT,
                DegradationSeverity.WARNING,
                message,
                context={"post_index": index, "agent_id": sender.agent_id},
            )
        warnings.append(message)
    return warnings


def _unresolved_message(conflict: PostStanceConflict) -> str:
    return (
        f"Startpost {conflict.post_index} ('{conflict.post_stance}') läuft gegen die Stance "
        f"seines Absenders agent_id={conflict.original_agent_id} ('{conflict.agent_stance}'); "
        "kein Agent mit passender Stance verfügbar."
    )
