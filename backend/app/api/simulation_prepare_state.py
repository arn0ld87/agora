"""Prepared-state and artifact inspection for simulation preparation."""

from __future__ import annotations

import os

from ..config import Config
from .simulation_common import get_artifact_store, logger

def check_simulation_prepared(simulation_id: str) -> tuple:
    """
    Check whether a simulation already has all preparation artifacts.
    """
    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(simulation_dir):
        return False, {"reason": "Simulation directory does not exist"}

    store = get_artifact_store()

    # JSON-Artefakte gehen über den Store; CSV (twitter_profiles) bleibt FS-direkt
    # (out of scope für Issue #13).
    json_artifacts = {
        "state.json": ("state", lambda: store.exists(simulation_id, "state")),
        "simulation_config.json": (
            "simulation_config",
            lambda: store.exists(simulation_id, "simulation_config"),
        ),
        "reddit_profiles.json": (
            "reddit_profiles",
            lambda: store.exists(simulation_id, "reddit_profiles"),
        ),
    }

    existing_files = []
    missing_files = []
    for filename, (_, exists_fn) in json_artifacts.items():
        if exists_fn():
            existing_files.append(filename)
        else:
            missing_files.append(filename)

    twitter_csv = os.path.join(simulation_dir, "twitter_profiles.csv")
    if os.path.exists(twitter_csv):
        existing_files.append("twitter_profiles.csv")
    else:
        missing_files.append("twitter_profiles.csv")

    if missing_files:
        return False, {
            "reason": "Missing required files",
            "missing_files": missing_files,
            "existing_files": existing_files,
        }

    try:
        state_data = store.read_json(simulation_id, "state", default=None)
        if not state_data:
            return False, {"reason": "State file is unreadable or temporarily incomplete"}

        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)
        logger.debug(
            f"Detect simulation preparation status: {simulation_id}, status={status}, config_generated={config_generated}"
        )

        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
        if status in prepared_statuses and config_generated:
            profiles_data = store.read_json(simulation_id, "reddit_profiles", default=[]) or []
            profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0

            if status == "preparing":
                # Der Aufrufer uebersetzt is_prepared=True unabhaengig vom
                # Detailstatus in "status: ready" (siehe simulation_prepare.py).
                # Schlaegt die Persistierung fehl, waere das ein Ready-Signal
                # ohne persistierten Ready-Zustand. Deshalb wird hier erst
                # persistiert und nur bei Erfolg ein positives Ergebnis
                # gemeldet; der Fehlerfall wird als "nicht vorbereitet"
                # zurueckgegeben statt still verschluckt.
                from datetime import datetime

                promoted = dict(state_data)
                promoted["status"] = "ready"
                promoted["updated_at"] = datetime.now().isoformat()
                try:
                    store.write_json(simulation_id, "state", promoted)
                except Exception as exc:  # noqa: BLE001 — Storefehler sind nicht typisiert
                    logger.error(
                        f"Failed to persist auto status update for {simulation_id}: {exc}"
                    )
                    return False, {
                        "reason": f"Failed to persist ready state: {exc}",
                        "status": status,
                        "config_generated": config_generated,
                    }
                logger.info(f"Auto update simulation status: {simulation_id} preparing -> ready")
                state_data = promoted
                status = "ready"

            logger.info(
                f"Simulation {simulation_id} Detection result: HasPreparation complete (status={status}, config_generated={config_generated})"
            )
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files,
            }

        logger.warning(
            f"Simulation {simulation_id} Detection result: Has notPreparation complete (status={status}, config_generated={config_generated})"
        )
        return False, {
            "reason": (
                "Status not in prepared list or config_generated is false: "
                f"status={status}, config_generated={config_generated}"
            ),
            "status": status,
            "config_generated": config_generated,
        }

    except Exception as exc:  # noqa: BLE001 — exc used in response payload
        return False, {"reason": f"Failed to read state file: {str(exc)}"}
