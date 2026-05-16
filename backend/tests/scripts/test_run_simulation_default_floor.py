"""
Slice 4 — Simulation-Floor-Tests (Issue #496).

Kein Subprocess-Spawn. Argparse-Defaults werden via Regex aus den
Script-Source-Dateien verifiziert; _validate_persona_quota wird direkt
als Unit-Test aufgerufen.
"""

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Pfade
# ---------------------------------------------------------------------------

_BACKEND = Path(__file__).resolve().parent.parent.parent  # backend/
_SIM_COMMON = _BACKEND / "scripts" / "_sim_common.py"
_REDDIT_SCRIPT = _BACKEND / "scripts" / "run_reddit_simulation.py"
_TWITTER_SCRIPT = _BACKEND / "scripts" / "run_twitter_simulation.py"


# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------

def _extract_default_from_sim_common(flag: str) -> int:
    """Extrahiert den ``default``-Wert eines argparse-Arguments aus _sim_common.py.

    Sucht nach dem Muster::

        "--num-agents",   (oder "--num-rounds")
        ...
        default=<N>,

    Innerhalb desselben add_argument-Blocks.
    """
    src = _SIM_COMMON.read_text(encoding="utf-8")
    # Suche den add_argument-Block, der den gesuchten Flag enthält, und lese
    # danach das erste ``default = <int>`` aus (innerhalb von ~300 Zeichen).
    m = re.search(
        rf'"{re.escape(flag)}"[\s\S]{{0,300}}?default\s*=\s*(\d+)',
        src,
    )
    assert m, f"{flag} default not found in {_SIM_COMMON}"
    return int(m.group(1))


def _extract_default_from_script(path: Path, flag: str) -> int:
    """Fallback: extrahiert Default direkt aus einem Script (falls es das
    Argument eigenständig definiert statt _sim_common zu nutzen)."""
    src = path.read_text(encoding="utf-8")
    m = re.search(
        rf'"{re.escape(flag)}"[\s\S]{{0,300}}?default\s*=\s*(\d+)',
        src,
    )
    assert m, f"{flag} default not found in {path}"
    return int(m.group(1))


# ---------------------------------------------------------------------------
# Tests: Argparse-Defaults (über _sim_common.py verifiziert)
# ---------------------------------------------------------------------------


class TestArgparseDefaults:
    """Verifiziert, dass build_single_platform_parser --num-agents=30 und
    --num-rounds=10 als Default-Werte setzt."""

    def test_reddit_num_agents_default(self) -> None:
        val = _extract_default_from_sim_common("--num-agents")
        assert val == 30, (
            f"run_reddit_simulation.py (via _sim_common): "
            f"--num-agents default ist {val}, erwartet 30 (Slice 4 Floor)"
        )

    def test_reddit_num_rounds_default(self) -> None:
        val = _extract_default_from_sim_common("--num-rounds")
        assert val == 10, (
            f"run_reddit_simulation.py (via _sim_common): "
            f"--num-rounds default ist {val}, erwartet 10 (Slice 4 Floor)"
        )

    def test_twitter_num_agents_default(self) -> None:
        # Twitter nutzt ebenfalls build_single_platform_parser aus _sim_common.
        # Der Wert ist identisch — wir prüfen hier explizit, dass das Script
        # selbst KEINEN eigenen Override definiert.
        src = _TWITTER_SCRIPT.read_text(encoding="utf-8")
        # Script darf keinen eigenen --num-agents-Block mit anderem Default setzen.
        own_override = re.search(
            r'"--num-agents"[\s\S]{0,200}?default\s*=\s*(?!30)(\d+)',
            src,
        )
        assert own_override is None, (
            "run_twitter_simulation.py überschreibt --num-agents default mit "
            f"{own_override.group(1) if own_override else '?'}, erwartet keinen Override"
        )
        # Wert aus _sim_common muss 30 sein (bereits durch test_reddit_* geprüft).
        val = _extract_default_from_sim_common("--num-agents")
        assert val == 30

    def test_twitter_num_rounds_default(self) -> None:
        src = _TWITTER_SCRIPT.read_text(encoding="utf-8")
        own_override = re.search(
            r'"--num-rounds"[\s\S]{0,200}?default\s*=\s*(?!10)(\d+)',
            src,
        )
        assert own_override is None, (
            "run_twitter_simulation.py überschreibt --num-rounds default mit "
            f"{own_override.group(1) if own_override else '?'}, erwartet keinen Override"
        )
        val = _extract_default_from_sim_common("--num-rounds")
        assert val == 10


# ---------------------------------------------------------------------------
# Tests: _validate_persona_quota
# ---------------------------------------------------------------------------


class TestValidatePersonaQuota:
    """Unit-Tests für SimulationConfigGenerator._validate_persona_quota."""

    @pytest.fixture(autouse=True)
    def _import_validator(self):
        from app.services.simulation_config_generator import SimulationConfigGenerator  # noqa: PLC0415
        self.validate = SimulationConfigGenerator._validate_persona_quota

    def test_raises_for_25_personas_without_env_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGORA_ALLOW_SMALL_SIM", raising=False)
        personas = list(range(25))
        with pytest.raises(ValueError, match="Simulation-Floor"):
            self.validate(personas)

    def test_passes_for_25_personas_with_env_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGORA_ALLOW_SMALL_SIM", "1")
        personas = list(range(25))
        # Darf keine Exception werfen.
        self.validate(personas)

    def test_passes_for_exactly_30_personas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGORA_ALLOW_SMALL_SIM", raising=False)
        personas = list(range(30))
        self.validate(personas)  # kein Raise erwartet

    def test_passes_for_more_than_30_personas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGORA_ALLOW_SMALL_SIM", raising=False)
        personas = list(range(50))
        self.validate(personas)  # kein Raise erwartet
