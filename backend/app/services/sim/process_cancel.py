"""Persistent cancel-marker handling for simulation subprocesses."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ...utils.logger import get_logger

logger = get_logger("agora.process_manager")

CANCEL_ABORT_FILENAME = "cancel_abort.json"

def _read_cancel_abort(sim_dir: str) -> Optional[Dict[str, Any]]:
    """cancel_abort.json lesen (vom Monitor bei konsumiertem Cancel-Flag oder von
    stop_simulation bei einem Nutzer-Stop geschrieben).

    Beheimatet in process_manager.py statt monitor.py (Review-Fix B2,
    2026-09-07): monitor.py importiert bereits lazy aus process_manager
    (``terminate_run`` in ``_cancel_supervision``) — ein Re-Import in
    Gegenrichtung haette einen Modul-Zyklus erzeugt.
    """
    import json

    path = os.path.join(sim_dir, CANCEL_ABORT_FILENAME)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_cancel_abort(sim_dir: str, abort_info: Dict[str, Any]) -> None:
    """First-writer-wins — analog zu ``_write_budget_abort`` in monitor.py."""
    import json

    path = os.path.join(sim_dir, CANCEL_ABORT_FILENAME)
    if os.path.exists(path):
        return
    try:
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(abort_info, handle)
            handle.write("\n")
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.warning("cancel abort marker write failed: %s", exc)


def _clear_cancel_abort(sim_dir: str) -> None:
    """Stale ``cancel_abort.json`` (und eine evtl. verwaiste ``.tmp``-Datei)
    vor einem Neustart entfernen — idempotent (Codex-Review PR #1474).

    ``_write_cancel_abort`` ist first-writer-wins und ``cancel_abort.json``
    liegt persistent im sim_dir. Wird dieselbe ``simulation_id`` nach einem
    Nutzer-Stop erneut gestartet, liest der neue Monitor sonst den ALTEN
    Marker und klassifiziert einen sauberen Exit-0-Lauf faelschlich als
    ``stopped``/``user_stop``. Aufruf in ``start_simulation`` VOR dem
    Subprozess-Spawn beseitigt das.
    """
    path = os.path.join(sim_dir, CANCEL_ABORT_FILENAME)
    tmp_path = f"{path}.tmp"
    for candidate in (path, tmp_path):
        try:
            os.remove(candidate)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("cancel abort marker cleanup failed: %s", exc)
