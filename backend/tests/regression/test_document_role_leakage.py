"""Szenario- und Erwartungstext stützt keinen Claim (Issue #1240).

Referenz: ``report_40236c4a59f0`` / ``sim_8495a5fe314b``. Der einzige
validierte Claim des Laufs (``claim_20``, Confidence 0.71) zitierte einen Satz,
den das Seed-Dokument als erwartetes Ergebnis mitlieferte.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from app.contracts.document_manifest_contract import (
    DocumentManifest,
    DocumentManifestEntry,
    DocumentRole,
    parse_document_roles,
)
from app.contracts.report_contract import EvidenceRecordModel
from app.services import document_roles as document_roles_module
from app.services.confidence_calculator import compute_confidence
from app.services.evidence_binder import bind_evidence_to_claim
from app.services.evidence_entailment import EntailmentVerdict, classify_evidence
from app.services.report_agent import ReportAgent
from app.services.report_agent.evidence import document_role_of

CLAIM_20 = "Der Betriebsrat wird zustimmen, weil keine Dozentendaten erhoben werden."


def _seed_item(role: str | None) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "evidence_id": f"ev_seed_{role}",
        "snippet": CLAIM_20,
        "type": "seed_document",
        "source_kind": "seed_corpus",
        "source_id_anchor": "seed_doc:erwartung#chunk:0",
    }
    if role is not None:
        item["document_role"] = role
    return item


def _judge_must_not_be_asked(_claim: str, _evidence: str) -> str:
    raise AssertionError("Szenario-Text darf keinen Judge-Call auslösen")


def _embed(_text: str) -> List[float]:
    return [1.0, 0.0, 0.0]


@pytest.mark.parametrize("role", ["scenario_statement", "requirement", "expected_result"])
def test_szenario_text_stuetzt_nie(role):
    result = classify_evidence(CLAIM_20, _seed_item(role), judge=_judge_must_not_be_asked)
    assert result.verdict is EntailmentVerdict.RELATED_ONLY
    assert "non_supporting_document_role" in result.checks
    assert role in result.reason


@pytest.mark.parametrize("role", [None, "domain_fact", "background"])
def test_domaenenfakt_mit_gleichem_wortlaut_stuetzt_weiter(role):
    """Gegenprobe: die Rolle ist die einzige Änderung, nicht der Text."""
    result = classify_evidence(CLAIM_20, _seed_item(role))
    assert result.verdict is EntailmentVerdict.SUPPORTED


def test_szenario_text_widerspricht_auch_nicht():
    """Eine erwartete Antwort, die nicht eintritt, ist kein Gegenbeleg."""
    item = _seed_item("expected_result")
    item["snippet"] = "Der Betriebsrat wird nicht zustimmen, weil Dozentendaten erhoben werden."
    result = classify_evidence(CLAIM_20, item)
    assert result.verdict is EntailmentVerdict.RELATED_ONLY


def test_claim_20_allein_auf_erwartungstext_bleibt_auf_dem_boden():
    bound = bind_evidence_to_claim(
        CLAIM_20, [_seed_item("expected_result")], _embed, threshold=0.5
    )
    assert bound[0]["supports_claim"] is False
    score, label = compute_confidence([{**_seed_item("expected_result"), **bound[0]}])
    assert (score, label) == (0.15, "speculative")


def test_hypothese_benennt_den_testfall_als_herkunft():
    bound = bind_evidence_to_claim(
        CLAIM_20, [_seed_item("expected_result")], _embed, threshold=0.5
    )
    agent = ReportAgent.__new__(ReportAgent)
    claims, hypotheses, _gaps, _decisions = agent._finalize_section_claims(
        [
            {
                "claim_id": "claim_20",
                "claim_text": CLAIM_20,
                "confidence_label": "speculative",
                "confidence_score": 0.15,
                "evidence": bound,
                "audit_trail": [],
            }
        ]
    )
    assert claims == []
    assert "kein Simulationsbefund" in hypotheses[0]["rationale"]


# --- Contract und Herkunft ---------------------------------------------------


def test_manifest_altbestand_ohne_rolle_ist_domaenenfakt():
    entry = DocumentManifestEntry.model_validate(
        {"document_id": "a", "filename": "a.md", "start_offset": 0, "end_offset": 3}
    )
    assert entry.document_role is DocumentRole.domain_fact


def test_upload_rollen_werden_streng_geparst():
    domain = DocumentRole.domain_fact
    assert parse_document_roles(None, 2) == [domain, domain]
    assert parse_document_roles(" ", 1) == [domain]
    assert parse_document_roles('["domain_fact", "requirement"]', 2) == [
        domain,
        DocumentRole.requirement,
    ]
    with pytest.raises(ValueError):
        parse_document_roles('["loesung"]', 1)
    with pytest.raises(ValueError):
        parse_document_roles("kein json", 1)
    with pytest.raises(ValueError, match="one role per file"):
        parse_document_roles('["requirement"]', 2)
    with pytest.raises(ValueError):
        # Die alte Form {Dateiname: Rolle} konnte gleichnamige Uploads nicht
        # unterscheiden (Codex-Review PR #1606).
        parse_document_roles('{"a.md": "requirement"}', 1)


def test_evidence_record_traegt_rolle_und_lehnt_unbekannte_ab():
    base = {
        "evidence_id": "ev_" + "0" * 32,
        "type": "seed_document",
        "source_kind": "seed_corpus",
        "source": "erwartung.md",
        "snippet": "x",
        "producer_key": "seed-doc:a:0",
        "source_id_anchor": "seed_doc:a#chunk:0",
    }
    record = EvidenceRecordModel.model_validate({**base, "document_role": "expected_result"})
    assert record.document_role is DocumentRole.expected_result
    assert EvidenceRecordModel.model_validate(base).document_role is None
    with pytest.raises(ValidationError):
        EvidenceRecordModel.model_validate({**base, "document_role": "loesung"})


def test_rolle_kommt_ueber_die_provenance_an_das_item():
    roles = {"erwartung": "expected_result"}
    assert document_role_of({"document_id": "erwartung", "chunk_id": 0}, roles) == "expected_result"
    assert document_role_of({"document_id": "szenario", "chunk_id": 0}, roles) is None
    assert document_role_of(None, roles) is None
    assert document_role_of({"document_id": "erwartung"}, {}) is None


def test_projekt_rollen_ohne_standardrolle(monkeypatch):
    manifest = DocumentManifest(
        documents=[
            DocumentManifestEntry(document_id="s", filename="s.md", start_offset=0, end_offset=1),
            DocumentManifestEntry(
                document_id="e",
                filename="e.md",
                start_offset=1,
                end_offset=2,
                document_role=DocumentRole.expected_result,
            ),
        ]
    )
    monkeypatch.setattr(
        document_roles_module.ProjectManager, "get_document_manifest", lambda _pid: manifest
    )
    assert document_roles_module.load_document_roles("proj_1") == {"e": "expected_result"}
    assert document_roles_module.load_document_roles(None) == {}
