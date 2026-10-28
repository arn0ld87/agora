"""Workspace credential scope detection, secret injection via FD pipe, and simulation RNG seeding."""

import hashlib
import json
import logging
import os
import random
from typing import Any

logger = logging.getLogger("agora.sim")

_PAYLOAD_FD_ENV_NAME = "AGORA_SECRET_ENV_FD"
_CREDENTIAL_SCOPE_ENV_KEY = "AGORA_CREDENTIAL_SCOPE"
_WORKSPACE_CREDENTIAL_SCOPE = "workspace"
_BOOST_ENV_KEYS = ("LLM_BOOST_API_KEY", "LLM_BOOST_BASE_URL", "LLM_BOOST_MODEL_NAME")
_REQUIRED_WORKSPACE_ENV_NAME = "LLM_API_KEY"


def is_workspace_credential_scope() -> bool:
    """Whether this subprocess belongs to a workspace-scoped run."""
    return os.environ.get(_CREDENTIAL_SCOPE_ENV_KEY) == _WORKSPACE_CREDENTIAL_SCOPE


def _fail_closed(message: str) -> None:
    """Exit non-zero with a secret-free message."""
    logger.error(message)
    raise SystemExit(f"agora.sim: {message}")


def load_workspace_secret_env_from_fd() -> None:
    """Liest ein via Pipe-FD uebergebenes Workspace-Secret ins Prozess-Env."""
    workspace_scoped = is_workspace_credential_scope()
    if workspace_scoped:
        for key in _BOOST_ENV_KEYS:
            os.environ.pop(key, None)

    fd_value = os.environ.pop(_PAYLOAD_FD_ENV_NAME, None)
    if not fd_value:
        if workspace_scoped:
            _fail_closed(
                f"workspace-scoped run has no {_PAYLOAD_FD_ENV_NAME} — "
                "refusing to start without a workspace credential"
            )
        return
    try:
        fd = int(fd_value)
    except ValueError:
        if workspace_scoped:
            _fail_closed(f"{_PAYLOAD_FD_ENV_NAME} ist keine gueltige FD-Nummer")
        logger.warning(
            "load_workspace_secret_env_from_fd: %s ist keine gueltige FD-Nummer",
            _PAYLOAD_FD_ENV_NAME,
        )
        return
    chunks: list[bytes] = []
    try:
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
    except OSError:
        if workspace_scoped:
            _fail_closed(f"FD {fd} (workspace credential pipe) nicht lesbar")
        logger.warning(
            "load_workspace_secret_env_from_fd: FD %s nicht lesbar", fd
        )
        return
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    if not chunks:
        if workspace_scoped:
            _fail_closed("leere Workspace-Credential-Payload")
        return
    try:
        secrets = json.loads(b"".join(chunks).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        if workspace_scoped:
            _fail_closed("Workspace-Credential-Payload nicht als JSON lesbar")
        logger.warning(
            "load_workspace_secret_env_from_fd: Payload nicht als JSON lesbar"
        )
        return
    if not isinstance(secrets, dict):
        if workspace_scoped:
            _fail_closed("Workspace-Credential-Payload ist kein JSON-Objekt")
        return
    if workspace_scoped and _REQUIRED_WORKSPACE_ENV_NAME not in secrets:
        _fail_closed(
            f"Workspace-Credential-Payload enthaelt kein {_REQUIRED_WORKSPACE_ENV_NAME}"
        )
    os.environ.update({str(k): str(v) for k, v in secrets.items()})


SIMULATION_SEED_CONFIG_KEY = "random_seed"
_SEED_MODULUS = 2**32


def derive_simulation_seed(config: dict[str, Any], *, fallback: str = "") -> int:
    """Bestimmt den Seed eines Laufs — vorgegeben oder aus der Lauf-ID abgeleitet."""
    raw = config.get(SIMULATION_SEED_CONFIG_KEY)
    if raw is not None and not isinstance(raw, bool):
        try:
            return int(raw) % _SEED_MODULUS
        except (TypeError, ValueError):
            pass

    identity = str(config.get("simulation_id") or fallback or "agora-simulation")
    digest = hashlib.sha256(identity.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def seed_simulation_rng(config: dict[str, Any], *, fallback: str = "") -> int:
    """Seedet den globalen random-Zustand des Subprozesses und gibt den Seed zurueck."""
    seed = derive_simulation_seed(config, fallback=fallback)
    random.seed(seed)
    return seed
