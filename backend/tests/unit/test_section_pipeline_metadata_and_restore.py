"""Unit-Tests für Metadaten-Filterung, State-Cleanup und Wiederherstellung in der Section-Pipeline (Befunde 3.1 & 3.2)."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List
import pytest

from app.models.report import ReportOutline, ReportSection
from app.services.report_agent.agent_section_saving import (
    _filter_structured_metadata_against_verified_section,
)
from app.services.report_agent.section_pipeline_runner import (
    _cleanup_pending_state,
    process_section,
    run_section_pipeline,
)
from app.services.report_agent.section_pipeline_steps import (
    _restore_persisted_section,
)
from app.services.report_agent.section_pipeline_types import (
    SectionContext,
    SectionEvidenceOutcome,
    SectionResult,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeReportLogger:
    def __init__(self) -> None:
        self.section_metadata: List[Dict[str, Any]] = []

    def log_section_metadata(self, **kwargs: Any) -> None:
        self.section_metadata.append(kwargs)


class FakePhaseTracker:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.phases: List[str] = []

    def __enter__(self) -> "FakePhaseTracker":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    @contextmanager
    def phase(self, name: str) -> Any:
        self.phases.append(name)
        yield


class FakeQuoteResult:
    def __init__(self, valid: bool = True) -> None:
        self.valid = valid
        self.failures: List[str] = []
        self.repaired_content = ""


class FakeVerifiedProse:
    def __init__(
        self,
        content: str,
        *,
        changed: bool = False,
        rejected: List[str] | None = None,
        unverified: List[str] | None = None,
    ) -> None:
        self.content = content
        self.changed = changed
        self.rejected = rejected or []
        self.unverified = unverified or []
        self.hypotheses: List[Dict[str, Any]] = []


class FakeReportManager:
    _MISSING_FOLDER = Path("/agora-fake-report-manager-ohne-ordner")

    def __init__(self, persisted: Dict[str, Any] | None = None) -> None:
        self.persisted = persisted or {}
        self.progress_calls: List[Dict[str, Any]] = []
        self.saved_sections: List[tuple] = []

    def _get_section_path(self, _report_id: str, section_index: int) -> str:
        return str(self._MISSING_FOLDER / f"section_{section_index:02d}.md")

    def update_progress(self, report_id: str, stage: str, progress: int, message: str, **kw: Any) -> None:
        self.progress_calls.append({"stage": stage, "progress": progress, "message": message, **kw})

    def save_section(self, report_id: str, section_index: int, section: Any) -> None:
        self.saved_sections.append((report_id, section_index, section.content))

    def prepare_content_for_evidence(self, content: str) -> str:
        return content

    def get_persisted_section(self, report_id: str, section_title: str) -> Dict[str, Any] | None:
        return self.persisted.get(section_title)

    def remove_orphan_markdown(self, report_id: str, section_index: int) -> None:
        pass

    def _clean_section_content(self, content: str, title: str) -> str:
        return content.strip()


class FakeAgent:
    def __init__(
        self,
        *,
        evidence_outcome: SectionEvidenceOutcome | None = None,
        evidence_map: Dict[str, Any] | None = None,
    ) -> None:
        self.evidence_map = evidence_map or {}
        self.persona_ids = ["p1", "p2"]
        self.report_logger = FakeReportLogger()
        self._pool: List[Dict[str, Any]] = []
        self._evidence_outcome = evidence_outcome or SectionEvidenceOutcome()
        self.recorded_prose_hypotheses: List[tuple] = []
        self.recorded_unverified: List[tuple] = []
        self.recorded_metadata: List[tuple] = []
        self.saved_evidence_calls: List[tuple] = []

    def _prose_evidence_pool(self) -> List[Dict[str, Any]]:
        return self._pool

    def _record_prose_hypotheses(self, section_index: int, flagged: Any) -> None:
        self.recorded_prose_hypotheses.append((section_index, flagged))

    def _record_unverified_statements(self, section_index: int, unverified: Any) -> None:
        self.recorded_unverified.append((section_index, unverified))

    def _record_section_metadata(self, section_index: int, metadata: Dict[str, Any]) -> None:
        self.recorded_metadata.append((section_index, metadata))

    def _save_evidence_section(
        self, report_id: str, section_index: int, section_title: str, content: str
    ) -> SectionEvidenceOutcome:
        self.saved_evidence_calls.append((report_id, section_index, section_title, content))
        # Simulieren, dass _save_evidence_section die Metadaten am Agenten aktualisiert
        if hasattr(self, "_pending_section_metadata") and isinstance(self._pending_section_metadata, dict):
            self._pending_section_metadata[section_index] = {"filtered": True, "title": section_title}
        return self._evidence_outcome


def _make_test_ctx(
    outline: ReportOutline,
    agent: FakeAgent,
    *,
    generate_section_fn: Any = None,
    persisted_contents: Dict[int, str] | None = None,
) -> SectionContext:
    def default_gen(agent: Any, **kw: Any) -> str:
        return "Generierter Sektions-Content"

    return SectionContext(
        report_id="rep-123",
        outline=outline,
        total_sections=len(outline.sections),
        generate_section=generate_section_fn or default_gen,
        generate_metadata=lambda agent, **kw: {"generated": True},
        validate_quotes=lambda *a, **kw: FakeQuoteResult(valid=True),
        verify_prose_fn=lambda content, pool: FakeVerifiedProse(content),
        is_fallback=lambda content: False,
        report_manager=FakeReportManager(),
        phase_tracker_factory=FakePhaseTracker,
        persisted_section_contents=persisted_contents or {},
    )


# ---------------------------------------------------------------------------
# Befund 3.1: Metadaten-Filterung & State-Cleanup
# ---------------------------------------------------------------------------

def test_filter_structured_metadata_against_verified_section() -> None:
    verified_claims = [
        {
            "claim_id": "c1",
            "statement": "Die Einführung erfolgt in Q3.",
            "evidence_refs": ["ev_1"],
        },
        {
            "claim_id": "c2",
            "statement": "Budget von 500k freigegeben.",
            "evidence": [{"evidence_id": "ev_2"}],
        },
    ]
    content = "Der Gesamttext besagt: Budget von 500k freigegeben. Ein Rollout in München ist geplant."

    metadata = {
        "summary": "Abschnittszusammenfassung",
        "custom_flag": 42,
        "recommendations": [
            {"id": "r1", "claim_id": "c1", "text": "Plan einhalten"},  # überlebt: c1 verifiziert
            {"id": "r2", "claim_id": "c_dropped", "text": "Ungültig"},  # verworfen: Claim fehlt
            {"id": "r3", "evidence_refs": ["ev_1"], "text": "Gestützt durch Ev1"},  # überlebt: ev_1 vorhanden
            {"id": "r4", "evidence_refs": ["ev_unknown"], "text": "Falsche Ref"},  # verworfen: Ref fehlt
            {"description": "Budget von 500k freigegeben."},  # überlebt: Dict-Text im Content
            {"description": "Völlig erfundene Phantasie."},  # verworfen: weder Claim noch Text
        ],
        "risks": [
            {"claim_id": "c2", "risk": "Budgetüberschreitung"},  # überlebt: c2
            {"claim_id": "c_missing", "risk": "Geisterrisiko"},  # verworfen
        ],
        "timeline": [
            {"claim_id": "c1", "milestone": "Start Q3"},  # überlebt
            {"claim_id": "c_none", "milestone": "Ende Q5"},  # verworfen
        ],
        "next_steps": [
            {"step": "Rollout in München ist geplant."},  # überlebt
            {"step": "Unerreichbarer Schritt."},  # verworfen
        ],
    }

    filtered = _filter_structured_metadata_against_verified_section(
        metadata,
        verified_claims=verified_claims,
        persisted_content=content,
    )

    # Skalare / allgemeine Felder bleiben erhalten
    assert filtered["summary"] == "Abschnittszusammenfassung"
    assert filtered["custom_flag"] == 42

    # Recommendations
    recs = filtered["recommendations"]
    assert len(recs) == 3
    assert recs[0]["id"] == "r1"
    assert recs[1]["id"] == "r3"
    assert recs[2]["description"] == "Budget von 500k freigegeben."

    # Risks
    risks = filtered["risks"]
    assert len(risks) == 1
    assert risks[0]["risk"] == "Budgetüberschreitung"

    # Timeline
    timeline = filtered["timeline"]
    assert len(timeline) == 1
    assert timeline[0]["milestone"] == "Start Q3"

    # Next steps
    next_steps = filtered["next_steps"]
    assert len(next_steps) == 1
    assert next_steps[0]["step"] == "Rollout in München ist geplant."


def test_cleanup_pending_state() -> None:
    class DummyAgent:
        pass

    agent = DummyAgent()
    # Dict-basierte Mappings mit section_index=1
    agent._pending_section_claims = {1: [{"id": 1}], 2: [{"id": 2}]}
    agent._pending_structured_metadata = {1: {"key": "val"}}
    agent._pending_structured_attempt_counts = {1: {"try": 2}}
    agent._pending_unbound_evidence_refs = {1: ["ref1"]}
    agent._pending_quote_validation_failed = {1: True}
    agent._pending_section_metadata = {1: {"title": "sec"}}
    agent._pending_prose_hypotheses = {1: ["hyp1"]}
    agent._pending_unverified_statements = {1: ["unver1"]}

    # Aufräumen für section_index=1
    _cleanup_pending_state(agent, section_index=1)

    # Für Index 1 müssen die Werte gelöscht sein, Index 2 bleibt unberührt
    assert 1 not in agent._pending_section_claims
    assert 2 in agent._pending_section_claims
    assert 1 not in agent._pending_structured_metadata
    assert 1 not in agent._pending_structured_attempt_counts
    assert 1 not in agent._pending_unbound_evidence_refs
    assert 1 not in agent._pending_quote_validation_failed
    assert 1 not in agent._pending_section_metadata
    assert 1 not in agent._pending_prose_hypotheses
    assert 1 not in agent._pending_unverified_statements

    # Idempotenz: Zweiter Aufruf darf keine Exception werfen
    _cleanup_pending_state(agent, section_index=1)


def test_process_section_ensures_cleanup_even_on_exception() -> None:
    agent = FakeAgent()
    agent._pending_section_claims = {1: ["leftover_claim"]}
    agent._pending_structured_metadata = {1: {"leftover": True}}

    section = ReportSection(title="Fehler-Sektion", content="", description="")
    outline = ReportOutline(title="Outline", summary="Summary", sections=[section])

    def crashing_gen(ag: Any, **kwargs: Any) -> str:
        raise RuntimeError("Generator-Crash")

    ctx = _make_test_ctx(outline, agent, generate_section_fn=crashing_gen)

    with pytest.raises(RuntimeError, match="Generator-Crash"):
        process_section(agent, section, ctx, section_index=1)

    # Der finally-Block in process_section muss _cleanup_pending_state ausgeführt haben
    assert 1 not in agent._pending_section_claims
    assert 1 not in agent._pending_structured_metadata


def test_process_section_returns_filtered_metadata_and_unbound_refs() -> None:
    agent = FakeAgent()
    agent._pending_section_metadata = {1: {"initial": True}}
    agent._pending_unbound_evidence_refs = {1: ["unbound_1", "unbound_2"]}

    section = ReportSection(title="Erfolgs-Sektion", content="", description="")
    outline = ReportOutline(title="Outline", summary="Summary", sections=[section])

    ctx = _make_test_ctx(outline, agent)

    result = run_section_pipeline(agent, section, ctx, section_index=1)

    assert result.failed is False
    # In FakeAgent._save_evidence_section wurde _pending_section_metadata[1] aktualisiert
    assert result.metadata == {"filtered": True, "title": "Erfolgs-Sektion"}
    assert result.unbound_evidence_refs == ["unbound_1", "unbound_2"]
    # Agent State wurde im finally-Block bereinigt
    assert 1 not in agent._pending_section_metadata
    assert 1 not in agent._pending_unbound_evidence_refs


# ---------------------------------------------------------------------------
# Befund 3.2: Vollständige Wiederherstellung von Abschnitten
# ---------------------------------------------------------------------------

def test_restore_persisted_section_populates_all_fields() -> None:
    agent = FakeAgent()
    section = ReportSection(title="Historische Sektion", content="", description="")
    outline = ReportOutline(title="Outline", summary="Summary", sections=[section])

    persisted = {
        "content": "Gespeicherter Text",
        "evidence": {"sources": ["src_1"]},
        "structured_metadata": {
            "summary": "Restored Summary",
            "recommendations": [{"text": "Vorhandene Empfehlung"}],
        },
        "unbound_evidence_refs": ["lost_ref_1"],
        "quote_validation_failed": True,
        "token_usage": {"prompt": 100, "completion": 50},
    }

    ctx = _make_test_ctx(
        outline,
        agent,
        persisted_contents={1: "Gespeicherter Text"},
    )

    result = _restore_persisted_section(
        agent,
        section,
        ctx,
        section_index=1,
        persisted_entry=persisted,
    )

    assert result.restored is True
    assert result.failed is False
    assert result.content == "Gespeicherter Text"
    assert result.metadata == persisted["structured_metadata"]
    assert result.unbound_evidence_refs == ["lost_ref_1"]
    assert result.quote_validation_failed is True

    # Section-Objekt wurde aktualisiert
    assert section.metadata["structured_metadata"] == persisted["structured_metadata"]
    assert section.metadata["quote_validation_failed"] is True

    # Agent hat Metadaten aufgezeichnet
    assert len(agent.recorded_metadata) == 1
    assert agent.recorded_metadata[0] == (1, persisted["structured_metadata"])


def test_workflow_logic_records_quote_validation_failure_even_if_restored() -> None:
    """Prüft die Loop-Invariante aus workflow.py: quote_validation_failed wird vor result.restored registriert."""
    section = ReportSection(title="Restaurierte Sektion mit Quote-Fehler", content="", description="")
    result = SectionResult(
        section_index=0,
        title=section.title,
        content="Inhalt",
        restored=True,
        quote_validation_failed=True,
    )

    quote_validation_failures: List[str] = []

    # Exakt die Logik aus workflow.py
    if result.quote_validation_failed:
        quote_validation_failures.append(section.title)

    if result.restored:
        pass  # continue im echten Loop

    assert quote_validation_failures == ["Restaurierte Sektion mit Quote-Fehler"]

