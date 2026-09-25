"""Gegenprobe-Auswertung zu #1240: Evidence je Dokument-Rolle."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.evidence_role_audit import UNKNOWN_ROLE, audit_evidence_roles

REPO = Path(__file__).resolve().parents[3]
LAUF = REPO / "agora-lauf-20260811-sim_54c1c2a6a875"


def _map() -> dict:
    return {
        "evidence_index": {
            "ev_a": {"source_kind": "seed_corpus", "snippet": "Fakt A", "document_role": "domain_fact"},
            "ev_b": {"source_kind": "seed_corpus", "snippet": "Erwartung B"},
            "ev_c": {"source_kind": "seed_corpus", "snippet": "Ohne Zuordnung"},
            "ev_q": {"source_kind": "agent_quote", "snippet": "Zitat"},
        },
        "sections": [
            {"claims": [
                {"evidence": [{"evidence_id": "ev_b", "supports_claim": True}]},
                {"evidence": [
                    {"evidence_id": "ev_a", "supports_claim": True},
                    {"evidence_id": "ev_q", "supports_claim": True},
                ]},
            ]},
        ],
    }


def test_rollen_aus_record_und_labels_unbekanntes_bleibt_unknown():
    result = audit_evidence_roles(_map(), {"Erwartung B": "expected_result"})

    assert result["seed_items_by_role"] == {
        "domain_fact": 1, "expected_result": 1, UNKNOWN_ROLE: 1,
    }
    assert result["testcase_share"] == round(1 / 3, 3)
    assert result["claims_supported_only_by_testcase_text"] == 1
    assert result["supporting_bindings_by_role"] == {
        "domain_fact": 1, "expected_result": 1, "not_seed": 1,
    }


def test_referenzlauf_messung_ist_reproduzierbar():
    """Die im Runbook dokumentierten Anteile (29 % / 42 %) bleiben nachrechenbar."""
    labels = json.loads((LAUF / "document-role-labels.json").read_text(encoding="utf-8"))
    shares = {
        name: audit_evidence_roles(
            json.loads((LAUF / name / "evidence_map.json").read_text(encoding="utf-8")), labels
        )["testcase_share"]
        for name in ("report_glm-5.2_9107e3d60b10", "report_deepseek_7ce9e4882bae")
    }
    assert shares == {
        "report_glm-5.2_9107e3d60b10": 0.286,
        "report_deepseek_7ce9e4882bae": 0.417,
    }
