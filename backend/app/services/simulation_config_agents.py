"""Implementation helpers extracted from SimulationConfigGenerator.

The public compatibility surface remains app.services.simulation_config_generator.
"""

from __future__ import annotations

import json
import math
from contextvars import copy_context
from typing import Any, Dict, List, Optional


from ..utils.logger import get_logger
from .entity_reader import EntityNode
from .simulation_activity_policy import (
    enforce_active_hours_floor,
    enforce_activity_level_floor,
)
from .simulation_config_models import (
    AgentActivityConfig,
)
from .simulation_config_schemas import (
    AgentConfigsResponse,
)
from .simulation_stance_graph import graph_edge_facts, resolve_stance

logger = get_logger("agora.simulation_config")

# Responsibility group: agents

def _generate_agent_configs_parallel(self, context: str, entities: List[EntityNode], batch_ranges: List[tuple[int, int]], simulation_requirement: str, contested_statement: Optional[str] = None) -> List[AgentActivityConfig]:
    """Führt die Agent-Config-Batches parallel statt sequentiell aus.

        Perf-Fix: ``batch_ranges`` sind disjunkte, vorab berechnete
        ``[start_idx, end_idx)``-Fenster über ``entities``. Jeder Batch liest
        nur aus dem gemeinsamen, unveränderlichen ``context`` und seinem
        eigenen Entity-Ausschnitt — keine geteilte veränderliche Struktur,
        daher sicher parallelisierbar. Reihenfolge und Entity-Zuordnung
        bleiben identisch zur sequentiellen Variante, weil ``map`` die
        Ergebnisse in Eingabereihenfolge liefert, unabhängig von der
        tatsächlichen Fertigstellungsreihenfolge der Batches.

        gevent-Kompatibilität: Produktionsserver läuft unter
        ``gunicorn -k gevent`` (``backend/wsgi.py`` patcht alle Sockets).
        ``ThreadPoolExecutor`` auf gevent-gepatchten Sockets reißt
        Verbindungen ab, weil OS-Threads nicht den gevent-Hub des
        aufrufenden Greenlets teilen — genau das Muster aus
        ``oasis_profile_generator.generate_profiles_from_entities``. Unter
        gevent daher der kooperative ``gevent.pool.Pool``, sonst
        ``ThreadPoolExecutor``.
        """
    # Ohne Streitfrage bleibt der Batch-Aufruf exakt der bisherige (#1778).
    contested_kwargs: Dict[str, Any] = {'contested_statement': contested_statement} if contested_statement else {}
    if len(batch_ranges) == 1:
        start_idx, end_idx = batch_ranges[0]
        return self._generate_agent_configs_batch(context=context, entities=entities[start_idx:end_idx], start_idx=start_idx, simulation_requirement=simulation_requirement, **contested_kwargs)

    def run_batch(batch_range: tuple[int, int]) -> List[AgentActivityConfig]:
        start_idx, end_idx = batch_range
        return self._generate_agent_configs_batch(context=context, entities=entities[start_idx:end_idx], start_idx=start_idx, simulation_requirement=simulation_requirement, **contested_kwargs)
    try:
        from gevent import monkey
    except ImportError:
        is_gevent = False
    else:
        is_gevent = monkey.is_module_patched('socket')
    pool_size = min(len(batch_ranges), self.MAX_PARALLEL_AGENT_BATCHES)
    remaining_budget = self.llm_client.remaining_hard_call_budget()
    if remaining_budget is not None:
        pool_size = min(pool_size, max(1, remaining_budget))
    if is_gevent:
        logger.info('Gevent detected: using cooperative Pool for %d parallel agent-config batches', len(batch_ranges))
        from gevent.pool import Pool
        pool = Pool(pool_size)
        credential_context = copy_context()
        try:
            batch_results = list(pool.map(lambda item: credential_context.copy().run(run_batch, item), batch_ranges))
        finally:
            pool.join()
    else:
        from concurrent.futures import ThreadPoolExecutor
        logger.info('No gevent monkey-patching detected: using ThreadPoolExecutor for %d parallel agent-config batches', len(batch_ranges))
        credential_context = copy_context()
        with ThreadPoolExecutor(max_workers=pool_size) as executor:
            batch_results = list(executor.map(lambda item: credential_context.copy().run(run_batch, item), batch_ranges))
    all_agent_configs: List[AgentActivityConfig] = []
    for batch_configs in batch_results:
        all_agent_configs.extend(batch_configs)
    return all_agent_configs


_GRAPH_EDGES_PROMPT_HINT = (
    '\n\n## Graph Edges\nEach entity lists `graph_edges` (edge_name, fact; `topic` is set when the edge points at the contested topic of this run). '
    'Set `stance` consistently with what these facts say about the entity\'s position on the contested topic; do not invent a position the facts do not support.'
)


def _topic_types_of(self) -> frozenset:
    """Topic-Typen des Laufs; leer, wenn der Generator keine gesetzt hat."""
    value = getattr(self, '_contested_topic_types', None)
    return value if isinstance(value, frozenset) else frozenset()


def _resolve_agent_stance(entity: EntityNode, cfg: Dict[str, Any], topic_types: frozenset) -> str:
    """Graph-Stance (Kante auf Topic-Knoten) vor LLM-/Regel-Stance (Issue #1759, A6)."""
    return resolve_stance(entity, cfg.get('stance', 'neutral'), topic_types)


def _contested_question_prompt_block(contested_statement: Optional[str]) -> str:
    """Prompt-Abschnitt, der Haltung und Vorzeichen an die Streitfrage bindet.

    Leerstring ohne Streitfrage: der Prompt bleibt dann unverändert.
    """
    if not contested_statement:
        return ''
    return (
        f'Contested question: {contested_statement}\n'
        'For every entity, `stance` and `sentiment_bias` refer ONLY to this contested question:\n'
        '- "supportive" and a positive sentiment_bias mean: the entity wants the contested question to come true.\n'
        '- "opposing" and a negative sentiment_bias mean: the entity wants to prevent it.\n'
        '- "neutral" means genuinely undecided. "observer" is reserved for media and pure reporting entities.\n'
        '- stance and the sign of sentiment_bias must agree. Never combine "opposing" with a positive sentiment_bias or "supportive" with a negative one.\n'
        '- Entities that are directly affected (employees, patients, residents, their associations, political groups) normally have a position. Do not default them to "neutral" or "observer".\n'
    )


def _align_sentiment_sign(stance: str, sentiment_bias: float) -> float:
    """Bringt das Vorzeichen von ``sentiment_bias`` mit der Haltung in Einklang.

    Die Haltung gewinnt, weil sie nach dem Graph-Abgleich (``resolve_stance``)
    feststeht. Jede Korrektur wird protokolliert.
    """
    if stance == 'opposing' and sentiment_bias > 0:
        aligned = -abs(sentiment_bias)
    elif stance == 'supportive' and sentiment_bias < 0:
        aligned = abs(sentiment_bias)
    else:
        return sentiment_bias
    logger.info('sentiment_bias %s passt nicht zur Haltung %s, korrigiert auf %s', sentiment_bias, stance, aligned)
    return aligned


def _generate_agent_configs_batch(self, context: str, entities: List[EntityNode], start_idx: int, simulation_requirement: str, contested_statement: Optional[str] = None) -> List[AgentActivityConfig]:
    """Generate agent configurations in batch"""
    entity_list = []
    summary_len = self.AGENT_SUMMARY_LENGTH
    topic_types = _topic_types_of(self)
    for i, e in enumerate(entities):
        entry = {'agent_id': start_idx + i, 'entity_name': e.name, 'entity_type': e.get_entity_type() or 'Unknown', 'summary': e.summary[:summary_len] if e.summary else ''}
        if topic_types:
            entry['graph_edges'] = graph_edge_facts(e, topic_types)
        entity_list.append(entry)
    prompt = f'Based on the following information, generate social media activity configuration for each entity.\n\nSimulation Requirements: {simulation_requirement}\n{_contested_question_prompt_block(contested_statement)}\n## Entity List\n```json\n{json.dumps(entity_list, ensure_ascii=False, indent=2)}\n```\n\n## Task\nGenerate activity configuration for each entity, noting:\n- **Time follows DACH / Europe-Berlin habits**: Almost no activity 0-5am, strongest after-work activity 18-22\n- **activity_level has a hard floor of 0.5** (values below 0.5 are raised automatically) — use it to differentiate degree of engagement above that floor, not to make an entity inactive\n- **Official institutions** (University/GovernmentAgency): Lower engagement within the floor (0.5-0.6), active during work hours (9-17), slow response (60-240 min), high influence (2.5-3.0)\n- **Media** (MediaOutlet): Medium-high activity (0.6-0.8), active all day (8-23), fast response (5-30 min), high influence (2.0-2.5)\n- **Individuals** (Student/Person/Alumni): High activity (0.7-0.9), mainly evening activity (18-23), fast response (1-15 min), low influence (0.8-1.2)\n- **Public figures/Experts**: Medium-high activity (0.6-0.8), medium-high influence (1.5-2.0)\n- **active_hours must cover at least 06:00-23:59** (hours outside that range are added automatically) — narrow it only within that window, never to fewer hours overall\n\nReturn JSON format (no markdown):\n{{\n    "agent_configs": [\n        {{\n            "agent_id": <must match input>,\n            "activity_level": <0.5-1.0>,\n            "posts_per_hour": <posting frequency>,\n            "comments_per_hour": <comment frequency>,\n            "active_hours": [<active hours list, must include 6-23, consider DACH / Europe-Berlin habits>],\n            "response_delay_min": <minimum response delay minutes>,\n            "response_delay_max": <maximum response delay minutes>,\n            "sentiment_bias": <-1.0 to 1.0>,\n            "stance": "<supportive/opposing/neutral/observer>",\n            "influence_weight": <influence weight>\n        }},\n        ...\n    ]\n}}'
    if topic_types:
        prompt += _GRAPH_EDGES_PROMPT_HINT
    system_prompt = 'You are a social media behavior analysis expert. Return pure JSON and use DACH / Europe-Berlin activity habits by default.'
    try:
        result = self._call_llm_with_retry(prompt, system_prompt, AgentConfigsResponse)
        llm_configs = {cfg['agent_id']: cfg for cfg in result.get('agent_configs', [])}
    except Exception as e:  # noqa: BLE001 — logged and intentionally converted to rule-based fallback
        logger.warning(f'Agent config batch LLM generation failed: {e}, using rule-based generation')
        llm_configs = {}
    configs = []
    for i, entity in enumerate(entities):
        agent_id = start_idx + i
        cfg = llm_configs.get(agent_id, {})
        if not cfg:
            cfg = self._generate_agent_config_by_rule(entity)
        # Issue #1713 Slice S4: dieselbe Untergrenze fuer LLM-Output (cfg aus
        # llm_configs) und Regel-Fallback (cfg aus _generate_agent_config_by_rule)
        # — beide landen hier im selben cfg-Dict, bevor AgentActivityConfig
        # gebaut wird.
        activity_level = enforce_activity_level_floor(cfg.get('activity_level', 0.5))
        active_hours = enforce_active_hours_floor(
            self._coerce_int_list(cfg.get('active_hours'), list(range(9, 23)))
        )
        config = AgentActivityConfig(agent_id=agent_id, entity_uuid=entity.uuid, entity_name=entity.name, entity_type=entity.get_entity_type() or 'Unknown', activity_level=activity_level, posts_per_hour=cfg.get('posts_per_hour', 0.5), comments_per_hour=cfg.get('comments_per_hour', 1.0), active_hours=active_hours, response_delay_min=cfg.get('response_delay_min', 5), response_delay_max=cfg.get('response_delay_max', 60), sentiment_bias=cfg.get('sentiment_bias', 0.0), stance=_resolve_agent_stance(entity, cfg, topic_types), influence_weight=cfg.get('influence_weight', 1.0))
        # Die Vorzeichenregel steht nur im Prompt mit Streitfrage; ohne
        # Streitfrage bleibt der Lauf wie zuvor (Review PR #1780).
        if contested_statement:
            config.sentiment_bias = _align_sentiment_sign(config.stance, config.sentiment_bias)
        configs.append(config)
    return configs


def _skeptics_needed(*, total: int, skeptic_count: int, min_ratio: float) -> int:
    """Kleinste Zahl zusaetzlicher Skeptiker, fuer die die *Endquote* stimmt.

    Die Vorgaengerrechnung ``ceil(total * min_ratio) - skeptic_count`` mass die
    Quote gegen die Ausgangspopulation und uebersah, dass jeder Zusatz die
    Population mitvergroessert: 10 Personas ohne Skeptiker ergaben bei 20 %
    zwei Zusaetze — 2/12 = 16,67 %.

    Gesucht ist stattdessen das kleinste ``k >= 0`` mit::

        (skeptic_count + k) / (total + k) >= min_ratio

    Umgestellt (fuer ``min_ratio < 1``)::

        k >= (min_ratio * total - skeptic_count) / (1 - min_ratio)

    Fuer ``min_ratio >= 1`` existiert kein solches ``k``, solange auch nur eine
    nicht-skeptische Persona im Set steht: Hinzufuegen kann den Anteil gegen 1
    treiben, ihn aber nie erreichen. Dieser Fall behaelt darum bewusst die
    bisherige Best-Effort-Rechnung und wird protokolliert, statt zu schleifen
    oder zu werfen — er kommt im Produktivpfad nicht vor (der einzige Aufrufer
    nutzt den Default 0.2).
    """
    if min_ratio <= 0:
        return 0
    if min_ratio >= 1:
        if skeptic_count >= total:
            return 0
        logger.warning(
            '_ensure_skeptic_quota: min_ratio=%.3f ist durch Hinzufuegen nicht '
            'erreichbar (%d/%d Skeptiker); fuelle best effort auf',
            min_ratio, skeptic_count, total,
        )
        return max(0, math.ceil(total * min_ratio) - skeptic_count)
    needed = (min_ratio * total - skeptic_count) / (1 - min_ratio)
    if needed <= 0:
        return 0
    # Fliesskomma-Rundungsfehler duerfen die Quote nicht um einen Zusatz
    # verfehlen: ``ceil`` auf einen Wert, der rechnerisch exakt ganzzahlig ist,
    # aber als 2.0000000000000004 dasteht, gaebe sonst 3 statt 2 — und
    # umgekehrt kann 1.9999999999999998 zu 2 statt 3 werden. Deshalb wird das
    # Ergebnis anschliessend gegen die Zielungleichung geprueft.
    candidate = math.ceil(round(needed, 9))
    while (skeptic_count + candidate) / (total + candidate) < min_ratio:
        candidate += 1
    while candidate > 0 and (skeptic_count + candidate - 1) / (total + candidate - 1) >= min_ratio:
        candidate -= 1
    return candidate


def _ensure_skeptic_quota(personas: List[AgentActivityConfig], min_ratio: float=0.2) -> List[AgentActivityConfig]:
    """Erzwingt ≥ ``min_ratio`` Skeptiker im Persona-Set.

        Als Skeptiker gilt ein Agent mit ``stance == "opposing"``.
        Falls die Quote nicht erreicht ist, werden synthetische
        AgentActivityConfig-Objekte mit ``stance="opposing"`` und
        einem negativen ``sentiment_bias`` ergänzt, bis die Quote
        erfüllt ist. Die originalen Personas bleiben unverändert.

        Slice 5 (Issue #497): Echo-Chamber-Red-Team.
        """
    if not personas:
        return personas
    total = len(personas)
    skeptic_count = sum(1 for p in personas if getattr(p, 'stance', '') == 'opposing')
    to_add = _skeptics_needed(total=total, skeptic_count=skeptic_count, min_ratio=min_ratio)
    if to_add <= 0:
        return personas
    result = list(personas)
    base_agent_id = max((p.agent_id for p in personas), default=-1) + 1
    for i in range(to_add):
        synthetic = AgentActivityConfig(agent_id=base_agent_id + i, entity_uuid=f'synthetic-skeptic-{base_agent_id + i}', entity_name=f'Skeptiker {base_agent_id + i}', entity_type='Person', activity_level=enforce_activity_level_floor(0.7), posts_per_hour=0.5, comments_per_hour=1.2, active_hours=enforce_active_hours_floor(range(18, 23)), response_delay_min=5, response_delay_max=30, sentiment_bias=-0.5, stance='opposing', influence_weight=1.0)
        result.append(synthetic)
        logger.info('_ensure_skeptic_quota: synthetischen Skeptiker hinzugefügt (agent_id=%d, gesamt-skeptisch=%d/%d)', synthetic.agent_id, skeptic_count + i + 1, total + i + 1)
    return result


def _generate_agent_config_by_rule(self, entity: EntityNode) -> Dict[str, Any]:
    """Generate single agent configuration based on DACH timing rules."""
    entity_type = (entity.get_entity_type() or 'Unknown').lower()
    if entity_type in ['university', 'governmentagency', 'ngo']:
        return {'activity_level': 0.2, 'posts_per_hour': 0.1, 'comments_per_hour': 0.05, 'active_hours': list(range(9, 18)), 'response_delay_min': 60, 'response_delay_max': 240, 'sentiment_bias': 0.0, 'stance': 'neutral', 'influence_weight': 3.0}
    elif entity_type in ['mediaoutlet']:
        return {'activity_level': 0.5, 'posts_per_hour': 0.8, 'comments_per_hour': 0.3, 'active_hours': list(range(7, 24)), 'response_delay_min': 5, 'response_delay_max': 30, 'sentiment_bias': 0.0, 'stance': 'observer', 'influence_weight': 2.5}
    elif entity_type in ['professor', 'expert', 'official']:
        return {'activity_level': 0.4, 'posts_per_hour': 0.3, 'comments_per_hour': 0.5, 'active_hours': list(range(8, 22)), 'response_delay_min': 15, 'response_delay_max': 90, 'sentiment_bias': 0.0, 'stance': 'neutral', 'influence_weight': 2.0}
    elif entity_type in ['student']:
        return {'activity_level': 0.8, 'posts_per_hour': 0.6, 'comments_per_hour': 1.5, 'active_hours': [8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23], 'response_delay_min': 1, 'response_delay_max': 15, 'sentiment_bias': 0.0, 'stance': 'neutral', 'influence_weight': 0.8}
    elif entity_type in ['alumni']:
        return {'activity_level': 0.6, 'posts_per_hour': 0.4, 'comments_per_hour': 0.8, 'active_hours': [12, 13, 19, 20, 21, 22, 23], 'response_delay_min': 5, 'response_delay_max': 30, 'sentiment_bias': 0.0, 'stance': 'neutral', 'influence_weight': 1.0}
    else:
        return {'activity_level': 0.7, 'posts_per_hour': 0.5, 'comments_per_hour': 1.2, 'active_hours': [9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23], 'response_delay_min': 2, 'response_delay_max': 20, 'sentiment_bias': 0.0, 'stance': 'neutral', 'influence_weight': 1.0}
