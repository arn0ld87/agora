"""
Simulation Configuration Intelligent Generator
Use LLM to automatically generate detailed simulation parameters based on simulation requirements, document content, and knowledge graph information
Implement full process automation without manual parameter setting

Adopt step-by-step generation strategy to avoid failures from generating too long content at once:
1. Generate time configuration
2. Generate event configuration
3. Generate agent configurations in batches
4. Generate platform configuration
"""

import math
import os
from typing import Dict, Any, List, Optional, Callable


from ..config import Config
from ..contracts.provider_types import PROVIDER_CODEX_CLI
from ..utils.logger import get_logger
from .entity_reader import EntityNode
from ..utils.llm_client import LLMClient

from .simulation_config_models import (
    AgentActivityConfig as AgentActivityConfig,
    EventConfig as EventConfig,
    PlatformConfig as PlatformConfig,
    SimulationParameters as SimulationParameters,
    TimeSimulationConfig as TimeSimulationConfig,
)
from . import simulation_config_context as _simulation_config_context
from . import simulation_config_llm as _simulation_config_llm
from . import simulation_config_time as _simulation_config_time
from . import simulation_config_events as _simulation_config_events
from . import simulation_config_agents as _simulation_config_agents

logger = get_logger("agora.simulation_config")

# Default DACH social activity timing profile (Europe/Berlin).
DACH_TIMEZONE_CONFIG = {
    # Dead hours (almost no activity)
    "dead_hours": [0, 1, 2, 3, 4, 5],
    # Morning hours (gradually waking up)
    "morning_hours": [6, 7, 8],
    # Work hours
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16],
    # Evening peak (most active)
    "peak_hours": [18, 19, 20, 21, 22],
    # Night hours (activity decreases)
    "night_hours": [23],
    # Activity multipliers
    "activity_multipliers": {
        "dead": 0.05,  # Almost no one in early morning
        "morning": 0.4,  # Gradually active in morning
        "work": 0.6,  # Lower activity during German office hours
        "peak": 1.5,  # Evening peak
        "night": 0.5,  # Activity decreases at night
    },
}














class SimulationConfigGenerator:
    """
    Simulation Configuration Intelligent Generator

    Use LLM to analyze simulation requirements, document content, knowledge graph entity information,
    and automatically generate optimal simulation parameter configuration

    Adopt step-by-step generation strategy:
    1. Generate time configuration and event configuration (lightweight)
    2. Generate agent configurations in batches (10-20 per batch)
    3. Generate platform configuration
    """

    # Maximum context length in characters
    MAX_CONTEXT_LENGTH = 50000
    # Number of agents per batch — Default 8 (#870); via AGORA_AGENTS_PER_BATCH
    # überschreibbar (siehe _resolve_agents_per_batch). 15 war zu groß für die
    # aktuellen LLM-Workloads (hohe Latenz, Memory-Peak).
    AGENTS_PER_BATCH = 8

    # Obergrenze für gleichzeitig laufende Agent-Config-Batches (Perf-Fix,
    # Produktionsmessung: 3 Batches sequentiell 81s statt ~28s parallel).
    # Batches sind disjunkte Entity-Bereiche und lesen nur aus dem
    # unveränderlichen ``context`` — beliebig parallelisierbar. Der Deckel
    # verhindert bei sehr vielen Entities unbegrenzt viele gleichzeitige
    # LLM-Requests; 8 spiegelt den AGENTS_PER_BATCH-Default.
    MAX_PARALLEL_AGENT_BATCHES = 8

    # Context truncation length for each step (characters)
    TIME_CONFIG_CONTEXT_LENGTH = 10000  # Time configuration
    EVENT_CONFIG_CONTEXT_LENGTH = 8000  # Event configuration
    ENTITY_SUMMARY_LENGTH = 300  # Entity summary
    AGENT_SUMMARY_LENGTH = 300  # Entity summary in agent configuration
    ENTITIES_PER_TYPE_DISPLAY = 20  # Number of entities to display per type

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        provider_type: Optional[str] = None,
        language: Optional[str] = None,
        run_id: Optional[str] = None,
    ):
        self.provider_type = provider_type
        # ``self.base_url``/``self.api_key`` bleiben absichtlich beim
        # ``.env``-Fallback-Schema (#778) — ``generate_config`` schreibt sie
        # weiter unten in ``SimulationParameters.llm_base_url`` fuer die
        # Simulations-Runden, ein Pfad, den Issue #1418 nicht anfasst.
        self.base_url = base_url or Config.LLM_BASE_URL
        # Key und Base-URL muessen aus derselben Quelle stammen (#778). Loest der
        # Aufrufer einen Provider-Endpoint auf, darf der .env-Key NICHT einspringen —
        # sonst geht der lokale Ollama-Key an einen Fremd-Provider (404/401).
        self.api_key = api_key or (
            Config.LLM_API_KEY if self.base_url == Config.LLM_BASE_URL else None
        )
        self.model_name = model_name or Config.LLM_MODEL_NAME
        # Normalize language to two-letter code; defaults from Config.AGENT_LANGUAGE.
        self.language = (language or Config.AGENT_LANGUAGE or "de").lower()
        # Batching-Granularität (#870): ENV-konfigurierbar, Default 8.
        self.AGENTS_PER_BATCH = self._resolve_agents_per_batch()

        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")

        # Issue #1418: codex_cli (transport="cli", #1405) hat weder base_url
        # noch api_key — der eigene LLMClient dieses Generators (fuer die
        # Config-Generierung) darf nicht mit dem obigen .env-Fallback gebaut
        # werden, sonst geht das Modell aus der Route an einen fremden
        # HTTP-Provider (beobachtet: gpt-5.6-luna an minimax.io → 400).
        is_cli_provider = provider_type == PROVIDER_CODEX_CLI
        client_base_url = None if is_cli_provider else self.base_url
        client_api_key = (
            (api_key or "codex-cli-local-session") if is_cli_provider else self.api_key
        )

        self.llm_client = LLMClient(
            api_key=client_api_key,
            base_url=client_base_url,
            model=self.model_name,
            # Budget-Enforcement (#984): ohne run_id gibt es keinen Enforcer —
            # Config-Generierung liefe am harten Run-Budget vorbei.
            run_id=run_id,
            # Ohne provider_type erkennt LLMClient codex_cli nicht als
            # Subprozess-Provider und versucht einen HTTP-Call.
            provider_type=self.provider_type,
        )

    @staticmethod
    def _resolve_agents_per_batch() -> int:
        """Löst AGENTS_PER_BATCH aus ENV ``AGORA_AGENTS_PER_BATCH`` (Default 8).

        Issue #870: 15 war zu groß für die aktuellen LLM-Workloads. Der Default
        fällt auf 8 (im Bereich 5–8). Ungültige Werte (non-int oder <1) fallen
        mit Warnung auf den Default zurück, damit ein Tippfehler in der ENV
        die Simulation nicht lahmlegt.
        """
        default = 8
        raw = os.getenv("AGORA_AGENTS_PER_BATCH")
        if raw is None or raw.strip() == "":
            return default
        try:
            value = int(raw)
        except ValueError:
            logger.warning(
                "AGORA_AGENTS_PER_BATCH='%s' ist keine Ganzzahl, falle auf Default %d zurück.",
                raw,
                default,
            )
            return default
        if value < 1:
            logger.warning(
                "AGORA_AGENTS_PER_BATCH=%d ist <1, falle auf Default %d zurück.",
                value,
                default,
            )
            return default
        return value

    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> SimulationParameters:
        """
        Intelligently generate complete simulation configuration (step-by-step generation)

        Args:
            simulation_id: Simulation ID
            project_id: Project ID
            graph_id: Knowledge graph ID
            simulation_requirement: Simulation requirement description
            document_text: Original document content
            entities: Filtered entity list
            enable_twitter: Whether to enable Twitter
            enable_reddit: Whether to enable Reddit
            progress_callback: Progress callback function(current_step, total_steps, message)

        Returns:
            SimulationParameters: Complete simulation parameters
        """
        logger.info(
            f"Starting intelligent simulation configuration generation: simulation_id={simulation_id}, entities={len(entities)}"
        )

        # Calculate total steps
        num_batches = math.ceil(len(entities) / self.AGENTS_PER_BATCH)
        total_steps = (
            3 + num_batches
        )  # time config + event config + N batch agents + platform config
        current_step = 0

        def report_progress(step: int, message: str):
            nonlocal current_step
            current_step = step
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")

        # 1. Build basic context information
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities,
        )

        reasoning_parts = []

        # ========== Step 1: Generate time configuration ==========
        report_progress(1, "Generating time configuration...")
        num_entities = len(entities)
        time_config_result = self._generate_time_config(context, num_entities)
        time_config = self._parse_time_config(time_config_result, num_entities)
        reasoning_parts.append(f"Time config: {time_config_result.get('reasoning', 'Success')}")

        # ========== Step 2: Generate event configuration ==========
        report_progress(2, "Generating event configuration and hot topics...")
        event_config_result = self._generate_event_config(context, simulation_requirement, entities)
        event_config = self._parse_event_config(event_config_result)
        reasoning_parts.append(f"Event config: {event_config_result.get('reasoning', 'Success')}")

        # ========== Step 3-N: Generate agent configurations in batches ==========
        # Perf-Fix: Batches sind disjunkte Entity-Bereiche, lesen nur aus dem
        # unveränderlichen ``context`` und schreiben in keine gemeinsame
        # Struktur — sie sind voneinander unabhängig und laufen parallel
        # (siehe ``_generate_agent_configs_parallel``). Produktionsmessung:
        # 3 Batches sequentiell ~81s, parallel ~28s.
        all_agent_configs: List[AgentActivityConfig] = []
        if num_batches:
            batch_ranges = [
                (
                    batch_idx * self.AGENTS_PER_BATCH,
                    min((batch_idx + 1) * self.AGENTS_PER_BATCH, len(entities)),
                )
                for batch_idx in range(num_batches)
            ]

            report_progress(
                3,
                f"Generating agent configuration in {num_batches} parallel "
                f"batch(es) (1-{len(entities)}/{len(entities)})...",
            )

            all_agent_configs = self._generate_agent_configs_parallel(
                context=context,
                entities=entities,
                batch_ranges=batch_ranges,
                simulation_requirement=simulation_requirement,
            )

            report_progress(
                2 + num_batches,
                f"Agent configuration batches complete ({len(all_agent_configs)}/{len(entities)})...",
            )

        reasoning_parts.append(f"Agent config: Successfully generated {len(all_agent_configs)}")

        # ========== Skeptiker-Quote ≥20 % (Slice 5, Issue #497) ==========
        all_agent_configs = self._ensure_skeptic_quota(all_agent_configs)

        # ========== Assign initial post agents ==========
        logger.info("Assigning appropriate publisher agents to initial posts...")
        event_config = self._assign_initial_post_agents(event_config, all_agent_configs)
        assigned_count = len(
            [p for p in event_config.initial_posts if p.get("poster_agent_id") is not None]
        )
        reasoning_parts.append(
            f"Initial posts assigned: {assigned_count} posts assigned publishers"
        )

        # ========== Final step: Generate platform configuration ==========
        report_progress(total_steps, "Generating platform configuration...")
        twitter_config = None
        reddit_config = None

        if enable_twitter:
            twitter_config = PlatformConfig(
                platform="twitter",
                recency_weight=0.4,
                popularity_weight=0.3,
                relevance_weight=0.3,
                viral_threshold=10,
                echo_chamber_strength=0.5,
            )

        if enable_reddit:
            reddit_config = PlatformConfig(
                platform="reddit",
                recency_weight=0.3,
                popularity_weight=0.4,
                relevance_weight=0.3,
                viral_threshold=15,
                echo_chamber_strength=0.6,
            )

        # Build final parameters
        params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            time_config=time_config,
            agent_configs=all_agent_configs,
            event_config=event_config,
            twitter_config=twitter_config,
            reddit_config=reddit_config,
            llm_model=self.model_name,
            llm_base_url=self.base_url,
            language=self.language,
            enable_agent_tools=getattr(Config, "ENABLE_AGENT_TOOLS", False),
            max_tool_calls_per_action=getattr(Config, "MAX_TOOL_CALLS_PER_ACTION", 2),
            neo4j_uri=Config.NEO4J_URI,
            neo4j_user=Config.NEO4J_USER,
            generation_reasoning=" | ".join(reasoning_parts),
        )

        logger.info(
            f"Simulation configuration generation complete: {len(params.agent_configs)} agent configurations"
        )

        return params

    def _build_context(self, simulation_requirement: str, document_text: str, entities: List[EntityNode]) -> str:
        return _simulation_config_context._build_context(self, simulation_requirement, document_text, entities)

    def _summarize_entities(self, entities: List[EntityNode]) -> str:
        return _simulation_config_context._summarize_entities(self, entities)

    def _call_llm_with_retry(self, prompt: str, system_prompt: str, schema: Any) -> Dict[str, Any]:
        return _simulation_config_llm._call_llm_with_retry(self, prompt, system_prompt, schema)

    def _fix_truncated_json(self, content: str) -> str:
        return _simulation_config_llm._fix_truncated_json(self, content)

    def _try_fix_config_json(self, content: str) -> Optional[Dict[str, Any]]:
        return _simulation_config_llm._try_fix_config_json(self, content)

    def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
        return _simulation_config_time._generate_time_config(self, context, num_entities)

    def _get_default_time_config(self, num_entities: int) -> Dict[str, Any]:
        return _simulation_config_time._get_default_time_config(self, num_entities)

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        return _simulation_config_time._coerce_int(value, default)

    @staticmethod
    def _coerce_int_list(value: Any, default: List[int]) -> List[int]:
        return _simulation_config_time._coerce_int_list(value, default)

    def _parse_time_config(self, result: Dict[str, Any], num_entities: int) -> TimeSimulationConfig:
        return _simulation_config_time._parse_time_config(self, result, num_entities)

    def _generate_event_config(self, context: str, simulation_requirement: str, entities: List[EntityNode]) -> Dict[str, Any]:
        return _simulation_config_events._generate_event_config(self, context, simulation_requirement, entities)

    def _parse_event_config(self, result: Dict[str, Any]) -> EventConfig:
        return _simulation_config_events._parse_event_config(self, result)

    def _assign_initial_post_agents(self, event_config: EventConfig, agent_configs: List[AgentActivityConfig]) -> EventConfig:
        return _simulation_config_events._assign_initial_post_agents(self, event_config, agent_configs)

    def _generate_agent_configs_parallel(self, context: str, entities: List[EntityNode], batch_ranges: List[tuple[int, int]], simulation_requirement: str) -> List[AgentActivityConfig]:
        return _simulation_config_agents._generate_agent_configs_parallel(self, context, entities, batch_ranges, simulation_requirement)

    def _generate_agent_configs_batch(self, context: str, entities: List[EntityNode], start_idx: int, simulation_requirement: str) -> List[AgentActivityConfig]:
        return _simulation_config_agents._generate_agent_configs_batch(self, context, entities, start_idx, simulation_requirement)

    @staticmethod
    def _ensure_skeptic_quota(personas: List[AgentActivityConfig], min_ratio: float=0.2) -> List[AgentActivityConfig]:
        return _simulation_config_agents._ensure_skeptic_quota(personas, min_ratio)

    def _generate_agent_config_by_rule(self, entity: EntityNode) -> Dict[str, Any]:
        return _simulation_config_agents._generate_agent_config_by_rule(self, entity)
