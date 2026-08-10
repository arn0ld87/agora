"""Regressionstests fuer die Sichtbarkeit der Report-Nachbearbeitung (Issue #1187).

Befund im Lauf ``report_b76cf7078229``: zwischen "Abschnittstext fertig" und
"Section saved" lagen 178-347s **ohne eine einzige Logzeile und ohne
``progress.json``-Update** — 1344s von 2285s Gesamtlaufzeit. ``progress.json``
stand nach dem Speichern von Abschnitt 6 weiterhin auf ``78 %`` mit einem
``updated_at``, das drei Minuten alt war. Ein arbeitender Lauf war fuer den
Nutzer nicht von einem abgestuerzten unterscheidbar.

Die Tests treffen genau diesen Defekt: waehrend der Nachbearbeitung muss
Fortschritt gemeldet und die Dauer jeder Phase geloggt werden. Sie sagen
ausdruecklich **nichts** darueber aus, wie schnell die Nachbearbeitung ist —
das ist Issue #1190 und bewusst blockiert, bis diese Instrumentierung
belastbare Zahlen liefert.
"""
from __future__ import annotations

from unittest.mock import patch

from app.services.report_agent import ReportAgent
from app.services.report_agent.postprocess_timing import (
    HEARTBEAT_INTERVAL_SECONDS,
    PostprocessPhaseTracker,
)


class _RecordingReportManager:
    """Zeichnet ``update_progress``-Aufrufe auf, statt progress.json zu schreiben."""

    def __init__(self) -> None:
        self.progress_calls: list[dict] = []

    def get_progress(self, report_id: str) -> dict:
        return {"progress": 40, "completed_sections": ["Erster Abschnitt"]}

    def update_progress(
        self,
        report_id: str,
        status: str,
        progress: int,
        message: str,
        current_section=None,
        completed_sections=None,
    ) -> None:
        self.progress_calls.append(
            {
                "report_id": report_id,
                "status": status,
                "progress": progress,
                "message": message,
                "current_section": current_section,
                "completed_sections": completed_sections,
            }
        )


class _RecordingLogger:
    def __init__(self) -> None:
        self.phase_timings: list[dict] = []

    def log_phase_timing(
        self,
        phase: str,
        duration_seconds: float,
        section_title=None,
        section_index=None,
    ) -> None:
        self.phase_timings.append(
            {
                "phase": phase,
                "duration_seconds": duration_seconds,
                "section_title": section_title,
                "section_index": section_index,
            }
        )


def _tracker(manager: _RecordingReportManager, logger: _RecordingLogger):
    return PostprocessPhaseTracker(
        "report_test",
        section_index=2,
        section_title="Stakeholder",
        report_logger=logger,
        report_manager=manager,
    )


# ---------------------------------------------------------------------------
# 1. Kern des Defekts: die Nachbearbeitung meldet ueberhaupt Fortschritt
# ---------------------------------------------------------------------------


def test_phase_meldet_start_und_ende_an_progress_json():
    manager = _RecordingReportManager()
    tracker = _tracker(manager, _RecordingLogger())

    with tracker.phase("claim_extraction_and_evidence_binding"):
        pass

    # Vor dem Fix: null Aufrufe waehrend der gesamten Nachbearbeitung.
    assert len(manager.progress_calls) == 2, (
        "Start und Ende einer Nachbearbeitungsphase muessen progress.json bewegen"
    )
    assert all(call["status"] == "generating" for call in manager.progress_calls)
    assert all(
        call["current_section"] == "Stakeholder" for call in manager.progress_calls
    )
    assert "gestartet" in manager.progress_calls[0]["message"]
    assert "abgeschlossen" in manager.progress_calls[-1]["message"]


def test_phase_uebernimmt_bestehenden_fortschrittsstand():
    """Der gemeldete Prozentwert darf nicht hinter den Stand zurueckfallen."""
    manager = _RecordingReportManager()
    tracker = _tracker(manager, _RecordingLogger())

    tracker.start_phase("evidence_map_persistence")

    assert manager.progress_calls[0]["progress"] == 40
    assert manager.progress_calls[0]["completed_sections"] == ["Erster Abschnitt"]


def test_phasenende_loggt_messbare_dauer():
    """Ohne Phasenzeiten bleibt Issue #1190 dauerhaft blockiert."""
    manager = _RecordingReportManager()
    logger = _RecordingLogger()
    tracker = _tracker(manager, logger)

    with patch(
        "app.services.report_agent.postprocess_timing.time.monotonic",
        side_effect=[100.0, 342.5],
    ):
        with tracker.phase("claim_extraction_and_evidence_binding"):
            pass

    assert len(logger.phase_timings) == 1
    timing = logger.phase_timings[0]
    assert timing["phase"] == "claim_extraction_and_evidence_binding"
    assert timing["duration_seconds"] == 242.5
    assert timing["section_index"] == 2
    assert timing["section_title"] == "Stakeholder"


# ---------------------------------------------------------------------------
# 2. Heartbeat: lange Phasen bleiben sichtbar, ohne progress.json zu fluten
# ---------------------------------------------------------------------------


def test_heartbeat_drosselt_innerhalb_des_intervalls():
    manager = _RecordingReportManager()
    tracker = _tracker(manager, _RecordingLogger())

    with patch(
        "app.services.report_agent.postprocess_timing.time.monotonic",
        side_effect=[100.0, 100.5, 101.0],
    ):
        tracker.start_phase("claim_extraction_and_evidence_binding")
        tracker.heartbeat("Claim 1/80")
        tracker.heartbeat("Claim 2/80")

    # Nur der start_phase-Aufruf; die beiden Heartbeats fallen ins Intervall.
    assert len(manager.progress_calls) == 1


def test_heartbeat_meldet_nach_ablauf_des_intervalls():
    manager = _RecordingReportManager()
    tracker = _tracker(manager, _RecordingLogger())

    spaeter = 100.0 + HEARTBEAT_INTERVAL_SECONDS + 1.0
    with patch(
        "app.services.report_agent.postprocess_timing.time.monotonic",
        side_effect=[100.0, spaeter, spaeter],
    ):
        tracker.start_phase("claim_extraction_and_evidence_binding")
        tracker.heartbeat("Claim 40/80")

    assert len(manager.progress_calls) == 2
    assert "Claim 40/80" in manager.progress_calls[-1]["message"]


def test_heartbeat_ohne_laufende_phase_ist_folgenlos():
    manager = _RecordingReportManager()
    tracker = _tracker(manager, _RecordingLogger())

    tracker.heartbeat("Claim 1/80")

    assert manager.progress_calls == []


def test_fortschrittsmeldung_stoppt_die_nachbearbeitung_nicht():
    """Ein Schreibfehler an progress.json darf den Report nicht abbrechen."""

    class _BrokenManager(_RecordingReportManager):
        def update_progress(self, *args, **kwargs):
            raise OSError("progress.json nicht schreibbar")

    tracker = _tracker(_BrokenManager(), _RecordingLogger())

    with tracker.phase("evidence_map_persistence"):
        pass


# ---------------------------------------------------------------------------
# 3. Integration: _save_evidence_section instrumentiert die echte Schleife
# ---------------------------------------------------------------------------


class _FakeAgentForTiming:
    """Spiegelt die von ``_save_evidence_section`` genutzten Attribute."""

    def __init__(self, *, report_logger=None) -> None:
        if report_logger is not None:
            self.report_logger = report_logger
        self.evidence_map = {
            "schema_version": 3,
            "report_id": "report_test",
            "simulation_id": "sim_test",
            "evidence_index": {},
            "global_evidence_refs": [],
            "sections": [],
            "degradation_log": [],
        }
        self._pending_prose_hypotheses: dict = {}
        self._pending_section_metadata: dict = {}
        self._collect_simulation_evidence_items = lambda: []
        self._build_claims_for_section = lambda content, heartbeat=None: []
        self._finalize_section_claims = lambda raw: ([], [], [], [])
        self._truncate = lambda text, length: (
            text[:length] if isinstance(text, str) else text
        )
        self._section_dedup_check = lambda **kwargs: None
        self._init_evidence_map = lambda report_id: None
        self._active_section_evidence: list = []
        self._active_section_unresolved_evidence: list = []
        self._remap_active_evidence_ids = (
            lambda id_remap: ReportAgent._remap_active_evidence_ids(self, id_remap)
        )


def test_nachbearbeitung_meldet_fortschritt_und_phasenzeiten():
    """Der eigentliche Regressionstest gegen den gemessenen Defekt.

    Vor dem Fix lief ``_save_evidence_section`` von Anfang bis Ende durch,
    ohne ein einziges Mal Fortschritt zu melden — genau die 178-347s Stille
    pro Abschnitt.
    """
    logger = _RecordingLogger()
    fake_agent = _FakeAgentForTiming(report_logger=logger)
    progress_calls: list[str] = []

    def _record_progress(report_id, status, progress, message, **kwargs):
        progress_calls.append(message)

    with patch(
        "app.services.report_agent.ReportManager.save_evidence_map"
    ), patch(
        "app.services.report_agent.ReportManager.update_progress",
        side_effect=_record_progress,
    ), patch(
        "app.services.report_agent.ReportManager.get_progress",
        return_value={"progress": 40, "completed_sections": []},
    ):
        ReportAgent._save_evidence_section(
            fake_agent,
            "report_test",
            2,
            "Stakeholder",
            "Ausfuehrlicher Abschnittstext fuer die zweite Sektion.",
        )

    assert progress_calls, (
        "Die Nachbearbeitung darf nicht mehr ohne jede Fortschrittsmeldung laufen"
    )
    gemeldete_phasen = {timing["phase"] for timing in logger.phase_timings}
    assert "claim_extraction_and_evidence_binding" in gemeldete_phasen
    assert "evidence_map_persistence" in gemeldete_phasen


def test_nachbearbeitung_ohne_logger_laeuft_unveraendert_durch():
    """Ohne ``report_logger`` bleibt die Instrumentierung vollstaendig inaktiv.

    Deckt den Pfad ab, auf dem ``phase_tracker`` ``None`` ist — ein
    ungeschuetzter ``end_phase()``-Aufruf riss hier mit ``AttributeError``
    genau die Unit-Tests, die ``ReportAgent`` ohne Logger bauen.
    """
    fake_agent = _FakeAgentForTiming()
    progress_calls: list[str] = []

    with patch(
        "app.services.report_agent.ReportManager.save_evidence_map"
    ) as mock_save, patch(
        "app.services.report_agent.ReportManager.update_progress",
        side_effect=lambda *a, **k: progress_calls.append(a),
    ):
        ReportAgent._save_evidence_section(
            fake_agent,
            "report_test",
            2,
            "Stakeholder",
            "Ausfuehrlicher Abschnittstext fuer die zweite Sektion.",
        )
        mock_save.assert_called_once()

    assert progress_calls == []
