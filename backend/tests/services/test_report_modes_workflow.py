"""Tests für Mode-abhängiges Verhalten in Report-Agent-Workflow und Renderer.

Sub-Slice P4.1 — Refs PLAN.md §5.1

Abgedeckt:
- strict: Claims ohne evidence_refs werden gedroppt (kein Hypothesis-Routing)
- strict: Low-confidence Claims werden gedroppt
- balanced: aktuelles Verhalten — Claims mit Evidence bleiben, Low-conf markiert
- explorative: alle Claims durch (keine Filterung)
- markdown_renderer: Banner erscheint für alle drei Modi
- build_report_v3 nimmt report_mode und schreibt ihn in ReportV3
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.contracts.report_v3 import ReportV3


# ---------------------------------------------------------------------------
# Shared Stub-Evidence-Map
# ---------------------------------------------------------------------------

def _make_evidence_map(
    *,
    include_low_confidence: bool = True,
    include_no_evidence: bool = True,
) -> dict[str, Any]:
    claims: list[dict[str, Any]] = [
        {
            "claim_id": "claim_high_ev",
            "claim_text": "Sicherheitsbedenken hemmen die Adoption nachweislich.",
            "confidence_label": "high",
            "evidence": [
                {
                    "source_id_anchor": "kg:metric:adoption_friction",
                    "type": "graph_metric",
                    "snippet": "adoption_friction: 0.72",
                    "supports_claim": True,
                }
            ],
        },
    ]
    if include_low_confidence:
        claims.append({
            "claim_id": "claim_low",
            "claim_text": "Niedrig-Konfidenz-Claim mit Evidence-Anker.",
            "confidence_label": "low",
            "evidence": [
                {
                    "source_id_anchor": "kg:metric:uncertainty_score",
                    "type": "graph_metric",
                    "snippet": "uncertainty_score: 0.9",
                    "supports_claim": False,
                }
            ],
        })
    if include_no_evidence:
        claims.append({
            "claim_id": "claim_no_ev",
            "claim_text": "Claim ganz ohne Evidence-Anker — kein Beleg vorhanden.",
            "confidence_label": "medium",
            "evidence": [],
        })

    return {
        "schema_version": 2,
        "report_id": "report_test_modes01",
        "simulation_id": "sim_test_modes001",
        "global_evidence": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Analyse",
                "section_summary": "Hauptanalyse",
                "claims": claims,
                "data_gaps": [],
                "hypotheses": [],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Tests: build_report_v3 — Mode-Parameter schreibt report_mode in ReportV3
# ---------------------------------------------------------------------------

class TestBuildReportV3Mode:
    def _make_report(self):
        from app.models.report import Report, ReportStatus  # noqa: PLC0415
        return Report(
            report_id="report_test_modes01",
            simulation_id="sim_test_modes001",
            graph_id="graph_test000001",
            simulation_requirement="Test",
            status=ReportStatus.COMPLETED,
            markdown_content="# Test",
        )

    def test_build_report_v3_default_mode_is_balanced(self):
        """build_report_v3 ohne mode → report_mode='balanced'."""
        from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

        evidence_map = _make_evidence_map()
        report = self._make_report()
        v3 = ReportManager.build_report_v3(report, evidence_map)
        assert v3.report_mode == "balanced"

    def test_build_report_v3_strict_mode_propagated(self):
        """build_report_v3 mit mode='strict' → report_mode='strict'."""
        from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

        evidence_map = _make_evidence_map()
        report = self._make_report()
        v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="strict")
        assert v3.report_mode == "strict"

    def test_build_report_v3_explorative_mode_propagated(self):
        """build_report_v3 mit mode='explorative' → report_mode='explorative'."""
        from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

        evidence_map = _make_evidence_map()
        report = self._make_report()
        v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="explorative")
        assert v3.report_mode == "explorative"


# ---------------------------------------------------------------------------
# Tests: Mode-abhängige Claim-Filterung
# ---------------------------------------------------------------------------

class TestClaimFilteringByMode:
    def _make_report(self):
        from app.models.report import Report, ReportStatus  # noqa: PLC0415
        return Report(
            report_id="report_test_modes01",
            simulation_id="sim_test_modes001",
            graph_id="graph_test000001",
            simulation_requirement="Test",
            status=ReportStatus.COMPLETED,
            markdown_content="# Test",
        )

    def test_strict_mode_drops_no_evidence_claims(self):
        """strict: Claims ohne evidence_refs werden gedroppt."""
        from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

        evidence_map = _make_evidence_map(include_no_evidence=True, include_low_confidence=False)
        report = self._make_report()
        v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="strict")
        claim_ids = {c.id for c in v3.claims}
        # claim_no_ev hat keine evidence → muss weg sein in strict
        assert "claim_no_ev" not in claim_ids

    def test_strict_mode_drops_low_confidence_claims(self):
        """strict: Low-confidence Claims werden gedroppt."""
        from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

        evidence_map = _make_evidence_map(include_no_evidence=False, include_low_confidence=True)
        report = self._make_report()
        v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="strict")
        claim_ids = {c.id for c in v3.claims}
        assert "claim_low" not in claim_ids
        # High-confidence Claim bleibt
        assert "claim_high_ev" in claim_ids

    def test_balanced_mode_keeps_high_confidence(self):
        """balanced: High-confidence Claims mit Evidence bleiben drin."""
        from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

        evidence_map = _make_evidence_map(include_no_evidence=False, include_low_confidence=False)
        report = self._make_report()
        v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="balanced")
        claim_ids = {c.id for c in v3.claims}
        assert "claim_high_ev" in claim_ids

    def test_explorative_mode_keeps_all_with_evidence(self):
        """explorative: Claims mit Evidence bleiben alle durch."""
        from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

        evidence_map = _make_evidence_map(include_no_evidence=False, include_low_confidence=True)
        report = self._make_report()
        v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="explorative")
        claim_ids = {c.id for c in v3.claims}
        # Im explorative-Modus bleibt claim_low drin (nicht gedroppt)
        assert "claim_low" in claim_ids
        assert "claim_high_ev" in claim_ids


# ---------------------------------------------------------------------------
# Tests: Markdown-Banner je Mode
# ---------------------------------------------------------------------------

class TestMarkdownBannerByMode:
    def _make_report_v3(self, mode: str) -> ReportV3:
        return ReportV3(
            report_id="rep-banner-test",
            generated_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
            report_mode=mode,  # type: ignore[arg-type]
        )

    def test_strict_banner_present(self):
        """render_report_v3 mit strict → Banner mit 'strict' im Header."""
        from app.services.report_agent.markdown_renderer import render_report_v3  # noqa: PLC0415

        v3 = self._make_report_v3("strict")
        rendered = render_report_v3(v3)
        assert "strict" in rendered
        assert "Report-Modus" in rendered

    def test_balanced_banner_present(self):
        """render_report_v3 mit balanced → Banner mit 'balanced' im Header."""
        from app.services.report_agent.markdown_renderer import render_report_v3  # noqa: PLC0415

        v3 = self._make_report_v3("balanced")
        rendered = render_report_v3(v3)
        assert "balanced" in rendered
        assert "Report-Modus" in rendered

    def test_explorative_banner_present(self):
        """render_report_v3 mit explorative → Banner mit 'EXPLORATIVE' im Header."""
        from app.services.report_agent.markdown_renderer import render_report_v3  # noqa: PLC0415

        v3 = self._make_report_v3("explorative")
        rendered = render_report_v3(v3)
        assert "EXPLORATIVE" in rendered or "explorative" in rendered
        assert "Report-Modus" in rendered

    def test_banner_appears_before_first_section(self):
        """Banner erscheint vor dem ersten Tabellen-Header."""
        from app.services.report_agent.markdown_renderer import render_report_v3  # noqa: PLC0415

        v3 = self._make_report_v3("strict")
        rendered = render_report_v3(v3)
        banner_pos = rendered.find("Report-Modus")
        table_pos = rendered.find("## Persona-Tabelle")
        assert banner_pos < table_pos, "Banner muss vor Persona-Tabelle stehen"
