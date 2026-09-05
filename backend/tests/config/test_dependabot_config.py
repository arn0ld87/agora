"""Waechter fuer .github/dependabot.yml.

Das Frontend-Update muss ueber das ``bun``-Oekosystem laufen. Das fruehere
``npm``-Oekosystem aktualisierte nur ``package.json`` und liess ``bun.lock``
stehen; der Frontend-Smoke-Gate (``bun install --frozen-lockfile``) brach dann
mit "lockfile had changes, but lockfile is frozen" ab (#1314, #1170, #1428).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPENDABOT_CONFIG = REPO_ROOT / ".github" / "dependabot.yml"
FRONTEND_LOCKFILE = REPO_ROOT / "frontend" / "bun.lock"


def _frontend_update_entry() -> dict[str, Any]:
    config = yaml.safe_load(DEPENDABOT_CONFIG.read_text(encoding="utf-8"))
    entries = [entry for entry in config["updates"] if entry.get("directory") == "/frontend"]
    assert len(entries) == 1, f"genau ein /frontend-Eintrag erwartet, gefunden: {len(entries)}"
    return entries[0]


def test_frontend_dependabot_uses_bun_ecosystem() -> None:
    entry = _frontend_update_entry()
    assert entry["package-ecosystem"] == "bun", (
        "Frontend-Updates muessen ueber das bun-Oekosystem laufen, sonst bleibt "
        "bun.lock stehen und der Frontend-Smoke-Gate bricht am Frozen-Lockfile ab"
    )


def test_frontend_lockfile_is_text_based_bun_lock() -> None:
    """Das bun-Oekosystem pflegt nur die textbasierte bun.lock, nicht bun.lockb."""
    assert FRONTEND_LOCKFILE.is_file(), "frontend/bun.lock fehlt"
    assert not (REPO_ROOT / "frontend" / "bun.lockb").exists(), (
        "binaeres bun.lockb gefunden; Dependabot kann nur die Text-Variante pflegen"
    )
