"""Tests für die Abschnitts-Pipeline (Issue #1212).

Diese Datei prüft ``process_section`` direkt am Interface. Kein einziger
``patch()``-Aufruf: alles, was der Ablauf über seine Umgebung braucht, kommt
über ``SectionContext`` herein. Das ist der Unterschied zu
``test_partial_report.py``, das denselben Ablauf über 21 Patches auf
Modulnamen in ``workflow`` erreicht und damit Namen statt Verhalten festhält.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, List

from app.models.report import ReportOutline, ReportSection
from app.services.report_agent.section_pipeline import (
    SectionContext,
    SectionEvidenceOutcome,
    process_section,
)


# ---------------------------------------------------------------------------
# Fakes — bewusst kleine, echte Klassen statt MagicMock: sie zeigen, welches
# Interface die Pipeline von ihrer Umgebung tatsächlich erwartet.
# ---------------------------------------------------------------------------


class FakeReportLogger:
    def __init__(self) -> None:
        self.section_metadata: List[Dict[str, Any]] = []

    def log_section_metadata(self, **kwargs: Any) -> None:
        self.section_metadata.append(kwargs)


class FakeAgent:
    """Minimaler Agent-Ersatz mit den von der Pipeline genutzten Anschlüssen."""

    def __init__(
        self,
        *,
        evidence_map: Dict[str, Any] | None = None,
        prose_pool: List[Dict[str, Any]] | None = None,
        evidence_outcome: SectionEvidenceOutcome | None = None,
    ) -> None:
        self.evidence_map = evidence_map if evidence_map is not None else {}
        self.persona_ids = ["p1", "p2"]
        self.report_logger = FakeReportLogger()
        self._pool = prose_pool or []
        self._evidence_outcome = evidence_outcome or SectionEvidenceOutcome()
        self.recorded_prose_hypotheses: List[tuple] = []
        self.recorded_metadata: List[tuple] = []
        self.saved_evidence_calls: List[tuple] = []

    def _prose_evidence_pool(self) -> List[Dict[str, Any]]:
        return self._pool

    def _record_prose_hypotheses(self, section_index: int, rejected: Any) -> None:
        self.recorded_prose_hypotheses.append((section_index, rejected))

    def _record_section_metadata(self, section_index: int, metadata: Dict[str, Any]) -> None:
        self.recorded_metadata.append((section_index, metadata))

    def _save_evidence_section(
        self, report_id: str, section_index: int, section_title: str, content: str
    ) -> SectionEvidenceOutcome:
        self.saved_evidence_calls.append((report_id, section_index, section_title, content))
        return self._evidence_outcome


class FakeReportManager:
    def __init__(self) -> None:
        self.progress_calls: List[Dict[str, Any]] = []
        self.saved_sections: List[tuple] = []
        self.clean_calls: List[tuple] = []
        self.evidence_prep_calls: List[str] = []

    def update_progress(self, report_id: str, stage: str, progress: int, message: str, **kw: Any) -> None:
        self.progress_calls.append({"stage": stage, "progress": progress, "message": message, **kw})

    def save_section(self, report_id: str, section_index: int, section: Any) -> None:
        self.saved_sections.append((report_id, section_index, section.content))

    def _clean_section_content(self, content: str, section_title: str) -> str:
        self.clean_calls.append((content, section_title))
        return content.strip()

    def prepare_content_for_evidence(self, content: str) -> str:
        """Spiegelt den Produktivpfad: Zitate rendern, Überschriften stehen lassen."""
        self.evidence_prep_calls.append(content)
        return (
            (content or "")
            .replace("<simulated_quote>", "> ")
            .replace("</simulated_quote>", "")
        )


class FakePhaseTracker:
    """Erfüllt den ``phase(name)``-Kontextmanager-Vertrag."""

    instances: List["FakePhaseTracker"] = []

    def __init__(self, report_id: str, **kwargs: Any) -> None:
        self.report_id = report_id
        self.kwargs = kwargs
        self.phases: List[str] = []
        FakePhaseTracker.instances.append(self)

    @contextmanager
    def phase(self, name: str):
        self.phases.append(name)
        yield


class FakeQuoteResult:
    def __init__(self, valid: bool) -> None:
        self.valid = valid
        self.invalid_quotes: List[str] = [] if valid else ["<simulated_quote persona_id=\"?\">"]
        self.unbound_evidence_refs: List[str] = [] if valid else ["ev_missing"]


class FakeVerifiedProse:
    def __init__(self, content: str, *, changed: bool = False, rejected: List[str] | None = None) -> None:
        self.content = content
        self.changed = changed
        self.rejected = rejected or []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_outline(n: int = 3) -> ReportOutline:
    return ReportOutline(
        title="Test Report",
        summary="Test summary",
        sections=[
            ReportSection(title=f"Section {i + 1}", content="", description="")
            for i in range(n)
        ],
    )


def _make_ctx(
    *,
    outline: ReportOutline | None = None,
    generated_content: str = "Erzeugter Abschnittsinhalt.",
    total_sections: int = 3,
    **overrides: Any,
) -> SectionContext:
    """Baut einen Kontext, in dem jeder Seam auf einen Fake zeigt."""
    outline = outline or _make_outline(total_sections)
    generate_calls: List[Dict[str, Any]] = []

    def fake_generate_section(agent: Any, **kwargs: Any) -> str:
        generate_calls.append(kwargs)
        return generated_content

    defaults: Dict[str, Any] = {
        "report_id": "report_test123",
        "outline": outline,
        "total_sections": total_sections,
        "generate_section": fake_generate_section,
        "generate_metadata": lambda agent, **kw: {},
        "validate_quotes": lambda *a, **kw: FakeQuoteResult(valid=True),
        "verify_prose_fn": lambda content, pool: FakeVerifiedProse(content),
        "is_fallback": lambda content: False,
        "report_manager": FakeReportManager(),
        "phase_tracker_factory": FakePhaseTracker,
    }
    defaults.update(overrides)
    ctx = SectionContext(**defaults)
    # Für Assertions am Testende erreichbar machen.
    ctx.generate_calls = generate_calls  # type: ignore[attr-defined]
    return ctx


# ---------------------------------------------------------------------------
# 1. Resume-Pfad
# ---------------------------------------------------------------------------


def test_persisted_section_is_restored_without_generating():
    """Ein Abschnitt, der schon auf der Platte liegt, wird nicht neu erzeugt."""
    outline = _make_outline(3)
    ctx = _make_ctx(outline=outline, persisted_section_contents={2: "  Bereits vorhanden.  "})
    agent = FakeAgent(evidence_map={"sections": [{"section_index": 2}]})

    result = process_section(agent, outline.sections[1], ctx, section_index=2)

    assert result.restored is True
    assert result.content == "Bereits vorhanden."
    assert result.failed is False
    assert ctx.generate_calls == [], "Resume darf keine Generierung auslösen"
    assert agent.saved_evidence_calls == [], "Resume darf keine Evidence neu binden"


def test_restored_section_without_persisted_evidence_still_returns_content():
    """Fehlende Evidenz zum Abschnitt wird geloggt, der Inhalt bleibt erhalten."""
    outline = _make_outline(2)
    ctx = _make_ctx(outline=outline, total_sections=2, persisted_section_contents={1: "Alter Text."})
    agent = FakeAgent(evidence_map={"sections": []})

    result = process_section(agent, outline.sections[0], ctx, section_index=1)

    assert result.restored is True
    assert result.content == "Alter Text."


# ---------------------------------------------------------------------------
# 2. Regulärer Durchlauf
# ---------------------------------------------------------------------------


def test_generated_section_reports_content_and_markdown():
    outline = _make_outline(3)
    ctx = _make_ctx(outline=outline, generated_content="Der Abschnittstext.")
    agent = FakeAgent()

    result = process_section(agent, outline.sections[0], ctx, section_index=1)

    assert result.restored is False
    assert result.failed is False
    assert result.content == "Der Abschnittstext."
    assert result.title == "Section 1"
    assert result.markdown == "## Section 1\n\nDer Abschnittstext."
    assert ctx.report_manager.saved_sections == [("report_test123", 1, "Der Abschnittstext.")]
    assert agent.saved_evidence_calls[0][1] == 1


def test_evidence_pfad_bekommt_denselben_bereinigten_text_wie_die_datei():
    """#1316: die Claim-Extraktion bekam rohes <simulated_quote>-Markup.

    ``save_section`` reinigte den Inhalt intern, ``_save_evidence_section``
    bekam dieselbe ungereinigte Variable — Tag-Fragmente landeten damit in
    den Claim-Kandidaten.
    """
    outline = _make_outline(3)
    ctx = _make_ctx(
        outline=outline,
        generated_content="<simulated_quote>Zu eng getaktet.</simulated_quote>",
    )
    agent = FakeAgent()

    process_section(agent, outline.sections[0], ctx, section_index=1)

    evidence_content = agent.saved_evidence_calls[0][3]
    assert "<simulated_quote>" not in evidence_content
    assert evidence_content.startswith("> ")
    assert ctx.report_manager.evidence_prep_calls == [
        "<simulated_quote>Zu eng getaktet.</simulated_quote>"
    ]


def test_evidence_pfad_behaelt_ueberschriften_als_markdown_heading():
    """#1316: der Heading-Umbau des Dateipfads darf die Extraktion nicht erreichen.

    ``_clean_section_content`` wandelt jede Überschrift in Fettschrift. Bekäme
    die Claim-Extraktion dieses Ergebnis, verlöre sie das ``#``-Signal — eine
    Zwischenüberschrift ab acht Wörtern würde als Aussage gebunden, weil der
    Bold-Filter nur darunter greift.
    """
    outline = _make_outline(3)
    heading = "### Reaktionen der Lehrkraefte auf den geplanten Zeitplan im Detail"
    ctx = _make_ctx(outline=outline, generated_content=f"{heading}\n\nDer Text.")
    agent = FakeAgent()

    process_section(agent, outline.sections[0], ctx, section_index=1)

    assert heading in agent.saved_evidence_calls[0][3]


def test_generated_section_reports_progress_before_generating():
    outline = _make_outline(4)
    seen: List[tuple] = []
    ctx = _make_ctx(
        outline=outline,
        total_sections=4,
        progress_callback=lambda stage, prog, msg: seen.append((stage, prog, msg)),
    )

    process_section(FakeAgent(), outline.sections[1], ctx, section_index=2)

    assert seen[0][0] == "generating"
    assert "Generating section: Section 2 (2/4)" in seen[0][2]


def test_base_progress_spans_twenty_to_ninety_percent():
    ctx = _make_ctx(total_sections=4)
    assert ctx.base_progress_for(1) == 20
    assert ctx.base_progress_for(4) == 72
    # Ein leerer Outline darf nicht durch Null teilen.
    assert _make_ctx(total_sections=0).base_progress_for(1) == 20


# ---------------------------------------------------------------------------
# 3. Fehlgeschlagene Generierung (P0-7)
# ---------------------------------------------------------------------------


def test_fallback_content_marks_failure_and_skips_metadata():
    """Fallback-Text erzeugt weder Metadaten noch Claims."""
    outline = _make_outline(2)
    metadata_calls: List[Any] = []

    def tracking_metadata(agent: Any, **kw: Any) -> Dict[str, Any]:
        metadata_calls.append(kw)
        return {"claims": ["darf nicht entstehen"]}

    ctx = _make_ctx(
        outline=outline,
        total_sections=2,
        generated_content="[Abschnitt konnte nicht erzeugt werden]",
        is_fallback=lambda content: content.startswith("[Abschnitt konnte nicht"),
        generate_metadata=tracking_metadata,
    )
    agent = FakeAgent()

    result = process_section(agent, outline.sections[0], ctx, section_index=1)

    assert result.failed is True
    assert result.metadata == {}
    assert metadata_calls == [], "Fallback-Abschnitt darf keine Metadaten extrahieren"
    assert agent.recorded_metadata == []


# ---------------------------------------------------------------------------
# 4. Zitatprüfung (M11.8e / P4.1)
# ---------------------------------------------------------------------------


def _quote_ctx(outline: ReportOutline, results: List[FakeQuoteResult], **overrides: Any) -> SectionContext:
    """Kontext, dessen Zitatprüfung eine vorgegebene Ergebnisfolge liefert."""
    calls = {"n": 0}

    def scripted_validate(*a: Any, **kw: Any) -> FakeQuoteResult:
        result = results[min(calls["n"], len(results) - 1)]
        calls["n"] += 1
        return result

    contents = ["Erster Versuch.", "Reparierter Versuch."]
    gen_calls = {"n": 0}

    def two_shot_generate(agent: Any, **kwargs: Any) -> str:
        content = contents[min(gen_calls["n"], len(contents) - 1)]
        gen_calls["n"] += 1
        return content

    defaults: Dict[str, Any] = {
        "outline": outline,
        "total_sections": len(outline.sections),
        "validate_quotes": scripted_validate,
        "generate_section": two_shot_generate,
    }
    defaults.update(overrides)
    ctx = _make_ctx(**defaults)
    ctx.generate_call_count = gen_calls  # type: ignore[attr-defined]
    return ctx


def test_invalid_quotes_trigger_repair_retry_that_succeeds():
    """Scheitert die Zitatprüfung, ersetzt ein erfolgreicher Repair den Inhalt."""
    outline = ReportOutline(
        title="R", summary="s",
        sections=[ReportSection(title="Persona-Reaktionen", content="", description="")],
    )
    ctx = _quote_ctx(outline, [FakeQuoteResult(valid=False), FakeQuoteResult(valid=True)])

    result = process_section(FakeAgent(), outline.sections[0], ctx, section_index=1)

    assert result.content == "Reparierter Versuch."
    assert result.quote_validation_failed is False
    assert ctx.generate_call_count["n"] == 2, "genau ein Repair-Retry"


def test_failed_repair_sets_flag_and_keeps_section():
    """Auch ein gescheiterter Repair verwirft den Abschnitt nicht."""
    outline = ReportOutline(
        title="R", summary="s",
        sections=[ReportSection(title="Persona-Reaktionen", content="", description="")],
    )
    ctx = _quote_ctx(outline, [FakeQuoteResult(valid=False), FakeQuoteResult(valid=False)])
    section = outline.sections[0]

    result = process_section(FakeAgent(), section, ctx, section_index=1)

    assert result.quote_validation_failed is True
    assert result.content == "Reparierter Versuch."
    assert result.failed is False
    assert section.metadata["quote_validation_failed"] is True


def test_explorative_mode_skips_quote_validation():
    """Im Modus ``explorative`` findet keine Zitatprüfung statt."""
    outline = ReportOutline(
        title="R", summary="s",
        sections=[ReportSection(title="Persona-Reaktionen", content="", description="")],
    )
    validations: List[int] = []
    ctx = _make_ctx(
        outline=outline,
        total_sections=1,
        report_mode="explorative",
        validate_quotes=lambda *a, **kw: validations.append(1) or FakeQuoteResult(valid=False),
    )

    result = process_section(FakeAgent(), outline.sections[0], ctx, section_index=1)

    assert validations == [], "explorative darf die Zitatprüfung nicht aufrufen"
    assert result.quote_validation_failed is False


def test_meta_section_titles_skip_quote_validation():
    """Abschnitte ohne Zitaterwartung werden nicht geprüft."""
    outline = ReportOutline(
        title="R", summary="s",
        sections=[ReportSection(title="Executive Summary", content="", description="")],
    )
    validations: List[int] = []
    ctx = _make_ctx(
        outline=outline,
        total_sections=1,
        validate_quotes=lambda *a, **kw: validations.append(1) or FakeQuoteResult(valid=False),
    )

    process_section(FakeAgent(), outline.sections[0], ctx, section_index=1)

    assert validations == []


# ---------------------------------------------------------------------------
# 5. Fließtext-Verifikation (P0)
# ---------------------------------------------------------------------------


def test_prose_verification_replaces_content_and_records_hypotheses():
    outline = _make_outline(1)
    ctx = _make_ctx(
        outline=outline,
        total_sections=1,
        generated_content="Roher Text mit 42 % Behauptung.",
        verify_prose_fn=lambda content, pool: FakeVerifiedProse(
            "Bereinigter Text.", changed=True, rejected=["42 % Behauptung"]
        ),
    )
    agent = FakeAgent()

    result = process_section(agent, outline.sections[0], ctx, section_index=1)

    assert result.content == "Bereinigter Text."
    assert agent.recorded_prose_hypotheses == [(1, ["42 % Behauptung"])]


def test_prose_verification_is_skipped_for_fallback_content():
    outline = _make_outline(1)
    verifications: List[int] = []
    ctx = _make_ctx(
        outline=outline,
        total_sections=1,
        is_fallback=lambda content: True,
        verify_prose_fn=lambda content, pool: verifications.append(1) or FakeVerifiedProse(content),
    )

    process_section(FakeAgent(), outline.sections[0], ctx, section_index=1)

    assert verifications == []


# ---------------------------------------------------------------------------
# 6. Metadaten (M11.8d / P0-6)
# ---------------------------------------------------------------------------


def test_metadata_is_attached_to_section_and_agent():
    outline = _make_outline(1)
    FakePhaseTracker.instances.clear()
    ctx = _make_ctx(
        outline=outline,
        total_sections=1,
        generate_metadata=lambda agent, **kw: {"key_findings": ["A"]},
    )
    agent = FakeAgent()
    section = outline.sections[0]

    result = process_section(agent, section, ctx, section_index=1)

    assert result.metadata == {"key_findings": ["A"]}
    assert section.metadata["structured_metadata"] == {"key_findings": ["A"]}
    assert agent.recorded_metadata == [(1, {"key_findings": ["A"]})]
    assert agent.report_logger.section_metadata[0]["section_index"] == 1
    assert FakePhaseTracker.instances[-1].phases == ["section_metadata"]


# ---------------------------------------------------------------------------
# 7. Evidence-Ergebnis wird beobachtbar durchgereicht (Vorarbeit Issue #1209)
# ---------------------------------------------------------------------------


def test_result_carries_bound_claims_and_gate_decisions():
    """Was gebunden und was verworfen wurde, steht im SectionResult.

    Vorbedingung für Issue #1209 Befund 6: die Zuordnung von Claims zu
    Evidence ist am Interface prüfbar, ohne die persistierte Evidenzkarte zu
    durchsuchen und ohne ``patch()``.
    """
    outline = _make_outline(1)
    outcome = SectionEvidenceOutcome(
        claims=[{"claim_id": "claim_01", "evidence": ["ev_a"]}],
        hypotheses=[{"hypothesis_id": "hypothesis_01", "hypothesis_text": "Unbelegt."}],
        data_gaps=[{"gap_id": "gap_01"}],
        gate_decisions=[{
            "claim_id": "claim_02",
            "violation": "no_supporting_evidence",
            "action": "moved_to_hypotheses",
            "detail": "Keine direkte Evidence gebunden.",
        }],
    )
    ctx = _make_ctx(outline=outline, total_sections=1)
    agent = FakeAgent(evidence_outcome=outcome)

    result = process_section(agent, outline.sections[0], ctx, section_index=1)

    assert result.bound_claims == [{"claim_id": "claim_01", "evidence": ["ev_a"]}]
    assert result.hypotheses[0]["hypothesis_id"] == "hypothesis_01"
    assert result.gate_decisions[0]["violation"] == "no_supporting_evidence"
    assert result.evidence.data_gaps == [{"gap_id": "gap_01"}]


def test_outcome_reads_from_the_validated_evidence_map():
    """``from_persisted_section`` spiegelt die Karte nach der Validierung.

    Die Reparaturläufe bei ``ValidationError`` können Einträge entfernen —
    maßgeblich ist, was am Ende in der Karte steht.
    """
    validated = {
        "sections": [
            {"section_index": 1, "claims": [{"claim_id": "claim_x"}]},
            {
                "section_index": 2,
                "claims": [{"claim_id": "claim_y"}],
                "hypotheses": [{"hypothesis_id": "hypothesis_01"}],
                "hypotheses_appendix": [{"hypothesis_id": "hypothesis_02"}],
                "data_gaps": [{"gap_id": "gap_01"}],
            },
        ]
    }

    outcome = SectionEvidenceOutcome.from_persisted_section(
        validated, 2, gate_decisions=[{"violation": "no_supporting_evidence"}],
        generation_failed=False,
    )

    assert outcome.claims == [{"claim_id": "claim_y"}]
    assert outcome.hypotheses == [{"hypothesis_id": "hypothesis_01"}]
    assert outcome.hypotheses_appendix == [{"hypothesis_id": "hypothesis_02"}]
    assert outcome.data_gaps == [{"gap_id": "gap_01"}]
    assert outcome.gate_decisions == [{"violation": "no_supporting_evidence"}]
    assert outcome.generation_failed is False


def test_outcome_for_unknown_section_is_empty_not_an_error():
    outcome = SectionEvidenceOutcome.from_persisted_section(
        {"sections": []}, 7, gate_decisions=[], generation_failed=True
    )

    assert outcome.claims == []
    assert outcome.generation_failed is True
