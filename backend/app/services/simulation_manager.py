"""
OASIS Simulation Manager
Manage Twitter and Reddit dual-platform parallel simulations
Use preset scripts + LLM intelligent generation of config parameters
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.logger import get_logger
from ..utils.artifact_locator import ArtifactLocator
from .artifact_store import SimulationArtifactStore, resolve_default_store
from .entity_reader import EntityReader
from .oasis_profile_generator import OasisProfileGenerator
from .simulation_config_generator import SimulationConfigGenerator
from .run_registry import RunRegistry

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
        parallel_profile_count: int = 3,
        storage: Any = None,
        llm_model: Optional[str] = None,
        language: Optional[str] = None,
        max_agents: Optional[int] = None,
    ) -> SimulationState:
        """
        Prepare simulation environment (fully automated)
        
        Steps:
        1. Read and filter entities from graph
        2. Generate OASIS Agent Profile for each entity (optional LLM enhancement, parallel support)
        3. Use LLM intelligent generation of simulation config parameters (time, activity, speaking frequency, etc.)
        4. Save config files and Profile files
        5. Copy preset scripts to simulation directory
        
        Args:
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description (for LLM config generation)
            document_text: Original document content (for LLM background understanding)
            defined_entity_types: Predefined entity types (optional)
            use_llm_for_profiles: Whether to use LLM to generate detailed profiles
            progress_callback: Progress callback function (stage, progress, message)
            parallel_profile_count: Number of parallel profile generations, default 3
            
        Returns:
            SimulationState
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation does not exist: {simulation_id}")
        
        try:
            state.status = SimulationStatus.PREPARING
            self._save_simulation_state(state)
            
            sim_dir = self._get_simulation_dir(simulation_id)
            
            # ========== Phase 1: Read and filter entities ==========
            if progress_callback:
                progress_callback("reading", 0, "Connecting to graph...")

            if not storage:
                raise ValueError("storage (GraphStorage) is required for prepare_simulation")
            reader = EntityReader(storage)
            
            if progress_callback:
                progress_callback("reading", 30, "Reading node data...")
            
            filtered = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=True
            )

            # User-controlled cap on number of agents (optional).
            # Truncates the entity list before persona generation. Entities are
            # kept in reader order so the most relevant ones win if the reader
            # already sorts by degree/importance.
            if max_agents is not None and max_agents > 0 and len(filtered.entities) > max_agents:
                logger.info(
                    f"Capping agent count at {max_agents} "
                    f"(originally {len(filtered.entities)} entities)"
                )
                filtered.entities = filtered.entities[:max_agents]
                filtered.filtered_count = len(filtered.entities)

            state.entities_count = filtered.filtered_count
            state.entity_types = list(filtered.entity_types)

            if progress_callback:
                progress_callback(
                    "reading", 100,
                    f"Completed, total {filtered.filtered_count} entities",
                    current=filtered.filtered_count,
                    total=filtered.filtered_count
                )
            
            if filtered.filtered_count == 0:
                state.status = SimulationStatus.FAILED
                state.error = "No entities matching criteria found, check if graph is correctly constructed"
                self._save_simulation_state(state)
                return state
            
            # ========== Phase 2: Generate Agent Profile ==========
            total_entities = len(filtered.entities)
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 0, 
                    "Starting generation...",
                    current=0,
                    total=total_entities
                )
            
            # Pass graph_id to enable graph retrieval functionality, get richer context.
            # Per-simulation overrides for model + language come from API request.
            generator = OasisProfileGenerator(
                storage=storage,
                graph_id=state.graph_id,
                model_name=llm_model,
                language=language,
            )
            
            def profile_progress(current, total, msg):
                if progress_callback:
                    progress_callback(
                        "generating_profiles", 
                        int(current / total * 100), 
                        msg,
                        current=current,
                        total=total,
                        item_name=msg
                    )
            
            # Set real-time save file path (prefer Reddit JSON format)
            realtime_output_path = None
            realtime_platform = "reddit"
            if state.enable_reddit:
                realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
                realtime_platform = "reddit"
            elif state.enable_twitter:
                realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
                realtime_platform = "twitter"
            
            profiles = generator.generate_profiles_from_entities(
                entities=filtered.entities,
                use_llm=use_llm_for_profiles,
                progress_callback=profile_progress,
                graph_id=state.graph_id,  # Pass graph_id for graph retrieval
                parallel_count=parallel_profile_count,  # Parallel generation count
                realtime_output_path=realtime_output_path,  # Real-time save path
                output_platform=realtime_platform  # Output format
            )
            
            state.profiles_count = len(profiles)
            
            # Save Profile files (Note: Twitter uses CSV format, Reddit uses JSON format)
            # Reddit has been saved in real-time during generation, save once more here to ensure completeness
            if progress_callback:
                progress_callback(
                    "generating_profiles", 95, 
                    "Saving Profile files...",
                    current=total_entities,
                    total=total_entities
                )
            
            if state.enable_reddit:
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "reddit_profiles.json"),
                    platform="reddit"
                )
            
            if state.enable_twitter:
                # Twitter uses CSV format! This is OASIS requirement
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
                    platform="twitter"
                )
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 100, 
                    f"Completed, total {len(profiles)} Profiles",
                    current=len(profiles),
                    total=len(profiles)
                )
            
            # ========== Phase 3: LLM intelligent generation of simulation config ==========
            if progress_callback:
                progress_callback(
                    "generating_config", 0, 
                    "Analyzing simulation requirements...",
                    current=0,
                    total=3
                )
            
            config_generator = SimulationConfigGenerator(
                model_name=llm_model,
                language=language,
            )
            
            if progress_callback:
                progress_callback(
                    "generating_config", 30, 
                    "Calling LLM to generate config...",
                    current=1,
                    total=3
                )
            
            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=filtered.entities,
                enable_twitter=state.enable_twitter,
                enable_reddit=state.enable_reddit
            )
            
            if progress_callback:
                progress_callback(
                    "generating_config", 70, 
                    "Saving config files...",
                    current=2,
                    total=3
                )
            
            # Save config files (atomic via store — fixes prior non-atomic write).
            self._store.write_json(
                simulation_id,
                "simulation_config",
                json.loads(sim_params.to_json()),
            )
            
            state.config_generated = True
            state.config_reasoning = sim_params.generation_reasoning
            
            if progress_callback:
                progress_callback(
                    "generating_config", 100, 
                    "Config generation completed",
                    current=3,
                    total=3
                )
            
            # Note: Run scripts remain in backend/scripts/ directory, no longer copy to simulation directory
            # When starting simulation, simulation_runner runs scripts from scripts/ directory
            
            # Update status
            state.status = SimulationStatus.READY
            self._save_simulation_state(state)
            
            logger.info(f"Simulation preparation completed: {simulation_id}, "
                       f"entities={state.entities_count}, profiles={state.profiles_count}")
            
            return state
            
        except Exception as e:
            logger.error(f"Simulation preparation failed: {simulation_id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            state.status = SimulationStatus.FAILED
            state.error = str(e)
            self._save_simulation_state(state)
            raise
    
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
        source = self.get_simulation(simulation_id)
        if not source:
            return []
        root_id = source.root_simulation_id or source.simulation_id
        simulations = self.list_simulations(project_id=source.project_id)
        branches = [
            sim for sim in simulations
            if (sim.root_simulation_id or sim.simulation_id) == root_id
        ]
        branches.sort(key=lambda sim: sim.created_at, reverse=True)
        return branches

    def create_branch(
        self,
        simulation_id: str,
        branch_name: str,
        *,
        copy_profiles: bool = True,
        copy_report_artifacts: bool = False,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> SimulationState:
        allowed_override_keys = {
            "llm_model",
            "language",
            "max_agents",
            "time_config",
            "enable_twitter",
            "enable_reddit",
            "persona_additions",
            "persona_removals",
        }
        overrides = overrides or {}
        unknown = sorted(set(overrides.keys()) - allowed_override_keys)
        if unknown:
            raise ValueError(f"Unsupported branch overrides: {', '.join(unknown)}")

        source = self.get_simulation(simulation_id)
        if not source:
            raise ValueError(f"Simulation does not exist: {simulation_id}")
        if source.status not in {SimulationStatus.READY, SimulationStatus.RUNNING, SimulationStatus.PAUSED, SimulationStatus.STOPPED, SimulationStatus.COMPLETED, SimulationStatus.FAILED}:
            raise ValueError("Only prepared simulations can be branched")

        source_dir = self._get_simulation_dir(simulation_id)
        if not self._store.exists(simulation_id, "simulation_config"):
            raise ValueError("Prepared simulation config not found")

        config = self._store.read_json(simulation_id, "simulation_config", default=None)
        if not config:
            raise ValueError("Prepared simulation config is unreadable")

        enable_twitter = bool(overrides.get("enable_twitter", source.enable_twitter))
        enable_reddit = bool(overrides.get("enable_reddit", source.enable_reddit))
        branch = self.create_simulation(
            project_id=source.project_id,
            graph_id=source.graph_id,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
        )
        branch.status = SimulationStatus.READY
        branch.entities_count = source.entities_count
        branch.profiles_count = source.profiles_count
        branch.entity_types = list(source.entity_types)
        branch.config_generated = True
        branch.source_simulation_id = source.simulation_id
        branch.root_simulation_id = source.root_simulation_id or source.simulation_id
        branch.branch_name = branch_name
        branch.branch_depth = int(source.branch_depth or 0) + 1
        branch.config_reasoning = source.config_reasoning

        branch_dir = self._get_simulation_dir(branch.simulation_id)

        config["simulation_id"] = branch.simulation_id
        config["project_id"] = branch.project_id
        config["graph_id"] = branch.graph_id
        config["branch_metadata"] = {
            "source_simulation_id": source.simulation_id,
            "root_simulation_id": branch.root_simulation_id,
            "branch_name": branch_name,
            "branch_depth": branch.branch_depth,
        }
        for key in ("llm_model", "language", "max_agents"):
            if key in overrides and overrides[key] not in (None, ""):
                config[key] = overrides[key]
        if "time_config" in overrides and isinstance(overrides["time_config"], dict):
            existing = config.get("time_config", {}) or {}
            existing.update(overrides["time_config"])
            config["time_config"] = existing
        config["enable_twitter"] = enable_twitter
        config["enable_reddit"] = enable_reddit

        self._store.write_json(branch.simulation_id, "simulation_config", config)

        persona_removals = set(overrides.get("persona_removals") or [])
        persona_additions = overrides.get("persona_additions") or []

        if copy_profiles:
            for filename in ("reddit_profiles.json", "twitter_profiles.csv"):
                src = os.path.join(source_dir, filename)
                dst = os.path.join(branch_dir, filename)
                if os.path.exists(src):
                    shutil.copy2(src, dst)

            if persona_removals or persona_additions:
                self._apply_persona_overrides(
                    branch.simulation_id, branch_dir, persona_removals, persona_additions
                )

        if copy_report_artifacts:
            reports_dir = os.path.join(Config.UPLOAD_FOLDER, "reports")
            if os.path.isdir(reports_dir):
                for report_folder in os.listdir(reports_dir):
                    meta_path = os.path.join(reports_dir, report_folder, "meta.json")
                    if not os.path.exists(meta_path):
                        continue
                    # Reports live outside the SimulationArtifactStore namespace
                    # (separate ReportStore is on the roadmap). Inline JSON read
                    # is the explicit boundary; no json_io leak into services/.
                    try:
                        with open(meta_path, "r", encoding="utf-8") as handle:
                            report_meta = json.load(handle)
                    except (json.JSONDecodeError, OSError) as exc:
                        logger.warning(f"Skipping unreadable report meta {meta_path}: {exc}")
                        continue
                    if not report_meta or report_meta.get("simulation_id") != simulation_id:
                        continue
                    branch_report_dir = os.path.join(branch_dir, "reports", report_folder)
                    shutil.copytree(os.path.join(reports_dir, report_folder), branch_report_dir, dirs_exist_ok=True)

        self._save_simulation_state(branch)
        RunRegistry().create_run(
            run_type="simulation_prepare",
            entity_id=branch.simulation_id,
            status="completed",
            progress=100,
            message=f"Scenario branch created from {simulation_id}",
            branch_label=branch_name,
            linked_ids={
                "simulation_id": branch.simulation_id,
                "project_id": branch.project_id,
                "source_simulation_id": simulation_id,
            },
            artifacts=ArtifactLocator.existing_paths({
                "simulation": ArtifactLocator.simulation_artifacts(branch.simulation_id),
            }),
            metadata={
                "branch_name": branch_name,
                "branch_depth": branch.branch_depth,
                "root_simulation_id": branch.root_simulation_id,
                "copy_profiles": copy_profiles,
                "copy_report_artifacts": copy_report_artifacts,
                "overrides": overrides,
            },
        )
        return branch

    def _apply_persona_overrides(
        self,
        simulation_id: str,
        sim_dir: str,
        persona_removals: set,
        persona_additions: List[Dict[str, Any]],
    ) -> None:
        twitter_path = os.path.join(sim_dir, "twitter_profiles.csv")

        if self._store.exists(simulation_id, "reddit_profiles"):
            reddit_profiles = self._store.read_json(
                simulation_id, "reddit_profiles", default=[]
            ) or []
            reddit_profiles = [
                profile for profile in reddit_profiles
                if profile.get("username") not in persona_removals
            ]
            for addition in persona_additions:
                platform = (addition.get("platform") or "reddit").lower()
                if platform == "reddit":
                    reddit_profiles.append(addition)
            self._store.write_json(simulation_id, "reddit_profiles", reddit_profiles)

        if os.path.exists(twitter_path):
            import csv

            with open(twitter_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                twitter_profiles = [
                    row for row in reader
                    if row.get("username") not in persona_removals
                ]
            for addition in persona_additions:
                platform = (addition.get("platform") or "reddit").lower()
                if platform != "twitter":
                    continue
                if not fieldnames:
                    fieldnames = list(addition.keys())
                for key in addition.keys():
                    if key not in fieldnames:
                        fieldnames.append(key)
                twitter_profiles.append({k: addition.get(k, "") for k in fieldnames})
            if fieldnames:
                with open(twitter_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(twitter_profiles)
    
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
