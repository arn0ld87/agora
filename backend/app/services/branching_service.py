"""Branching service for simulations.

Issue #44 (EPIC-06-ST-04): Branch-Logik aus ``SimulationManager`` in eigene
Service-Datei extrahiert. Funktionen nehmen einen ``SimulationManager`` als
ersten Parameter, um zirkuläre Importe zu vermeiden — der Manager bleibt die
einzige Eintrittstelle für Caller, delegiert aber an dieses Modul.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..config import Config
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger
from .run_registry import RunRegistry

if TYPE_CHECKING:
    from .simulation_manager import SimulationManager, SimulationState

logger = get_logger("agora.branching")


def list_branches(
    manager: SimulationManager, simulation_id: str
) -> List[SimulationState]:
    """Liste aller Branches, die denselben Root teilen wie ``simulation_id``.

    Sortiert absteigend nach ``created_at``. Liefert leere Liste, wenn die
    Quell-Simulation nicht existiert.
    """
    source = manager.get_simulation(simulation_id)
    if not source:
        return []
    root_id = source.root_simulation_id or source.simulation_id
    simulations = manager.list_simulations(project_id=source.project_id)
    branches = [
        sim for sim in simulations
        if (sim.root_simulation_id or sim.simulation_id) == root_id
    ]
    branches.sort(key=lambda sim: sim.created_at, reverse=True)
    return branches


def create_branch(
    manager: SimulationManager,
    simulation_id: str,
    branch_name: str,
    *,
    copy_profiles: bool = True,
    copy_report_artifacts: bool = False,
    overrides: Optional[Dict[str, Any]] = None,
) -> SimulationState:
    """Erstelle einen Branch mit optionalen Overrides für Config und Personas.

    Validiert Override-Keys, setzt den Branch-State auf ``READY`` und kopiert
    die Profile bzw. Report-Artefakte je nach Flag. Persona-Removals/Additions
    werden in :func:`_apply_persona_overrides` angewandt.
    """
    # Lazy-Import zur Vermeidung des Circular-Imports
    # (simulation_manager importiert dieses Modul für Delegationen).
    from .simulation_manager import SimulationStatus

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

    source = manager.get_simulation(simulation_id)
    if not source:
        raise ValueError(f"Simulation does not exist: {simulation_id}")
    if source.status not in {
        SimulationStatus.READY,
        SimulationStatus.RUNNING,
        SimulationStatus.PAUSED,
        SimulationStatus.STOPPED,
        SimulationStatus.COMPLETED,
        SimulationStatus.FAILED,
    }:
        raise ValueError("Only prepared simulations can be branched")

    source_dir = manager._get_simulation_dir(simulation_id)
    if not manager._store.exists(simulation_id, "simulation_config"):
        raise ValueError("Prepared simulation config not found")

    config = manager._store.read_json(simulation_id, "simulation_config", default=None)
    if not config:
        raise ValueError("Prepared simulation config is unreadable")

    enable_twitter = bool(overrides.get("enable_twitter", source.enable_twitter))
    enable_reddit = bool(overrides.get("enable_reddit", source.enable_reddit))
    branch = manager.create_simulation(
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

    branch_dir = manager._get_simulation_dir(branch.simulation_id)

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

    manager._store.write_json(branch.simulation_id, "simulation_config", config)

    persona_removals = set(overrides.get("persona_removals") or [])
    persona_additions = overrides.get("persona_additions") or []

    if copy_profiles:
        for filename in ("reddit_profiles.json", "twitter_profiles.csv"):
            src = os.path.join(source_dir, filename)
            dst = os.path.join(branch_dir, filename)
            if os.path.exists(src):
                shutil.copy2(src, dst)

        if persona_removals or persona_additions:
            _apply_persona_overrides(
                manager, branch.simulation_id, branch_dir, persona_removals, persona_additions
            )

    if copy_report_artifacts:
        reports_dir = os.path.join(Config.UPLOAD_FOLDER, "reports")
        if os.path.isdir(reports_dir):
            for report_folder in os.listdir(reports_dir):
                meta_path = os.path.join(reports_dir, report_folder, "meta.json")
                if not os.path.exists(meta_path):
                    continue
                # Reports live outside the SimulationArtifactStore namespace
                # (separate ReportStore is on the roadmap, Issue #46). Inline
                # JSON read is the explicit boundary; no json_io leak into
                # services/.
                try:
                    with open(meta_path, "r", encoding="utf-8") as handle:
                        report_meta = json.load(handle)
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning(f"Skipping unreadable report meta {meta_path}: {exc}")
                    continue
                if not report_meta or report_meta.get("simulation_id") != simulation_id:
                    continue
                branch_report_dir = os.path.join(branch_dir, "reports", report_folder)
                shutil.copytree(
                    os.path.join(reports_dir, report_folder),
                    branch_report_dir,
                    dirs_exist_ok=True,
                )

    manager._save_simulation_state(branch)
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
    manager: SimulationManager,
    simulation_id: str,
    sim_dir: str,
    persona_removals: set,
    persona_additions: List[Dict[str, Any]],
) -> None:
    """Wende Persona-Removals und -Additions auf Reddit-JSON und Twitter-CSV an.

    Reddit-Profile liegen im Artifact-Store (logischer Name ``reddit_profiles``);
    Twitter-Profile sind ein CSV-Export außerhalb des Stores und werden direkt
    auf der Platte editiert.
    """
    twitter_path = os.path.join(sim_dir, "twitter_profiles.csv")

    if manager._store.exists(simulation_id, "reddit_profiles"):
        reddit_profiles = manager._store.read_json(
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
        manager._store.write_json(simulation_id, "reddit_profiles", reddit_profiles)

    if os.path.exists(twitter_path):
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


__all__ = ["list_branches", "create_branch"]
