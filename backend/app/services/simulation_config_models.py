"""Data contracts for simulation configuration generation.

Extracted from simulation_config_generator so the generator can stay an orchestration facade.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

@dataclass
class AgentActivityConfig:
    """Activity configuration for a single Agent"""

    agent_id: int
    entity_uuid: str
    entity_name: str
    entity_type: str

    # Activity configuration (0.0-1.0)
    activity_level: float = 0.5  # Overall activity level

    # Speech frequency (expected posts per hour)
    posts_per_hour: float = 1.0
    comments_per_hour: float = 2.0

    # Active time periods (24-hour format, 0-23)
    active_hours: List[int] = field(default_factory=lambda: list(range(8, 23)))

    # Response speed (reaction delay to trending events, unit: simulation minutes)
    response_delay_min: int = 5
    response_delay_max: int = 60

    # Sentiment tendency (-1.0 to 1.0, negative to positive)
    sentiment_bias: float = 0.0

    # Stance (attitude toward specific topics)
    stance: str = "neutral"  # supportive, opposing, neutral, observer

    # Influence weight (determines probability of their speech being seen by other agents)
    influence_weight: float = 1.0


@dataclass
class TimeSimulationConfig:
    """Time simulation configuration (default profile: DACH / Europe-Berlin)"""

    # Total simulation time (simulation hours)
    total_simulation_hours: int = 72  # Default 72 hours (3 days)

    # Time represented per round (simulation minutes) - default 60 minutes (1 hour), speed up time
    minutes_per_round: int = 60

    # Range of agents activated per hour
    agents_per_hour_min: int = 5
    agents_per_hour_max: int = 20

    # Peak hours (evening after work)
    peak_hours: List[int] = field(default_factory=lambda: [18, 19, 20, 21, 22])
    peak_activity_multiplier: float = 1.5

    # Off-peak hours (early morning 0-5, almost no activity)
    off_peak_hours: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    off_peak_activity_multiplier: float = 0.05  # Very low activity in early morning

    # Morning hours
    morning_hours: List[int] = field(default_factory=lambda: [6, 7, 8])
    morning_activity_multiplier: float = 0.4

    # Work hours
    work_hours: List[int] = field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16])
    work_activity_multiplier: float = 0.6


@dataclass
class EventConfig:
    """Event configuration"""

    # Initial posts (triggering events at the start of simulation)
    initial_posts: List[Dict[str, Any]] = field(default_factory=list)

    # Scheduled events (events triggered at specific times)
    scheduled_events: List[Dict[str, Any]] = field(default_factory=list)

    # Hot topic keywords
    hot_topics: List[str] = field(default_factory=list)

    # Opinion narrative direction
    narrative_direction: str = ""


@dataclass
class PlatformConfig:
    """Platform-specific configuration"""

    platform: str  # twitter or reddit

    # Recommendation algorithm weights
    recency_weight: float = 0.4  # Time freshness
    popularity_weight: float = 0.3  # Popularity
    relevance_weight: float = 0.3  # Relevance

    # Viral threshold (number of interactions before triggering spread)
    viral_threshold: int = 10

    # Echo chamber effect strength (degree of similar opinion clustering)
    echo_chamber_strength: float = 0.5


@dataclass
class SimulationParameters:
    """Complete simulation parameter configuration"""

    # Basic information
    simulation_id: str
    project_id: str
    graph_id: str
    simulation_requirement: str

    # Time configuration
    time_config: TimeSimulationConfig = field(default_factory=TimeSimulationConfig)

    # Agent configuration list
    agent_configs: List[AgentActivityConfig] = field(default_factory=list)

    # Event configuration
    event_config: EventConfig = field(default_factory=EventConfig)

    # Platform configuration
    twitter_config: Optional[PlatformConfig] = None
    reddit_config: Optional[PlatformConfig] = None

    # LLM configuration
    llm_model: str = ""
    llm_base_url: str = ""

    # Agent language ("de" or "en") — controls posts/replies language inside OASIS.
    language: str = "de"

    # Tool-use configuration (injected into subprocess for agent tool calling)
    enable_agent_tools: bool = False
    max_tool_calls_per_action: int = 2
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"

    # Generation metadata
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generation_reasoning: str = ""  # LLM reasoning explanation

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        time_dict = asdict(self.time_config)
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "time_config": time_dict,
            "agent_configs": [asdict(a) for a in self.agent_configs],
            "event_config": asdict(self.event_config),
            "twitter_config": asdict(self.twitter_config) if self.twitter_config else None,
            "reddit_config": asdict(self.reddit_config) if self.reddit_config else None,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "language": self.language,
            "enable_agent_tools": self.enable_agent_tools,
            "max_tool_calls_per_action": self.max_tool_calls_per_action,
            "neo4j_uri": self.neo4j_uri,
            "neo4j_user": self.neo4j_user,
            "generated_at": self.generated_at,
            "generation_reasoning": self.generation_reasoning,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
