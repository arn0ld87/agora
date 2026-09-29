"""Regressionstests fuer Epic #1713 Slice S0: Kennzahlen "Simulation lebt".

Fixtures unter ``backend/tests/fixtures/sim_liveness/``:

- ``clean_run/``: ein voller Simulationslauf (4 Agenten, 3 Hauptrunden) mit
  bewusst konstruierten Aktionen, damit jede Kennzahl (L1-L5, L7, L8) einen
  von Hand nachrechenbaren erwarteten Wert hat.
- ``legacy_run/``: reproduziert die #1713-Slice-S1-Altlauf-Signatur (ein
  Startpost, der ohne ``round``-Feld erneut in Runde 1 geloggt wurde) plus
  eine echte neue Aktion in derselben Runde.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import sim_liveness_metrics as metrics  # type: ignore[import-not-found]  # noqa: E402

_FIXTURES = _BACKEND_DIR / "tests" / "fixtures" / "sim_liveness"


class TestCleanRunMetrics:
    """Alle Kennzahlen gegen von Hand nachgerechnete erwartete Werte."""

    @pytest.fixture()
    def report(self):
        return metrics.compute_report(_FIXTURES / "clean_run")

    def test_top_level_fields(self, report) -> None:
        assert report.sim_id == "sim_liveness_clean"
        assert report.platforms == ["twitter"]
        assert report.agent_count == 4
        assert report.rounds_completed == 3
        assert report.runner_status == "completed"
        assert report.wall_clock_seconds == pytest.approx(1800.0)

    def test_l1_actions_per_agent_round(self, report) -> None:
        tw = report.per_platform["twitter"]
        # 7 reale Aktionen (ohne Startpost, ohne DO_NOTHING) / (4 Agenten * 3 Runden)
        assert tw.actions_per_agent_round == pytest.approx(7 / 12)

    def test_l2_active_agent_share_median(self, report) -> None:
        tw = report.per_platform["twitter"]
        # Jede der drei Runden hat 3 von 4 Agenten aktiv (inkl. DO_NOTHING)
        assert tw.active_agent_share_median == pytest.approx(0.75)

    def test_l3_own_post_share(self, report) -> None:
        tw = report.per_platform["twitter"]
        # CREATE_POST + QUOTE_POST = 2 von (CREATE_POST+CREATE_COMMENT+QUOTE_POST+REPOST) = 4
        assert tw.own_post_share == pytest.approx(0.5)

    def test_l4_mutual_pair_share_and_chain(self, report) -> None:
        tw = report.per_platform["twitter"]
        # Kanten: Petra->Mara (Like), Mara->Jonas (Like), Jonas->Mara (Dislike),
        # Petra->Jonas (Repost), Karl->Mara (Quote). Paare: {Mara,Jonas} mutual,
        # {Mara,Petra} einseitig, {Jonas,Petra} einseitig, {Mara,Karl} einseitig.
        assert tw.mutual_pair_share == pytest.approx(1 / 4)
        assert tw.max_chain_length == 2

    def test_l5_rejection_share(self, report) -> None:
        tw = report.per_platform["twitter"]
        # 1 Dislike von 3 Like/Dislike-Reaktionen
        assert tw.rejection_share == pytest.approx(1 / 3)
        assert tw.contra_reply_share is None

    def test_l7_none_without_seed(self, report) -> None:
        tw = report.per_platform["twitter"]
        assert tw.seed_echo_share is None
        assert any("kein --seed" in note for note in tw.data_quality_notes)

    def test_l8_no_duplicates_full_round_fill(self, report) -> None:
        tw = report.per_platform["twitter"]
        assert tw.duplicate_log_lines == 0
        assert tw.round_fill_share == pytest.approx(1.0)

    def test_action_type_counts(self, report) -> None:
        tw = report.per_platform["twitter"]
        assert tw.action_type_counts["CREATE_POST"] == 2  # Startpost + Jonas
        assert tw.action_type_counts["DO_NOTHING"] == 2
        assert tw.action_type_counts["REPOST"] == 1
        assert tw.action_type_counts["QUOTE_POST"] == 1

    def test_overall_mirrors_single_platform(self, report) -> None:
        # Bei genau einer Plattform muss "gesamt" dieselben Werte tragen.
        tw = report.per_platform["twitter"]
        overall = report.overall
        assert overall.platform == "gesamt"
        assert overall.actions_per_agent_round == pytest.approx(tw.actions_per_agent_round)
        assert overall.own_post_share == pytest.approx(tw.own_post_share)


class TestSeedEcho:
    def test_seed_echo_share_with_number_match(self) -> None:
        report = metrics.compute_report(
            _FIXTURES / "clean_run", seed_path=_FIXTURES / "clean_run" / "seed.md"
        )
        tw = report.per_platform["twitter"]
        # 2 eigene Posts (CREATE_POST Runde 1 "...42 neue Stellen.", QUOTE_POST
        # Runde 3 "Sehe ich anders."); nur der erste enthaelt die Seed-Zahl 42.
        assert tw.seed_echo_share == pytest.approx(0.5)

    def test_missing_seed_file_yields_none_with_note(self, tmp_path) -> None:
        report = metrics.compute_report(
            _FIXTURES / "clean_run", seed_path=tmp_path / "missing_seed.md"
        )
        tw = report.per_platform["twitter"]
        assert tw.seed_echo_share is None


class TestLegacyRunAltlaufSignatur:
    """#1713 Slice S1: last_rowid nicht gezogen -> Startpost taucht in Runde 1
    erneut auf (hier zusaetzlich ohne ``round``-Feld, wie ein echter Altlauf
    vor der Log-Konvention)."""

    @pytest.fixture()
    def report(self):
        return metrics.compute_report(_FIXTURES / "legacy_run")

    def test_round_derived_from_round_start_event(self, report) -> None:
        tw = report.per_platform["twitter"]
        assert any("aus round_start-Events abgeleitet" in note for note in tw.data_quality_notes)

    def test_duplicate_startpost_detected(self, report) -> None:
        tw = report.per_platform["twitter"]
        assert tw.duplicate_log_lines == 1
        assert any("Altlauf-Signatur" in note for note in tw.data_quality_notes)

    def test_real_new_action_still_counted(self, report) -> None:
        # Trotz Altlauf-Erkennung darf die echte neue Aktion (Jonas) nicht
        # verworfen werden.
        assert report.rounds_completed == 1
        tw = report.per_platform["twitter"]
        assert tw.actions_per_agent_round == pytest.approx(2 / (2 * 1))
