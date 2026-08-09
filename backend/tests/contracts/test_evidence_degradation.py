"""Tests für die graziöse Degradation nach Issue #1006.

Deckt drei Bausteine ab, ohne die ADR-0002-Hartanker anzufassen:

- ``degrade_sections_for_violations`` (app.services.report_agent.evidence) —
  repariert Sections nach einem fehlgeschlagenen Contract-Validate.
- ``apply_degradation_downgrade`` (app.services.report_agent.output_contract) —
  stuft COMPLETED auf INCOMPLETE ab, wenn degradiert wurde.
- die dreistufige try/except-Reaktion in ``ReportAgent._save_evidence_section``.

Der letzte Test (``test_medium_validator_bleibt_streng``) beweist, dass der
Contract-Validator selbst (ADR-0002 Anker 6, ``agent_grounded_for_medium``)
weiterhin ohne Kompromiss ablehnt — nur die Reaktion auf den Verstoss wurde
verändert, nicht der Verstoss toleriert.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.contracts import EvidenceMapModel
from app.models.report import ReportStatus
from app.services.report_agent import ReportAgent
from app.services.report_agent.evidence import (
    degrade_sections_for_violations,
    normalize_sections_for_contract,
)
from app.services.report_agent.output_contract import (
    apply_degradation_downgrade,
    is_deliverable_report_status,
)

_SEED_EVIDENCE_ID = "ev_00000000000000000000000000000001"


class _FakeAgentForDegradation:
    """Leichtgewichtiges Fake-Objekt für den ungebundenen Aufruf von
    ``ReportAgent._save_evidence_section`` (agent.py:684-843).

    Spiegelt nur die dort tatsächlich verwendeten Attribute/Methoden — kein
    echter ``ReportAgent``, da dessen Konstruktion (LLM-Client, Graph-Tools)
    für diesen Test unnötig teuer wäre.
    """

    def __init__(
        self,
        *,
        evidence_map: dict,
        claims: list,
        hypotheses: list | None = None,
        data_gaps: list | None = None,
    ) -> None:
        self.evidence_map = evidence_map
        self._pending_prose_hypotheses: dict = {}
        self._pending_section_metadata: dict = {}
        self._collect_simulation_evidence_items = lambda: []
        self._build_claims_for_section = lambda content: []
        self._finalize_section_claims = lambda raw: (
            claims,
            hypotheses or [],
            data_gaps or [],
            [],
        )
        self._truncate = lambda text, length: (
            text[:length] if isinstance(text, str) else text
        )
        self._section_dedup_check = lambda **kwargs: None
        self._init_evidence_map = lambda report_id: None


def _valid_existing_section() -> dict:
    return {
        "section_index": 1,
        "section_title": "Erste Sektion",
        "section_summary": "Kurze Zusammenfassung des ersten Abschnitts.",
        "claims": [],
        "hypotheses": [],
        "hypotheses_appendix": [],
        "data_gaps": [],
        "structured_metadata": {},
        "generation_failed": False,
    }


def _seed_only_medium_claim() -> dict:
    """Medium-Claim mit ausschliesslich seed_corpus-Evidence — verletzt
    ``agent_grounded_for_medium`` (ADR-0002 Anker 6): fehlt agent_quote."""
    return {
        "claim_id": "claim_01",
        "claim_text": "Claim ohne agent-grounded Evidence fuer medium-Label.",
        "confidence_label": "medium",
        "confidence_score": 0.5,
        "evidence": [
            {
                "evidence_id": _SEED_EVIDENCE_ID,
                "supports_claim": True,
            },
        ],
        "audit_trail": [],
    }


# ---------------------------------------------------------------------------
# 1. _save_evidence_section: Verstoss haelt uebrige Sections
# ---------------------------------------------------------------------------


def test_medium_violation_haelt_uebrige_sections():
    fake_agent = _FakeAgentForDegradation(
        evidence_map={
            "schema_version": 3,
            "report_id": "r1",
            "simulation_id": "sim1",
            "evidence_index": {
                _SEED_EVIDENCE_ID: {
                    "evidence_id": _SEED_EVIDENCE_ID,
                    "producer_key": "seed_dokument_01#degradation-fixture",
                    "type": "graph_fact",
                    "source": "seed_dokument_01",
                    "snippet": "Beleg-Snippet aus dem Seed-Korpus.",
                    "source_kind": "seed_corpus",
                }
            },
            "global_evidence_refs": [],
            "sections": [_valid_existing_section()],
            "degradation_log": [],
        },
        claims=[_seed_only_medium_claim()],
    )

    with patch("app.services.report_agent.ReportManager.save_evidence_map") as mock_save:
        ReportAgent._save_evidence_section(
            fake_agent,
            "r1",
            2,
            "Zweite Sektion mit Verstoss",
            "Ausfuehrlicher Abschnittstext fuer die zweite Sektion.",
        )
        mock_save.assert_called_once()
        persisted = mock_save.call_args[0][1]

    # Re-Validierung des persistierten Payloads muss bestehen — kein
    # ValidationError mehr nach der Reparatur.
    EvidenceMapModel.model_validate(persisted)

    sections_by_index = {s["section_index"]: s for s in persisted["sections"]}
    assert set(sections_by_index) == {1, 2}
    assert sections_by_index[1]["section_title"] == "Erste Sektion"

    section2 = sections_by_index[2]
    claim_ids = [c["claim_id"] for c in section2["claims"]]
    hypothesis_texts = [h["hypothesis_text"] for h in section2["hypotheses"]]

    assert len(persisted["degradation_log"]) == 1
    entry = persisted["degradation_log"][0]

    if "claim_01" in claim_ids:
        repaired_claim = next(c for c in section2["claims"] if c["claim_id"] == "claim_01")
        assert repaired_claim["confidence_label"] == "low"
        assert entry["action"] == "downgraded_to_low"
    else:
        assert any("Claim ohne agent-grounded" in t for t in hypothesis_texts)
        assert entry["action"] == "moved_to_hypotheses"


def test_root_validator_targets_section_when_claim_ids_repeat():
    first_section = _valid_existing_section()
    first_section["claims"] = [_seed_only_medium_claim()]
    second_section = _valid_existing_section()
    second_section["section_index"] = 2
    second_section["section_title"] = "Zweite Sektion"
    second_section["claims"] = [_seed_only_medium_claim()]
    payload = {
        "schema_version": 3,
        "report_id": "r-duplicate-claims",
        "simulation_id": "sim-duplicate-claims",
        "evidence_index": {
            _SEED_EVIDENCE_ID: {
                "evidence_id": _SEED_EVIDENCE_ID,
                "producer_key": "seed:duplicate-claim-fixture",
                "type": "graph_fact",
                "source": "seed",
                "snippet": "Seed-only Evidence.",
                "source_kind": "seed_corpus",
            }
        },
        "global_evidence_refs": [],
        "sections": [first_section, second_section],
    }

    with pytest.raises(ValidationError) as exc_info:
        EvidenceMapModel.model_validate(payload)

    repaired, _ = degrade_sections_for_violations(
        payload["sections"], exc_info.value
    )

    assert repaired[0]["claims"][0]["confidence_label"] == "low"
    assert repaired[1]["claims"][0]["confidence_label"] == "medium"


# ---------------------------------------------------------------------------
# 2. normalize_sections_for_contract filtert hypotheses_appendix-Platzhalter
# ---------------------------------------------------------------------------


def test_hypotheses_appendix_placeholder_wird_gefiltert():
    sections = [
        {
            "section_index": 1,
            "section_title": "Sektion mit Appendix-Platzhalter",
            "section_summary": "Zusammenfassung des Abschnitts.",
            "claims": [],
            "hypotheses": [],
            "hypotheses_appendix": [
                {
                    "hypothesis_id": "hypothesis_01",
                    "hypothesis_text": "",
                    "rationale": "Ausreichend lange Begruendung fuer den Eintrag.",
                    "suggested_evidence": [],
                },
            ],
            "data_gaps": [],
            "structured_metadata": {},
            "generation_failed": False,
        },
    ]

    normalized = normalize_sections_for_contract(sections)

    assert normalized[0]["hypotheses_appendix"] == []

    payload = {
        "schema_version": 3,
        "report_id": "r1",
        "simulation_id": "sim1",
        "evidence_index": {},
        "global_evidence_refs": [],
        "sections": normalized,
    }
    validated = EvidenceMapModel.model_validate(payload)
    assert validated.sections[0].hypotheses_appendix == []


# ---------------------------------------------------------------------------
# 3. Claim ohne Evidence und zu kurzem claim_text wird gedroppt, nicht als
#    zu kurze Hypothese eingefuegt.
# ---------------------------------------------------------------------------


def test_claim_ohne_evidence_und_zu_kurz_wird_gedroppt():
    sections = [
        {
            "section_index": 1,
            "section_title": "Sektion mit kurzem Claim",
            "section_summary": "Zusammenfassung des Abschnitts.",
            "claims": [
                {
                    "claim_id": "claim_01",
                    "claim_text": "Kurz",
                    "confidence_label": "low",
                    "confidence_score": 0.1,
                    "evidence": [],
                    "audit_trail": [],
                },
            ],
            "hypotheses": [],
            "hypotheses_appendix": [],
            "data_gaps": [],
            "structured_metadata": {},
            "generation_failed": False,
        },
    ]

    with pytest.raises(ValidationError) as excinfo:
        EvidenceMapModel.model_validate(
            {
                "schema_version": 2,
                "report_id": "r1",
                "simulation_id": "sim1",
                "global_evidence": [],
                "sections": sections,
            }
        )

    repaired, violations = degrade_sections_for_violations(
        sections, excinfo.value, logger=None
    )

    assert repaired[0]["claims"] == []
    assert len(violations) == 1
    assert violations[0]["action"] == "dropped"
    assert repaired[0]["hypotheses"] == []
    assert all(
        len(h["hypothesis_text"]) >= 8 for h in repaired[0].get("hypotheses", [])
    )


# ---------------------------------------------------------------------------
# 4. apply_degradation_downgrade: COMPLETED -> INCOMPLETE, aber nur bei
#    nicht-leerem Log; FAILED wird nicht aufgewertet.
# ---------------------------------------------------------------------------


def test_degradation_log_erzwingt_incomplete():
    entry = {
        "section_index": 1,
        "claim_id": "claim_01",
        "violation": "value_error",
        "action": "downgraded_to_low",
        "detail": "Testeintrag.",
    }

    assert (
        apply_degradation_downgrade(ReportStatus.COMPLETED, [entry])
        == ReportStatus.INCOMPLETE
    )
    assert (
        apply_degradation_downgrade(ReportStatus.COMPLETED, [])
        == ReportStatus.COMPLETED
    )
    assert (
        apply_degradation_downgrade(ReportStatus.FAILED, [entry])
        == ReportStatus.FAILED
    )


# ---------------------------------------------------------------------------
# 5. Hartanker-Beweis: der medium-Validator bleibt streng.
# ---------------------------------------------------------------------------


def test_medium_validator_bleibt_streng():
    payload = {
        "schema_version": 2,
        "report_id": "r1",
        "simulation_id": "sim1",
        "global_evidence": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Sektion mit strengem Validator",
                "section_summary": "Zusammenfassung des Abschnitts.",
                "claims": [_seed_only_medium_claim()],
                "hypotheses": [],
                "hypotheses_appendix": [],
                "data_gaps": [],
                "structured_metadata": {},
                "generation_failed": False,
            },
        ],
    }

    with pytest.raises(ValidationError):
        EvidenceMapModel.model_validate(payload)


# ---------------------------------------------------------------------------
# 6. Zustellung: INCOMPLETE ist ein Teilergebnis, kein Fehlschlag
# ---------------------------------------------------------------------------


def test_incomplete_report_ist_auslieferbar():
    """PR-Review #1011 (Codex P1): ohne diese Unterscheidung landet ein
    degradierter Report im failed-Zweig von ``ReportGenerationService`` und der
    Nutzer liest "Report generation failed", obwohl das Ergebnis vorliegt —
    der Fix aus #1006 waere in der Oberflaeche wirkungslos."""
    assert is_deliverable_report_status(ReportStatus.INCOMPLETE) is True
    assert is_deliverable_report_status(ReportStatus.COMPLETED) is True

    assert is_deliverable_report_status(ReportStatus.FAILED) is False
    assert is_deliverable_report_status(ReportStatus.PENDING) is False
    assert is_deliverable_report_status(ReportStatus.PLANNING) is False
    assert is_deliverable_report_status(ReportStatus.GENERATING) is False


def test_report_generation_liefert_incomplete_statt_zu_scheitern():
    """Der Produktivpfad in ``report_generation.py`` nutzt genau diese
    Unterscheidung — ein Test auf den Helper allein wuerde eine spaetere
    Rueckkehr zum harten ``== COMPLETED`` nicht bemerken."""
    import inspect

    from app.services import report_generation

    source = inspect.getsource(report_generation.ReportGenerationService.start_generation)
    assert "is_deliverable_report_status(report.status)" in source, (
        "start_generation entscheidet nicht mehr ueber is_deliverable_report_status — "
        "ein degradierter Report wuerde wieder als Fehlschlag zugestellt."
    )
