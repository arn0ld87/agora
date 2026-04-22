"""
Shared helpers for locating simulation and report artifacts on disk.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ..config import Config


class ArtifactLocator:
    @staticmethod
    def uploads_dir() -> str:
        return Config.UPLOAD_FOLDER

    @staticmethod
    def simulations_dir() -> str:
        return os.path.join(Config.UPLOAD_FOLDER, "simulations")

    @staticmethod
    def reports_dir() -> str:
        return os.path.join(Config.UPLOAD_FOLDER, "reports")

    @classmethod
    def simulation_dir(cls, simulation_id: str) -> str:
        return os.path.join(cls.simulations_dir(), simulation_id)

    @classmethod
    def report_dir(cls, report_id: str) -> str:
        return os.path.join(cls.reports_dir(), report_id)

    @classmethod
    def simulation_file(cls, simulation_id: str, filename: str) -> str:
        return os.path.join(cls.simulation_dir(simulation_id), filename)

    @classmethod
    def report_file(cls, report_id: str, filename: str) -> str:
        return os.path.join(cls.report_dir(report_id), filename)

    @classmethod
    def simulation_artifacts(cls, simulation_id: str) -> Dict[str, Optional[str]]:
        sim_dir = cls.simulation_dir(simulation_id)
        return {
            "simulation_dir": sim_dir,
            "state": cls.simulation_file(simulation_id, "state.json"),
            "config": cls.simulation_file(simulation_id, "simulation_config.json"),
            "run_state": cls.simulation_file(simulation_id, "run_state.json"),
            "control_state": cls.simulation_file(simulation_id, "control_state.json"),
            "reddit_profiles": cls.simulation_file(simulation_id, "reddit_profiles.json"),
            "twitter_profiles": cls.simulation_file(simulation_id, "twitter_profiles.csv"),
            "simulation_log": cls.simulation_file(simulation_id, "simulation.log"),
        }

    @classmethod
    def report_artifacts(cls, report_id: str) -> Dict[str, Optional[str]]:
        report_dir = cls.report_dir(report_id)
        return {
            "report_dir": report_dir,
            "meta": cls.report_file(report_id, "meta.json"),
            "outline": cls.report_file(report_id, "outline.json"),
            "progress": cls.report_file(report_id, "progress.json"),
            "markdown": cls.report_file(report_id, "full_report.md"),
            "agent_log": cls.report_file(report_id, "agent_log.jsonl"),
            "console_log": cls.report_file(report_id, "console_log.txt"),
            "evidence_map": cls.report_file(report_id, "evidence_map.json"),
        }

    @staticmethod
    def existing_paths(artifacts: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in artifacts.items():
            if isinstance(value, dict):
                nested = ArtifactLocator.existing_paths(value)
                if nested:
                    result[key] = nested
                continue
            if value and os.path.exists(value):
                result[key] = value
        return result
