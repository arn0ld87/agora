"""GitHub-Copilot-Token-Resolver.

GitHub Copilot benutzt keinen klassischen API-Key, sondern einen OAuth-Token
aus der GitHub-CLI-Session (``gh auth login``). Dieser Resolver ruft
``gh auth token`` als Subprozess und gibt den Klartext-Token zurück.

Phase 1 — Modell-Discovery:
    Die ``/v1/models``-Antwort des Copilot-Backends ist instabil (Endpoint
    wechselt, Auth-Flow nicht öffentlich dokumentiert). Daher liefern wir
    in Phase 1 eine statische Liste. Sobald der API-Pfad gefestigt ist,
    kann ``fetch_live_models`` den Endpoint anbinden.

Security:
    Der Resolver loggt NIE den Token-Wert. Bei Erfolg geht nur eine Info-Zeile
    mit der Token-Länge raus.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
import threading
from typing import Optional

logger = logging.getLogger("agora.llm.github_copilot")

# Phase-1 statische Modellliste. Kann jederzeit ergänzt werden.
GITHUB_COPILOT_MODELS: tuple[str, ...] = (
    "gpt-4o-copilot",
    "gpt-4o-mini-copilot",
    "claude-sonnet-4.5-copilot",
    "o1-mini-copilot",
)

GITHUB_COPILOT_BASE_URL = "https://api.githubcopilot.com"

# Token-Cache: vermeidet wiederholte subprocess-Spawns (Gemini MEDIUM #3).
# TTL 300 s — kurz genug um Token-Rotationen zu erfassen, lang genug um
# den Overhead bei Per-Request-Auflösung zu vermeiden.
_TOKEN_CACHE_TTL: float = 300.0
_token_cache: Optional[str] = None
_token_cache_ts: float = 0.0
_token_cache_lock = threading.Lock()


def resolve_copilot_token(timeout_seconds: float = 3.0) -> Optional[str]:
    """Resolve a GitHub Copilot token via ``gh auth token``.

    Ergebnis wird für ``_TOKEN_CACHE_TTL`` Sekunden gecacht, um wiederholte
    subprocess-Spawns zu vermeiden (Gemini MEDIUM #3).

    Returns
    -------
    Optional[str]
        Token-String, oder ``None`` wenn ``gh`` nicht installiert ist bzw.
        der User nicht angemeldet ist. Niemals ein leerer String.
    """
    global _token_cache, _token_cache_ts

    now = time.monotonic()
    with _token_cache_lock:
        if _token_cache is not None and (now - _token_cache_ts) < _TOKEN_CACHE_TTL:
            return _token_cache

    token = _resolve_copilot_token_uncached(timeout_seconds)

    with _token_cache_lock:
        _token_cache = token
        _token_cache_ts = time.monotonic()

    return token


def _resolve_copilot_token_uncached(timeout_seconds: float) -> Optional[str]:
    """Interner uncached Resolver — nicht direkt aufrufen."""
    gh_path = shutil.which("gh")
    if gh_path is None:
        logger.debug("`gh` CLI nicht im PATH — Copilot-Token nicht auflösbar")
        return None
    try:
        proc = subprocess.run(
            [gh_path, "auth", "token"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("`gh auth token` hat das Timeout (%.1fs) überschritten", timeout_seconds)
        return None
    except OSError as exc:
        logger.warning("`gh auth token` konnte nicht ausgeführt werden: %s", exc)
        return None

    if proc.returncode != 0:
        logger.info("`gh auth token` non-zero exit (%s): %s", proc.returncode, proc.stderr.strip())
        return None

    token = proc.stdout.strip()
    if not token:
        return None
    logger.info("GitHub-Copilot-Token aufgelöst (len=%d)", len(token))
    return token


def clear_token_cache() -> None:
    """Nur für Tests — leert den Token-Cache."""
    global _token_cache, _token_cache_ts
    with _token_cache_lock:
        _token_cache = None
        _token_cache_ts = 0.0
