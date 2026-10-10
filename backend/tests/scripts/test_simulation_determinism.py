"""Issue #1160 F — der stochastische Anteil eines Laufs ist reproduzierbar.

Der Simulationslauf traf seine Zufallsentscheidungen aus dem globalen,
ungeseedeten ``random``-Zustand: wie viele Agenten pro Runde aktiv werden
(``random.uniform``), welche davon überhaupt in Frage kommen
(``random.random`` gegen das Aktivitätsniveau) und welche schließlich gezogen
werden (``random.sample``). Zwei Läufe derselben Konfiguration waren damit
nicht vergleichbar — und ohne Vergleichbarkeit ist jeder Re-Run und jede
Baseline-Messung methodisch angreifbar. Einzige geseedete Insel war
``louvain_communities(..., seed=42)`` in der Netzwerkanalyse.

**Was diese Tests zusichern und was nicht.** Reproduzierbar wird der
stochastische Anteil des Laufs. Die Antworten der Sprachmodelle bleiben
nichtdeterministisch — gleicher Seed bedeutet also *nicht* gleicher Report.
Wer identische Berichte braucht, braucht zusätzlich die Aufzeichnung der
LLM-Antworten; das ist ein eigener Slice (#763). Ein Test, der „gleicher Seed
→ gleicher Report" behauptete, würde etwas zusichern, das die Architektur
nicht hergibt.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _sim_common import (  # noqa: E402
    SIMULATION_SEED_CONFIG_KEY,
    derive_simulation_seed,
    seed_simulation_rng,
)


class TestSeedDerivation:
    def test_same_simulation_id_yields_the_same_seed(self) -> None:
        """Derselbe Lauf ergibt beim Neustart denselben Seed."""
        config = {"simulation_id": "sim_0123456789ab"}
        assert derive_simulation_seed(config) == derive_simulation_seed(dict(config))

    def test_different_simulation_ids_yield_different_seeds(self) -> None:
        """Sonst wären verschiedene Läufe untereinander nicht unterscheidbar."""
        first = derive_simulation_seed({"simulation_id": "sim_0123456789ab"})
        second = derive_simulation_seed({"simulation_id": "sim_ba9876543210"})
        assert first != second

    def test_the_seed_survives_a_process_restart(self) -> None:
        """Der abgeleitete Seed darf nicht an ``hash()`` hängen.

        Pythons String-Hash ist pro Prozess zufällig gesalzen
        (``PYTHONHASHSEED``). Ein darauf gebauter Seed wäre das Gegenteil von
        reproduzierbar — und der Fehler fiele im selben Prozess nicht auf.
        Deshalb hier ein zweiter Prozess mit abweichendem Salt.
        """
        import subprocess

        code = (
            "from _sim_common import derive_simulation_seed;"
            "print(derive_simulation_seed({'simulation_id': 'sim_0123456789ab'}))"
        )
        seeds = set()
        for hash_seed in ("1", "12345"):
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=_SCRIPTS_DIR,
                capture_output=True,
                text=True,
                env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": hash_seed},
                timeout=60,
            )
            assert result.returncode == 0, result.stderr
            seeds.add(result.stdout.strip())

        assert len(seeds) == 1, (
            f"Der Seed haengt am prozess-lokalen String-Hash: {seeds}. "
            "Damit waere er zwischen zwei Laeufen verschieden."
        )
        assert seeds.pop() == str(
            derive_simulation_seed({"simulation_id": "sim_0123456789ab"})
        )

    def test_an_explicit_seed_wins_over_the_derivation(self) -> None:
        """Der Weg, einen Lauf gezielt zu wiederholen."""
        config = {"simulation_id": "sim_0123456789ab", SIMULATION_SEED_CONFIG_KEY: 4711}
        assert derive_simulation_seed(config) == 4711

    @pytest.mark.parametrize("unusable", [None, "keine-zahl", [], {}, True])
    def test_an_unusable_seed_falls_back_to_the_derivation(self, unusable: object) -> None:
        """Ein kaputtes Feld darf den Lauf nicht abbrechen — und nicht stillschweigend
        alle Läufe auf denselben Seed ziehen.

        ``True`` ist ausdrücklich mitgeprüft: in Python ist ``bool`` ein
        ``int``, ein ``random_seed: true`` aus einer handgeschriebenen Config
        würde sonst als Seed 1 durchgehen.
        """
        derived = derive_simulation_seed({"simulation_id": "sim_0123456789ab"})
        config = {
            "simulation_id": "sim_0123456789ab",
            SIMULATION_SEED_CONFIG_KEY: unusable,
        }
        assert derive_simulation_seed(config) == derived

    def test_a_config_without_any_identity_still_yields_a_seed(self) -> None:
        assert isinstance(derive_simulation_seed({}), int)
        assert derive_simulation_seed({}, fallback="sim_dir_name") != derive_simulation_seed({})


class TestSeededRoundsRepeat:
    """Der eigentliche Nachweis: dieselbe Konfiguration, dieselbe Auswahl."""

    @staticmethod
    def _draw_rounds(config: dict, rounds: int = 5) -> list[list[int]]:
        """Bildet die Zufallsentscheidungen von ``get_active_agents_for_round`` nach.

        Nachgebildet statt aufgerufen, weil die echte Funktion eine
        OASIS-Umgebung braucht (``env.agent_graph``). Entscheidend ist die
        Reihenfolge der ``random``-Aufrufe — und die ist hier dieselbe:
        ``uniform`` für die Zielanzahl, ``random`` je Kandidat, ``sample`` für
        die Auswahl.
        """
        seed_simulation_rng(config)
        drawn: list[list[int]] = []
        for _ in range(rounds):
            target = int(random.uniform(5, 20) * 1.5)
            candidates = [i for i in range(40) if random.random() < 0.5]
            drawn.append(sorted(random.sample(candidates, min(target, len(candidates)))))
        return drawn

    def test_same_config_yields_the_same_activation_sequence(self) -> None:
        config = {"simulation_id": "sim_0123456789ab"}
        assert self._draw_rounds(config) == self._draw_rounds(dict(config))

    def test_a_different_run_yields_a_different_sequence(self) -> None:
        """Gegenprobe: der Seed darf die Simulation nicht auf eine feste Abfolge
        festnageln, die für jeden Lauf gleich ist."""
        first = self._draw_rounds({"simulation_id": "sim_0123456789ab"})
        second = self._draw_rounds({"simulation_id": "sim_ba9876543210"})
        assert first != second

    def test_an_explicit_seed_reproduces_another_runs_sequence(self) -> None:
        """Der praktische Fall: einen Lauf wiederholen, indem man seinen Seed
        in die Konfiguration des neuen Laufs schreibt."""
        original = {"simulation_id": "sim_0123456789ab"}
        seed = derive_simulation_seed(original)

        replay = {"simulation_id": "sim_voelligandereid", SIMULATION_SEED_CONFIG_KEY: seed}

        assert self._draw_rounds(replay) == self._draw_rounds(original)


def test_seeding_returns_the_seed_it_applied() -> None:
    """Der Rückgabewert wird protokolliert — er ist die Angabe, mit der sich der
    Lauf wiederholen lässt. Ein falscher Wert wäre schlimmer als keiner."""
    config = {"simulation_id": "sim_0123456789ab"}
    applied = seed_simulation_rng(config)
    assert applied == derive_simulation_seed(config)

    random.seed(applied)
    expected = [random.random() for _ in range(3)]
    seed_simulation_rng(config)
    assert [random.random() for _ in range(3)] == expected


class _FirstKRng:
    """Deterministische Ziehung: alle sind Kandidat, ``sample`` nimmt die ersten ``k``."""

    def uniform(self, a: float, b: float) -> float:
        return b

    def random(self) -> float:
        return 0.0

    def sample(self, population, k: int):
        return list(population)[:k]


_LEGACY_TIME_CONFIG = {
    "agents_per_hour_min": 4,
    "agents_per_hour_max": 4,
    "peak_hours": [],
    "off_peak_hours": [],
}


def _legacy_agent_configs(count: int = 6) -> list[dict]:
    return [{"agent_id": i, "activity_level": 1.0, "active_hours": list(range(24))} for i in range(count)]


def test_legacy_selection_skips_ids_without_agent() -> None:
    """#1779: ``target_count`` wird nicht von Agenten ohne OASIS-Agent verbraucht.

    Der Altpfad zog früher aus ALLEN Konfigurationen und verwarf nicht
    auflösbare IDs erst danach (Runner: ``except Exception: pass``). Mit den
    IDs 1 und 4 ohne Agent blieben von der Zielzahl 4 nur 2 übrig.
    """
    from app.services import simulation_activity_policy as policy

    existing = {0, 2, 3, 5}

    selected = policy.select_active_agent_ids(
        _LEGACY_TIME_CONFIG, _legacy_agent_configs(), 12, _FirstKRng(), existing
    )

    assert selected == [0, 2, 3, 5]


def test_legacy_selection_without_existing_ids_is_unchanged() -> None:
    from app.services import simulation_activity_policy as policy

    selected = policy.select_active_agent_ids(
        _LEGACY_TIME_CONFIG, _legacy_agent_configs(), 12, _FirstKRng()
    )

    assert selected == [0, 1, 2, 3]


def test_missing_agents_are_logged_once_per_set() -> None:
    from app.services import simulation_activity_policy as policy

    policy._REPORTED_MISSING_AGENTS.clear()
    for _ in range(3):
        policy.select_active_agent_ids(
            _LEGACY_TIME_CONFIG, _legacy_agent_configs(), 12, _FirstKRng(), {0, 2, 3, 5}
        )

    assert policy._REPORTED_MISSING_AGENTS == {(1, 4)}


class _Graph:
    def __init__(self, ids: list[int]) -> None:
        self._agents = {i: object() for i in ids}

    def get_agents(self):
        return list(self._agents.items())

    def get_agent(self, agent_id: int):
        return self._agents[agent_id]


class _Env:
    def __init__(self, ids: list[int]) -> None:
        self.agent_graph = _Graph(ids)


def test_parallel_runner_selection_fills_the_target_with_existing_agents() -> None:
    import run_parallel_simulation as rps  # type: ignore[import-not-found]

    config = {"time_config": dict(_LEGACY_TIME_CONFIG), "agent_configs": _legacy_agent_configs()}
    random.seed(0)

    active = rps.get_active_agents_for_round(_Env([0, 2, 3, 5]), config, 12, 3)

    assert sorted(agent_id for agent_id, _ in active) == [0, 2, 3, 5]


def test_single_platform_runner_selection_fills_the_target_with_existing_agents() -> None:
    from sim_runtime import platform_runner

    runner = platform_runner.SinglePlatformRunner.__new__(platform_runner.SinglePlatformRunner)
    runner.config = {"time_config": dict(_LEGACY_TIME_CONFIG), "agent_configs": _legacy_agent_configs()}
    runner.random_seed = 0
    random.seed(0)

    active = runner._get_active_agents_for_round(_Env([0, 2, 3, 5]), 12, 3)

    assert sorted(agent_id for agent_id, _ in active) == [0, 2, 3, 5]


def test_parallel_runner_logs_an_agent_that_cannot_be_activated() -> None:
    """Der stille ``except Exception: pass`` ist weg: ein unerwartet fehlender Agent steht im Log."""
    import logging

    import run_parallel_simulation as rps  # type: ignore[import-not-found]

    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    runner_logger = logging.getLogger("agora.run_parallel_simulation")
    handler = _Collect(level=logging.WARNING)
    runner_logger.addHandler(handler)

    class _BrokenGraph(_Graph):
        def get_agent(self, agent_id: int):
            raise KeyError(agent_id)

    env = _Env([0, 1, 2, 3])
    env.agent_graph = _BrokenGraph([0, 1, 2, 3])
    config = {"time_config": dict(_LEGACY_TIME_CONFIG), "agent_configs": _legacy_agent_configs(4)}

    try:
        active = rps.get_active_agents_for_round(env, config, 12, 0)
    finally:
        runner_logger.removeHandler(handler)

    assert active == []
    assert len(records) == 4
    assert all("nicht aktivierbar" in record.getMessage() for record in records)
