"""
OASIS Simulation Manager
Manage Twitter and Reddit dual-platform parallel simulations
Use preset scripts + LLM intelligent generation of config parameters
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..utils.logger import get_logger
from .artifact_store import SimulationArtifactStore, resolve_default_store
from . import branching_service, prepare_service

if TYPE_CHECKING:
    from ..contracts import PersonaQuotaPlan
# simulation_state_machine importiert ``SimulationStatus`` aus diesem Modul,
# daher Lazy-Import in ``_set_status`` (vermeidet Zirkularität).

logger = get_logger('agora.simulation')


class SimulationStatus(str, Enum):
    """Simulation status"""
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"      # Simulation manually stopped
    COMPLETED = "completed"  # Simulation completed naturally
    FAILED = "failed"


class PlatformType(str, Enum):
    """Platform type"""
    TWITTER = "twitter"
    REDDIT = "reddit"


@dataclass
class SimulationState:
    """Simulation status"""
    simulation_id: str
    project_id: str
    graph_id: str
    
    # Platform enabled state
    enable_twitter: bool = True
    enable_reddit: bool = True
    
    # Status
    status: SimulationStatus = SimulationStatus.CREATED
    
    # Preparation phase data
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: List[str] = field(default_factory=list)
    
    # Config generation information
    config_generated: bool = False
    config_reasoning: str = ""
    
    # Runtime data
    current_round: int = 0
    twitter_status: str = "not_started"
    reddit_status: str = "not_started"
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Error message
    error: Optional[str] = None

    # Scenario branching lineage
    source_simulation_id: Optional[str] = None
    root_simulation_id: Optional[str] = None
    branch_name: Optional[str] = None
    branch_depth: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Complete status dict (internal use)"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "enable_twitter": self.enable_twitter,
            "enable_reddit": self.enable_reddit,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "current_round": self.current_round,
            "twitter_status": self.twitter_status,
            "reddit_status": self.reddit_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "source_simulation_id": self.source_simulation_id,
            "root_simulation_id": self.root_simulation_id,
            "branch_name": self.branch_name,
            "branch_depth": self.branch_depth,
        }
    
    def to_simple_dict(self) -> Dict[str, Any]:
        """Simplified status dict (API return use)"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "error": self.error,
            "source_simulation_id": self.source_simulation_id,
            "root_simulation_id": self.root_simulation_id,
            "branch_name": self.branch_name,
            "branch_depth": self.branch_depth,
        }


class SimulationManager:
    """
    Simulation Manager
    
    Core Functions:
    1. Read entities from graph and filter
    2. Generate OASIS Agent Profile
    3. Use LLM intelligent generation of simulation config parameters
    4. Prepare all files required by preset scripts
    """
    
    # Simulation data storage directory
    SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__), 
        '../../uploads/simulations'
    )
    
    def __init__(self, store: Optional[SimulationArtifactStore] = None):
        # Ensure directory exists
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)

        # In-memory simulation state cache
        self._simulations: Dict[str, SimulationState] = {}

        # SimulationArtifactStore (Issue #13). Falls keiner injiziert wird,
        # ziehen wir den App-weiten Store; outside Flask context fällt der
        # Resolver auf einen Default-LocalAdapter zurück.
        self._store = store or resolve_default_store()
    
    def _get_simulation_dir(self, simulation_id: str) -> str:
        """Get simulation data directory"""
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir
    
    def _save_simulation_state(self, state: SimulationState):
        """Save simulation state to file"""
        # Ensure the on-disk directory exists for non-store consumers (e.g. profile
        # generator writes via filesystem path); the store itself also creates it.
        self._get_simulation_dir(state.simulation_id)

        state.updated_at = datetime.now().isoformat()
        self._store.write_json(state.simulation_id, "state", state.to_dict())

        self._simulations[state.simulation_id] = state

    def _set_status(
        self, state: SimulationState, new_status: SimulationStatus
    ) -> None:
        """Set ``state.status`` after validating the transition against the FSM.

        Wirft :class:`simulation_state_machine.InvalidStatusTransition`, wenn
        der Übergang nicht in ``ALLOWED_TRANSITIONS`` steht. Für legitime
        Resets (Force-Restart einer abgelaufenen Simulation) gibt es die
        separate Methode :meth:`_reset_to_ready`.
        """
        from .simulation_state_machine import assert_valid_transition

        assert_valid_transition(state.status, new_status)
        state.status = new_status
        self._save_simulation_state(state)

    def _reset_to_ready(self, state: SimulationState, *, reason: str) -> None:
        """Force-Reset einer Simulation auf ``READY`` aus beliebigem Status.

        Bewusst kein FSM-Übergang: Aufrufer muss vorher alle Runtime-Artefakte
        (Logs, run_state, control_state) selbst aufgeräumt haben. Der Reset
        wird mit ``reason`` geloggt, damit der Bypass nachvollziehbar bleibt.
        """
        previous = state.status.value
        logger.info(
            f"Force-reset simulation {state.simulation_id} status "
            f"{previous} -> {SimulationStatus.READY.value} (reason: {reason})"
        )
        state.status = SimulationStatus.READY
        self._save_simulation_state(state)

    def _load_simulation_state(self, simulation_id: str) -> Optional[SimulationState]:
        """Load simulation state from file"""
        if simulation_id in self._simulations:
            return self._simulations[simulation_id]

        # Touch the directory so list_simulations + downstream FS users keep working
        # after a fresh install where only state.json exists in the store.
        self._get_simulation_dir(simulation_id)

        if not self._store.exists(simulation_id, "state"):
            return None

        data = self._store.read_json(simulation_id, "state", default=None)
        if not data:
            return None
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
            status=SimulationStatus(data.get("status", "created")),
            entities_count=data.get("entities_count", 0),
            profiles_count=data.get("profiles_count", 0),
            entity_types=data.get("entity_types", []),
            config_generated=data.get("config_generated", False),
            config_reasoning=data.get("config_reasoning", ""),
            current_round=data.get("current_round", 0),
            twitter_status=data.get("twitter_status", "not_started"),
            reddit_status=data.get("reddit_status", "not_started"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
            source_simulation_id=data.get("source_simulation_id"),
            root_simulation_id=data.get("root_simulation_id"),
            branch_name=data.get("branch_name"),
            branch_depth=int(data.get("branch_depth", 0) or 0),
        )
        
        self._simulations[simulation_id] = state
        return state
    
    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
    ) -> SimulationState:
        """
        Create new simulation
        
        Args:
            project_id: Project ID
            graph_id: Graph ID
            enable_twitter: Whether to enable Twitter simulation
            enable_reddit: Whether to enable Reddit simulation
            
        Returns:
            SimulationState
        """
        import uuid
        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
            status=SimulationStatus.CREATED,
            root_simulation_id=simulation_id,
        )
        
        self._save_simulation_state(state)
        logger.info(f"Create simulation: {simulation_id}, project={project_id}, graph={graph_id}")
        
        return state
    
    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: Optional[List[str]] = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Optional[callable] = None,
        parallel_profile_count: Optional[int] = None,
        storage: Any = None,
        llm_model: Optional[str] = None,
        language: Optional[str] = None,
        max_agents: Optional[int] = None,
        quota_plan: Optional["PersonaQuotaPlan"] = None,
    ) -> SimulationState:
        return prepare_service.prepare_simulation(
            self,
            simulation_id,
            simulation_requirement,
            document_text,
            defined_entity_types=defined_entity_types,
            use_llm_for_profiles=use_llm_for_profiles,
            progress_callback=progress_callback,
            parallel_profile_count=parallel_profile_count,
            storage=storage,
            llm_model=llm_model,
            language=language,
            max_agents=max_agents,
            quota_plan=quota_plan,
        )

    
    def get_simulation(self, simulation_id: str) -> Optional[SimulationState]:
        """Get simulation state"""
        return self._load_simulation_state(simulation_id)
    
    def list_simulations(self, project_id: Optional[str] = None) -> List[SimulationState]:
        """List all simulations"""
        simulations = []
        
        if os.path.exists(self.SIMULATION_DATA_DIR):
            for sim_id in os.listdir(self.SIMULATION_DATA_DIR):
                # Skip hidden files (such as .DS_Store) and non-directory files
                sim_path = os.path.join(self.SIMULATION_DATA_DIR, sim_id)
                if sim_id.startswith('.') or not os.path.isdir(sim_path):
                    continue
                
                state = self._load_simulation_state(sim_id)
                if state:
                    if project_id is None or state.project_id == project_id:
                        simulations.append(state)
        
        return simulations

    def get_simulation_config(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        if not self._store.exists(simulation_id, "simulation_config"):
            return None
        return self._store.read_json(simulation_id, "simulation_config", default=None)

    def list_branches(self, simulation_id: str) -> List[SimulationState]:
        return branching_service.list_branches(self, simulation_id)

    def create_branch(
        self,
        simulation_id: str,
        branch_name: str,
        *,
        copy_profiles: bool = True,
        copy_report_artifacts: bool = False,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> SimulationState:
        return branching_service.create_branch(
            self,
            simulation_id,
            branch_name,
            copy_profiles=copy_profiles,
            copy_report_artifacts=copy_report_artifacts,
            overrides=overrides,
        )

    def get_profiles(self, simulation_id: str, platform: str = "reddit") -> List[Dict[str, Any]]:
        """Get Agent Profiles for simulation.

        Only Reddit profiles are persisted as JSON; Twitter uses CSV (out of
        scope for the JSON artifact store) and would always have been empty
        through this code path.
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation does not exist: {simulation_id}")

        if platform != "reddit":
            return []

        if not self._store.exists(simulation_id, "reddit_profiles"):
            return []
        return self._store.read_json(simulation_id, "reddit_profiles", default=[]) or []
    
    def get_run_instructions(self, simulation_id: str) -> Dict[str, str]:
        """Get run instructions"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "twitter": f"python {scripts_dir}/run_twitter_simulation.py --config {config_path}",
                "reddit": f"python {scripts_dir}/run_reddit_simulation.py --config {config_path}",
                "parallel": f"python {scripts_dir}/run_parallel_simulation.py --config {config_path}",
            },
            "instructions": (
                f"1. Activate conda environment: conda activate Agora\n"
                f"2. Run simulation (scripts located in {scripts_dir}):\n"
                f"   - Run Twitter alone: python {scripts_dir}/run_twitter_simulation.py --config {config_path}\n"
                f"   - Run Reddit alone: python {scripts_dir}/run_reddit_simulation.py --config {config_path}\n"
                f"   - Run both platforms in parallel: python {scripts_dir}/run_parallel_simulation.py --config {config_path}"
            )
        }
