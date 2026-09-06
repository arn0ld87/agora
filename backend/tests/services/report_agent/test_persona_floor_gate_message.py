"""Regressionstest #1420 — Persona-Floor-Gate-Meldung mit Kandidaten-/Ablehnungszahl.

Produktionsbeleg: ein Lauf mit 23 Persona-Kandidaten (nach Dedup), 8 davon
durch das Eignungs-Gate als technische Artefakte abgelehnt (kein Nachrücker
verfügbar), 15 zugelassenen Personas scheiterte am Mindestanzahl-Gate
(Floor 20) mit der nichtssagenden Meldung "15/20 Personas vorhanden." — ohne
Hinweis darauf, dass ein anderes, korrekt arbeitendes Qualitätsgate den Pool
verkleinert hat.

Die Ablehnungszahl selbst wird an dieser Stelle nicht persistiert (sie lebt
nur lokal in ``OasisProfileGenerator.generate_profiles_from_entities`` und
wird nur geloggt). Sie lässt sich aber verlustfrei aus zwei bereits
persistierten Werten ableiten: ``state.entities_count`` (Kandidatenzahl vor
der Generierung, gesetzt in ``prepare_service.py::_phase_read_entities``) und
der tatsächlichen Personazahl — jede Ablehnung ohne Nachrücker lässt exakt
einen Profilslot leer.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.report import Report, ReportStatus
from app.services.report_agent.workflow import (
    _load_persona_candidate_count,
    _mark_incomplete_for_persona_floor,
)


def _make_report() -> Report:
    return Report(
        report_id="report_1420",
        simulation_id="sim_1420",
        graph_id="graph_1420",
        simulation_requirement="Testauftrag",
        status=ReportStatus.PENDING,
    )


class TestMarkIncompleteForPersonaFloorMessage:
    def test_message_includes_candidate_rejection_and_result_counts(self):
        """Kernauftrag: Kandidatenzahl, Ablehnungszahl, Ergebniszahl in der Meldung."""
        report = _make_report()
        with patch(
            "app.services.report_agent.workflow.ReportManager"
        ) as mock_rm:
            result = _mark_incomplete_for_persona_floor(
                report,
                report_id="report_1420",
                persona_count=15,
                floor=20,
                candidate_count=23,
            )
            assert mock_rm.update_progress.called
            assert mock_rm.save_report.called

        assert result.status == ReportStatus.INCOMPLETE
        assert result.error is not None
        # Kandidatenzahl (23), Ablehnungszahl (8 = 23-15), Ergebniszahl (15).
        assert "23" in result.error
        assert "8" in result.error
        assert "15" in result.error
        assert "20" in result.error  # Floor bleibt in der Meldung sichtbar.

    def test_message_falls_back_without_candidate_count(self):
        """Ohne verfuegbare Kandidatenzahl bleibt die knappe Kurzform bestehen —
        kein Bruch fuer Simulationen ohne persistiertes ``entities_count``."""
        report = _make_report()
        with patch("app.services.report_agent.workflow.ReportManager"):
            result = _mark_incomplete_for_persona_floor(
                report,
                report_id="report_1420",
                persona_count=15,
                floor=20,
                candidate_count=None,
            )
        assert result.status == ReportStatus.INCOMPLETE
        assert result.error == "Persona-Mindestanzahl nicht erreicht: 15/20 Personas vorhanden."

    def test_message_omits_rejection_detail_when_candidates_below_result(self):
        """Verteidigung gegen Datendrift: eine unplausible Kandidatenzahl
        (kleiner als das Ergebnis) darf keine negative Ablehnungszahl erzeugen —
        das Gate degradiert dann auf die Kurzform statt falsche Zahlen zu zeigen."""
        report = _make_report()
        with patch("app.services.report_agent.workflow.ReportManager"):
            result = _mark_incomplete_for_persona_floor(
                report,
                report_id="report_1420",
                persona_count=15,
                floor=20,
                candidate_count=10,
            )
        assert result.status == ReportStatus.INCOMPLETE
        assert result.error == "Persona-Mindestanzahl nicht erreicht: 15/20 Personas vorhanden."

    def test_gate_still_marks_incomplete_regardless_of_message_enrichment(self):
        """Pflichttest: das Gate greift weiterhin bei zu wenigen Personas —
        die Meldungsanreicherung darf den Statuswechsel nicht wirkungslos machen."""
        report = _make_report()
        with patch("app.services.report_agent.workflow.ReportManager"):
            result = _mark_incomplete_for_persona_floor(
                report,
                report_id="report_1420",
                persona_count=3,
                floor=20,
                candidate_count=3,
            )
        assert result.status == ReportStatus.INCOMPLETE
        assert result.missing_sections and len(result.missing_sections) == 1


class TestLoadPersonaCandidateCount:
    def test_reads_entities_count_from_persisted_state(self):
        agent = MagicMock()
        agent.simulation_id = "sim_1420"
        store = MagicMock()
        store.read_json.return_value = {"entities_count": 23, "profiles_count": 15}
        with patch(
            "app.services.report_agent.workflow.resolve_default_store",
            return_value=store,
        ):
            assert _load_persona_candidate_count(agent) == 23
        store.read_json.assert_called_once_with("sim_1420", "state", default=None)

    def test_returns_none_when_state_missing_or_invalid(self):
        agent = MagicMock()
        agent.simulation_id = "sim_1420"
        store = MagicMock()
        store.read_json.return_value = None
        with patch(
            "app.services.report_agent.workflow.resolve_default_store",
            return_value=store,
        ):
            assert _load_persona_candidate_count(agent) is None

        store.read_json.return_value = {"entities_count": "not-a-number"}
        with patch(
            "app.services.report_agent.workflow.resolve_default_store",
            return_value=store,
        ):
            assert _load_persona_candidate_count(agent) is None

    def test_returns_none_on_store_error(self):
        agent = MagicMock()
        agent.simulation_id = "sim_1420"
        store = MagicMock()
        store.read_json.side_effect = RuntimeError("store unavailable")
        with patch(
            "app.services.report_agent.workflow.resolve_default_store",
            return_value=store,
        ):
            assert _load_persona_candidate_count(agent) is None
