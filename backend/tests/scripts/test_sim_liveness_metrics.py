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

import json
import sys
import time
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
        # mutual_pair_share (Akteur-Reaktionsgraph, unveraendert): Petra->Mara
        # (Like), Mara->Jonas (Like), Jonas->Mara (Dislike), Petra->Jonas
        # (Repost), Karl->Mara (Quote). Paare: {Mara,Jonas} mutual,
        # {Mara,Petra} einseitig, {Jonas,Petra} einseitig, {Mara,Karl} einseitig.
        assert tw.mutual_pair_share == pytest.approx(1 / 4)
        # max_chain_length (#1713 Slice S2: Beitrags-Antwortkette statt
        # Pfadsuche im Agentengraph). Jonas' Post (post_id=2) ist Wurzel;
        # Karls Kommentar (post_id=2) und Petras Repost (reposted_id=2)
        # haengen direkt darunter -> Tiefe 1. Karls Quote referenziert
        # quoted_id=1 (Maras Startpost aus Runde 0, der nie ein post_id-Feld
        # traegt, siehe _log_initial_post) und wird mangels bekanntem
        # Elternknoten selbst zur Wurzel -> Tiefe 0. Laengste Kette = 1
        # Kante (vorher 2, weil die alte Implementierung ueber den
        # Agentengraphen lief statt ueber Beitragsreferenzen).
        assert tw.max_chain_length == 1

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


class TestChainCycleTermination:
    """#1713 Slice S2: eine lange Folge wechselseitiger A<->B-Interaktionen
    sah im alten Agentengraph-Modell wie ein Zyklus aus (Kante A->B *und*
    B->A) und war Teil der exponentiellen Pfadsuche. Im Beitragsketten-
    Modell ist das schlicht eine korrekte, lange Kette -- jeder Beitrag hat
    hoechstens einen Elternbeitrag, ein echter Zyklus kann aus den Feldern
    strukturell nicht entstehen."""

    def test_alternating_agents_long_chain_terminates_and_is_correct(self) -> None:
        hops = 120
        actions: list[dict] = [
            {
                "round": 1,
                "agent_id": 0,
                "agent_name": "A",
                "action_type": "CREATE_POST",
                "action_args": {"content": "root", "post_id": 1},
            }
        ]
        for i in range(2, hops + 2):
            actor = "A" if i % 2 == 0 else "B"
            actions.append(
                {
                    "round": 1,
                    "agent_id": 0 if actor == "A" else 1,
                    "agent_name": actor,
                    "action_type": "QUOTE_POST",
                    "action_args": {
                        "content": f"reply {i}",
                        "quoted_id": i - 1,
                        "new_post_id": i,
                    },
                }
            )
        start = time.perf_counter()
        max_chain = metrics._max_chain_length(actions, "twitter")
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"_max_chain_length took {elapsed:.3f}s for {hops} hops"
        assert max_chain == hops

    def test_malformed_forward_reference_does_not_create_cycle(self) -> None:
        # post 1 referenziert (fehlerhaft) post 2, der erst danach im Log
        # auftaucht; post 2 referenziert echt post 1. Eine Elternreferenz
        # zaehlt nur, wenn der Zielknoten beim Verarbeiten bereits bekannt
        # ist -- die Vorwaertsreferenz wird ignoriert statt einen echten
        # Zyklus zu bilden (und die Berechnung zu haengen).
        actions = [
            {
                "agent_id": 0,
                "action_type": "QUOTE_POST",
                "action_args": {"content": "a", "quoted_id": 2, "new_post_id": 1},
            },
            {
                "agent_id": 1,
                "action_type": "QUOTE_POST",
                "action_args": {"content": "b", "quoted_id": 1, "new_post_id": 2},
            },
        ]
        max_chain = metrics._max_chain_length(actions, "twitter")
        assert max_chain == 1


class TestNestedCommentChainS5:
    """#1713 Slice S5: Kommentar-auf-Kommentar (Reddit, nested-comments-Patch)
    muss die L4-Kette ueber ``parent_comment_id`` verlaengern statt an der
    Post-Ebene zu kappen (vorher: jedes CREATE_COMMENT haengte immer direkt
    unter seinem Elternpost, egal ob es tatsaechlich auf einen anderen
    Kommentar antwortete)."""

    def test_comment_on_comment_extends_chain_via_parent_comment_id(self) -> None:
        actions = [
            {
                "round": 1,
                "agent_id": 0,
                "agent_name": "A",
                "action_type": "CREATE_POST",
                "action_args": {"content": "root", "post_id": 1},
            },
            {
                # Top-Level-Kommentar: kein parent_comment_id-Wert -> haengt
                # direkt unter dem Post (Tiefe 1).
                "round": 1,
                "agent_id": 1,
                "agent_name": "B",
                "action_type": "CREATE_COMMENT",
                "action_args": {
                    "content": "Elternkommentar",
                    "comment_id": 10,
                    "post_id": 1,
                    "parent_comment_id": None,
                },
            },
            {
                # Antwort auf den Elternkommentar (nicht auf den Post) ->
                # muss ueber parent_comment_id an comment_id=10 haengen,
                # Tiefe 2.
                "round": 1,
                "agent_id": 2,
                "agent_name": "C",
                "action_type": "CREATE_COMMENT",
                "action_args": {
                    "content": "Antwort auf Elternkommentar",
                    "comment_id": 11,
                    "post_id": 1,
                    "parent_comment_id": 10,
                },
            },
            {
                # Dritte Ebene: Antwort auf die Antwort -> Tiefe 3.
                "round": 1,
                "agent_id": 0,
                "agent_name": "A",
                "action_type": "CREATE_COMMENT",
                "action_args": {
                    "content": "Antwort auf die Antwort",
                    "comment_id": 12,
                    "post_id": 1,
                    "parent_comment_id": 11,
                },
            },
        ]
        max_chain = metrics._max_chain_length(actions, "twitter")
        assert max_chain == 3

    def test_comment_without_parent_comment_id_key_falls_back_to_post(self) -> None:
        """Rueckwaertskompatibilitaet: fehlt das Feld ``parent_comment_id``
        komplett in den action_args (Twitter, oder aeltere Laeufe ohne
        Patch), verhaelt sich die Kette wie vor #1713 S5 -- der Kommentar
        haengt direkt unter seinem Elternpost."""
        actions = [
            {
                "round": 1,
                "agent_id": 0,
                "agent_name": "A",
                "action_type": "CREATE_POST",
                "action_args": {"content": "root", "post_id": 1},
            },
            {
                "round": 1,
                "agent_id": 1,
                "agent_name": "B",
                "action_type": "CREATE_COMMENT",
                "action_args": {
                    "content": "Antwort",
                    "comment_id": 10,
                    "post_id": 1,
                },
            },
        ]
        max_chain = metrics._max_chain_length(actions, "twitter")
        assert max_chain == 1


def _build_large_run(base_dir: Path, total_actions: int = 5000, agent_count: int = 60) -> Path:
    """Synthetischer Lauf fuer den Performance-Regressionstest: 5000 Aktionen,
    60 Agenten, ueberwiegend QUOTE_POST auf den jeweils juengsten Post einer
    gleitenden Post-Auswahl, damit tief verschachtelte Ketten entstehen."""
    run_dir = base_dir / "large_run"
    (run_dir / "twitter").mkdir(parents=True)
    agent_configs = [{"agent_id": i, "entity_name": f"Agent{i}"} for i in range(agent_count)]
    (run_dir / "simulation_config.json").write_text(
        json.dumps({"simulation_id": "sim_liveness_perf", "agent_configs": agent_configs})
    )
    (run_dir / "run_state.json").write_text(json.dumps({"runner_status": "completed"}))

    lines: list[str] = []
    recent_posts: list[int] = []
    next_id = 1
    round_num = 0
    actions_per_round = 50
    for i in range(total_actions):
        if i % actions_per_round == 0:
            round_num += 1
            lines.append(json.dumps({"round": round_num, "event_type": "round_start"}))
        agent_id = i % agent_count
        own_id = next_id
        next_id += 1
        if not recent_posts or i % 4 == 0:
            action = {
                "round": round_num,
                "agent_id": agent_id,
                "agent_name": f"Agent{agent_id}",
                "action_type": "CREATE_POST",
                "action_args": {"content": f"post {own_id}", "post_id": own_id},
                "success": True,
            }
        else:
            parent_id = recent_posts[-1]
            action = {
                "round": round_num,
                "agent_id": agent_id,
                "agent_name": f"Agent{agent_id}",
                "action_type": "QUOTE_POST",
                "action_args": {
                    "content": f"quote {own_id}",
                    "quoted_id": parent_id,
                    "new_post_id": own_id,
                    "original_author_name": f"Agent{(agent_id - 1) % agent_count}",
                },
                "success": True,
            }
        recent_posts.append(own_id)
        if len(recent_posts) > 25:
            recent_posts.pop(0)
        lines.append(json.dumps(action))
        if (i + 1) % actions_per_round == 0:
            lines.append(json.dumps({"round": round_num, "event_type": "round_end"}))
    (run_dir / "twitter" / "actions.jsonl").write_text("\n".join(lines) + "\n")
    return run_dir


class TestPerformance:
    """#1713: max_chain_length haengte echte Laeufe (sim_8fd9a6e4bc97) ueber
    20 Minuten wegen der exponentiellen Pfadsuche im Agentengraph. Das
    Beitragsketten-Modell muss dieselbe Groessenordnung in Sekunden statt
    Minuten schaffen."""

    def test_large_run_completes_within_two_seconds(self, tmp_path) -> None:
        run_dir = _build_large_run(tmp_path)
        start = time.perf_counter()
        report = metrics.compute_report(run_dir)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"compute_report took {elapsed:.2f}s for 5000 actions (limit 2.0s)"
        tw = report.per_platform["twitter"]
        assert tw.max_chain_length is not None
        assert tw.max_chain_length > 0
