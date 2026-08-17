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

# Issue #1341: ReportV3 exportiert abschnittsqualifizierte Claim-IDs
# (``C<abschnitt>_<i>``), weil die abschnittsinterne ``claim_id`` beim Merge
# kollidiert. Damit ist die Roh-ID kein Identifikator mehr — die Tests greifen
# den Claim ueber seine Aussage, die den Filterpfad unveraendert ueberlebt.
_CLAIM_HIGH_EV = "Sicherheitsbedenken hemmen die Adoption nachweislich."
_CLAIM_LOW = "Niedrig-Konfidenz-Claim mit Evidence-Anker."
_CLAIM_NO_EV = "Claim ganz ohne Evidence-Anker — kein Beleg vorhanden."
_CLAIM_FLOOR = "Ein Claim mit variabler Evidence-Anzahl."


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
            # Zwei Quellen tragen die hohe Confidence dieses Claims.
            "evidence": [
                {
                    "source_id_anchor": "kg:metric:adoption_friction",
                    "type": "graph_metric",
                    "snippet": "adoption_friction: 0.72",
                    "supports_claim": True,
                },
                {
                    "source_id_anchor": "kg:metric:trust_deficit",
                    "type": "graph_metric",
                    "snippet": "trust_deficit: 0.65",
                    "supports_claim": True,
                },
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
        claim_statements = {c.statement for c in v3.claims}
        # claim_no_ev hat keine evidence → muss weg sein in strict
        assert _CLAIM_NO_EV not in claim_statements

    def test_strict_mode_drops_low_confidence_claims(self):
        """strict: Low-confidence Claims werden gedroppt."""
        from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

        evidence_map = _make_evidence_map(include_no_evidence=False, include_low_confidence=True)
        report = self._make_report()
        v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="strict")
        claim_statements = {c.statement for c in v3.claims}
        assert _CLAIM_LOW not in claim_statements
        # High-confidence Claim bleibt
        assert _CLAIM_HIGH_EV in claim_statements

    def test_balanced_mode_keeps_high_confidence(self):
        """balanced: High-confidence Claims mit Evidence bleiben drin."""
        from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

        evidence_map = _make_evidence_map(include_no_evidence=False, include_low_confidence=False)
        report = self._make_report()
        v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="balanced")
        claim_statements = {c.statement for c in v3.claims}
        assert _CLAIM_HIGH_EV in claim_statements

    def test_explorative_mode_keeps_only_supported_claims(self):
        """explorative: Thematisch verwandte, nicht stützende Bindings zählen nicht."""
        from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

        evidence_map = _make_evidence_map(include_no_evidence=False, include_low_confidence=True)
        report = self._make_report()
        v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="explorative")
        claim_statements = {c.statement for c in v3.claims}
        # claim_low hat nur ein nicht stützendes Binding und damit keinen Beleg.
        assert _CLAIM_LOW not in claim_statements
        assert _CLAIM_HIGH_EV in claim_statements


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


# ---------------------------------------------------------------------------
# Tests: ADR-0002 — ein stützender Beleg trägt einen low Claim
# ---------------------------------------------------------------------------

def _make_evidence_map_with_evidence_count(evidence_count: int) -> dict:
    """Erzeugt eine Evidence-Map mit einem Claim mit `evidence_count` Evidence-Items."""
    evidence = [
        {
            "source_id_anchor": f"kg:metric:source_{i}",
            "type": "graph_metric",
            "snippet": f"metric_{i}: 0.8",
            "supports_claim": True,
        }
        for i in range(evidence_count)
    ]
    return {
        "schema_version": 2,
        "report_id": "report_test_floor01",
        "simulation_id": "sim_test_floor001",
        "global_evidence": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Evidence-Floor-Test",
                "section_summary": "Testabschnitt für den Evidence-Floor",
                "claims": [
                    {
                        "claim_id": "claim_floor_test",
                        "claim_text": "Ein Claim mit variabler Evidence-Anzahl.",
                        "confidence_label": "low" if evidence_count == 1 else "high",
                        "confidence_score": 0.75,
                        "evidence": evidence,
                    }
                ],
                "data_gaps": [],
                "hypotheses": [],
            }
        ],
    }


class TestEvidenceFloorS1:
    def _make_report(self):
        from app.models.report import Report, ReportStatus  # noqa: PLC0415
        return Report(
            report_id="report_test_floor01",
            simulation_id="sim_test_floor001",
            graph_id="graph_test000001",
            simulation_requirement="Test",
            status=ReportStatus.COMPLETED,
            markdown_content="# Test",
        )

    def test_single_evidence_keeps_low_claim(self):
        """ADR-0002: Ein stützendes Evidence-Item trägt einen low Claim."""
        from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

        evidence_map = _make_evidence_map_with_evidence_count(1)
        report = self._make_report()
        v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="balanced")
        claim_statements = {c.statement for c in v3.claims}
        assert _CLAIM_FLOOR in claim_statements
        claim = next(item for item in v3.claims if item.statement == _CLAIM_FLOOR)
        assert claim.confidence == "low"
        assert len(claim.evidence_refs) == 1
        assert claim.evidence_refs[0].startswith("ev_")
        assert not v3.hypotheses

    def test_two_evidence_keeps_claim(self):
        """Zwei stützende Evidence-Items bleiben unverändert ein Claim."""
        from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

        evidence_map = _make_evidence_map_with_evidence_count(2)
        report = self._make_report()
        v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="balanced")
        claim_statements = {c.statement for c in v3.claims}
        assert _CLAIM_FLOOR in claim_statements
