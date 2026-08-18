"""P2.1: Evidence-leere Claim-Kandidaten werden nicht als Claims persistiert."""
from __future__ import annotations

import json
from pathlib import Path

from app.contracts import ReportSectionModel
from app.services.report_agent import ReportAgent


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "bad" / "orphan_all_claims.json"


def test_all_orphan_claims_route_to_hypotheses_and_data_gaps() -> None:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    agent = ReportAgent.__new__(ReportAgent)
    claims, hypotheses, data_gaps, _decisions = agent._finalize_section_claims(raw["claims"])

    assert claims == []
    assert len(hypotheses) == len(raw["claims"])
    assert len(data_gaps) == len(raw["claims"])
    # Der Evidence-Index dieses Agents ist leer — zu den Aussagen liegt
    # tatsächlich nichts vor. Das ist die eine Konstellation, in der ein Data
    # Gap zu Recht entsteht; ein bloß gescheitertes Binding erzeugt seit der
    # Data-Gap-Semantik keinen mehr
    # (siehe tests/regression/test_data_gap_semantics.py).
    assert {gap["gap_reason"] for gap in data_gaps} == {"source_information_absent"}

    section = ReportSectionModel.model_validate(
        {
            "section_index": 1,
            "section_title": "Datenluecken",
            "section_summary": "Alle Claim-Kandidaten ohne Evidence wurden geroutet.",
            "claims": claims,
            "hypotheses": hypotheses,
            "data_gaps": data_gaps,
        }
    )

    assert len(section.claims) == 0
    assert len(section.hypotheses) == 2
    assert len(section.data_gaps) == 2
