"""Subprocess environment, path and OASIS database helpers.

Extracted from process_manager; no lifecycle state is owned here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from ...llm.providers.codex_cli import CLI_TRANSPORT_VALUE, TRANSPORT_ENV_KEY

SAFE_ENV_KEYS: frozenset[str] = frozenset(
    {
        "PATH", "PYTHONPATH", "PYTHONUTF8", "PYTHONIOENCODING", "TZ",
        "LLM_BASE_URL", "LLM_MODEL_NAME", "LLM_MAX_OUTPUT_TOKENS",
        "OLLAMA_THINKING", "REDIS_URL", "HF_TOKEN",
        "AGORA_CODEX_CLI_BIN", "AGORA_CODEX_CLI_TIMEOUT_SECONDS",
    }
)

_OASIS_DB_DIR_NAME = "oasis_db"
_OASIS_DB_FILE_NAME = "social_media.db"

def _resolve_child_path(base_dir: str, child_name: str, *, kind: str) -> Path:
    base = Path(base_dir).expanduser().resolve()
    child = (base / child_name).resolve()
    try:
        child.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Invalid {kind} path") from exc
    return child


def _build_subprocess_env(
    runtime_env: Optional[Dict[str, str]], sim_dir: Any
) -> Dict[str, str]:
    """Env für den OASIS-Subprozess — Whitelist-only (Code-Review 2026-05-17 §1.6).

    Nur explizit erlaubte Keys aus ``os.environ``; Secrets wie SECRET_KEY,
    AGORA_AUTH_TOKEN oder NEO4J_PASSWORD werden bewusst NICHT vererbt.
    ``runtime_env``-Werte kommen immer mit und überschreiben Whitelist-Werte
    (enthält u. a. LLM_API_KEY und OPENAI_API_KEY für den Subprozess).

    Aus ``start_simulation`` extrahiert, als der CLI-Sonderfall unten die
    Funktion über das radon-Gate (MAI-17) gehoben hätte.
    """
    env = {k: v for k, v in os.environ.items() if k in SAFE_ENV_KEYS}
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if runtime_env:
        env.update({k: v for k, v in runtime_env.items() if v})
    # Issue #1423: Bei CLI-Transport (codex_cli) darf das aus der Whitelist
    # geerbte ``LLM_BASE_URL`` NICHT stehen bleiben. Der Provider hat keinen
    # HTTP-Endpunkt; das geerbte Feld ist die ``.env``-URL des Backends, und
    # der Subprozess schickte das geroutete Modell genau dorthin (beobachtet:
    # ``gpt-5.6-luna`` an ``api.minimax.io`` → HTTP 400 (2013)). Das Signal
    # setzt ``build_route_subprocess_env`` anhand von
    # ``ProviderConnectionDefinition.transport``.
    if env.get(TRANSPORT_ENV_KEY, "").strip().lower() == CLI_TRANSPORT_VALUE:
        env.pop("LLM_BASE_URL", None)
    # Sub-Slice 21: OASIS-DB pro Sim ins schreibbare uploads/-Volume
    _inject_oasis_db_env(env, str(sim_dir))
    return env


def _compute_oasis_db_path(sim_dir: str) -> str:
    """Liefert ``<sim_dir>/oasis_db/social_media.db`` und legt das
    Verzeichnis an (idempotent). OASIS' ``get_db_path()`` macht **kein**
    ``mkdir``, wenn ``OASIS_DB_PATH``-ENV gesetzt ist — das Verzeichnis
    muss vorhanden sein, bevor der Subprozess startet."""
    db_dir = os.path.join(sim_dir, _OASIS_DB_DIR_NAME)
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, _OASIS_DB_FILE_NAME)


def _inject_oasis_db_env(env: Dict[str, str], sim_dir: str) -> None:
    """Setzt ``OASIS_DB_PATH`` im Subprozess-Env auf einen sim-spezifischen
    Pfad — aber nur, wenn der User es nicht selbst überschrieben hat
    (z. B. via Compose-Env oder ``.env``)."""
    if env.get("OASIS_DB_PATH"):
        return
    env["OASIS_DB_PATH"] = _compute_oasis_db_path(sim_dir)
