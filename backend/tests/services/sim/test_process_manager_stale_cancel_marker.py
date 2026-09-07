"""Regression: stale cancel_abort.json darf einen Neustart nicht als
user_stop einfärben (Codex-Review PR #1474, P1).

``stop_simulation`` schreibt seit PR #1474 first-writer-wins einen
Nutzer-Stop-Marker (``cancel_abort.json``) ins sim_dir. Diese Datei wird
nirgends aufgeräumt und liegt persistent im Simulationsverzeichnis. Wird
dieselbe ``simulation_id`` erneut gestartet, muss ``start_simulation`` den
alten Marker entfernen — sonst liest der neue Monitor den ALTEN Marker und
klassifiziert einen sauberen Exit-0-Lauf fälschlich als ``stopped``/
``user_stop``.
"""

from __future__ import annotations

import json
import os

from unittest.mock import MagicMock


from app.services.sim import process_manager
from app.services.sim.process_manager import CANCEL_ABORT_FILENAME, _clear_cancel_abort


class TestClearCancelAbort:
    def test_removes_existing_marker(self, tmp_path):
        sim_dir = tmp_path / "sim_with_marker"
        sim_dir.mkdir()
        marker_path = sim_dir / CANCEL_ABORT_FILENAME
        marker_path.write_text(
            json.dumps({"source": "user_stop", "ts": 123.0}), encoding="utf-8"
        )

        _clear_cancel_abort(str(sim_dir))

        assert not marker_path.exists()

    def test_no_op_when_no_marker(self, tmp_path):
        """Kein Marker vorhanden — kein Fehler, kein Effekt."""
        sim_dir = tmp_path / "sim_without_marker"
        sim_dir.mkdir()

        # Darf keine Exception werfen.
        _clear_cancel_abort(str(sim_dir))

        assert not (sim_dir / CANCEL_ABORT_FILENAME).exists()

    def test_removes_orphaned_tmp_file(self, tmp_path):
        """Eine verwaiste .tmp-Datei (First-Writer-Wins-Artefakt) wird ebenfalls entfernt."""
        sim_dir = tmp_path / "sim_with_tmp"
        sim_dir.mkdir()
        tmp_marker = sim_dir / f"{CANCEL_ABORT_FILENAME}.tmp"
        tmp_marker.write_text("{}", encoding="utf-8")

        _clear_cancel_abort(str(sim_dir))

        assert not tmp_marker.exists()


class TestStartSimulationClearsStaleMarker:
    def test_start_simulation_removes_stale_cancel_abort(self, tmp_path, monkeypatch):
        """Regression: cancel_abort.json aus einem frueheren user_stop
        darf beim naechsten start_simulation nicht ueberleben."""
        script_path = tmp_path / "run_parallel_simulation.py"
        script_path.write_text("print('ok')\n", encoding="utf-8")
        sim_dir = tmp_path / "sim_stale_marker"
        sim_dir.mkdir()
        (sim_dir / "simulation_config.json").write_text("{}", encoding="utf-8")

        marker_path = sim_dir / CANCEL_ABORT_FILENAME
        marker_path.write_text(
            json.dumps({"source": "user_stop", "ts": 1.0}), encoding="utf-8"
        )

        class FakeProcess:
            pid = 99999

        def fake_popen(*args, **kwargs):
            # Zum Zeitpunkt des Spawns muss der Marker bereits weg sein.
            assert not marker_path.exists()
            return FakeProcess()

        monkeypatch.setattr(process_manager.subprocess, "Popen", fake_popen)

        process_manager.start_simulation(
            "sim_stale_marker",
            "parallel",
            run_state_dir=str(tmp_path),
            scripts_dir=str(tmp_path),
            processes={},
            action_queues={},
            monitor_threads={},
            stdout_files={},
            stderr_files={},
            graph_memory_enabled={},
            get_run_state=lambda _: None,
            save_state=MagicMock(),
            on_monitor_start=MagicMock(),
            write_control_state=MagicMock(),
            get_config=lambda _: {
                "time_config": {
                    "total_simulation_hours": 1,
                    "minutes_per_round": 60,
                }
            },
            config_exists=lambda _: True,
            setup_graph_memory=MagicMock(),
        )

        assert not marker_path.exists()
        assert not os.path.exists(str(marker_path) + ".tmp")
