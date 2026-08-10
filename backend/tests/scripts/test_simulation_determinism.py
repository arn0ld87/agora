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
