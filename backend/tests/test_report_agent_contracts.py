"""
Tests für die EvidenceMapModel-Boundary-Validation in report_agent.py.

Sub-Slice 02c — Refs #107.
Prüft: _init_evidence_map, _save_evidence_section, Fallback-Init im Tool-Loop.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.contracts import EvidenceMapModel
from app.services.evidence_migrations import CURRENT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(tmp_path) -> object:
    """Erstellt einen minimalen ReportAgent mit gemockten Abhängigkeiten."""
    from app.services.report_agent import ReportAgent

    graph_tools_mock = MagicMock()
    llm_mock = MagicMock()

    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_test"
    agent.simulation_id = "sim_test"
    agent.simulation_requirement = "Testreq"
    agent.llm = llm_mock
    agent.web_tools = MagicMock()
    agent.graph_tools = graph_tools_mock
    agent.tools = {}
    agent.report_logger = None
    agent.console_logger = None
    agent.evidence_map = None
    agent._active_section_evidence = []
    agent._current_section_index = None
    agent._embed_cache = None
    return agent


def _make_valid_evidence_item() -> dict:
    return {
        "type": "graph_metric",
        "source": "simulation_metrics",
        "snippet": "echo_chamber_index: 0.42",
        "match_score": 0.7,
        "supports_claim": True,
    }


# ---------------------------------------------------------------------------
# Test 1: _init_evidence_map — schema_version == 3 und EvidenceMapModel-konform
# ---------------------------------------------------------------------------

def test_init_evidence_map_sets_schema_version_3(tmp_path):
    """_init_evidence_map muss schema_version=3 setzen und EvidenceMapModel-konform sein."""
    agent = _make_agent(tmp_path)

    # _collect_simulation_evidence_items liefert leere Liste (keine echte Simulation)
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])

    agent._init_evidence_map("report_abc123")

    assert agent.evidence_map is not None
    assert agent.evidence_map["schema_version"] == CURRENT_SCHEMA_VERSION
    assert agent.evidence_map["schema_version"] == 3
    assert agent.evidence_map["report_id"] == "report_abc123"
    assert agent.evidence_map["simulation_id"] == "sim_test"
    assert isinstance(agent.evidence_map["sections"], list)

    # Nochmals gegen das Modell validieren — darf keine Exception werfen
    validated = EvidenceMapModel.model_validate(agent.evidence_map)
    assert validated.schema_version == 3


# ---------------------------------------------------------------------------
# Test 2: _save_evidence_section — invalide Section wirft ValidationError
#         BEVOR ReportManager.save_evidence_map aufgerufen wird
# ---------------------------------------------------------------------------

def test_save_evidence_section_invalid_section_raises_before_persist(tmp_path):
    """
    Wenn _build_claims_for_section einen Claim mit leerem claim_text liefert
    UND section_title fehlt (section_title=''), muss EvidenceMapModel
    ValidationError werfen, bevor save_evidence_map aufgerufen wird.
    """
    agent = _make_agent(tmp_path)
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])

    # evidence_map vorinitialisieren (gültiger Zustand)
    agent.evidence_map = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "report_id": "report_abc123",
        "simulation_id": "sim_test",
        "global_evidence": [],
        "sections": [],
    }

    # _build_claims_for_section → leere claims-Liste, aber section_title="" verletzt
    # ReportSectionModel.section_title min_length=3
    with patch("app.services.report_agent.ReportManager.save_evidence_map") as mock_save:
        with pytest.raises(ValidationError):
            # section_title mit Länge < 3 soll ValidationError provozieren
            agent._build_claims_for_section = MagicMock(return_value=[
                {
                    "claim_id": "claim_01",
                    "claim_text": "Valider Claim-Text ist lang genug.",
                    "confidence_label": "low",
                    "confidence_score": 0.2,
                    "evidence": [],
                    "audit_trail": [],
                }
            ])
            # section_title="ab" hat Länge 2 → verletzt min_length=3
            agent._save_evidence_section("report_abc123", 1, "ab", "Inhalt")

        # save_evidence_map darf NICHT aufgerufen worden sein
        mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: Round-Trip — Section speichern, erneut validieren → keine Exception
# ---------------------------------------------------------------------------

def test_save_evidence_section_round_trip(tmp_path):
    """
    Vollständiger Round-Trip: _save_evidence_section mit valider Section,
    dann erneutes EvidenceMapModel.model_validate → keine Exception,
    schema_version bleibt 3.
    """
    agent = _make_agent(tmp_path)
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent.evidence_map = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "report_id": "report_abc123",
        "simulation_id": "sim_test",
        "global_evidence": [],
        "sections": [],
    }

    # Claims, die das Modell akzeptiert (low, kein supports_claim nötig)
    valid_claims = [
        {
            "claim_id": "claim_01",
            "claim_text": "Die Personas reagieren skeptisch auf die Kampagne.",
            "confidence_label": "low",
            "confidence_score": 0.25,
            "evidence": [_make_valid_evidence_item()],
            "audit_trail": [],
        }
    ]
    agent._build_claims_for_section = MagicMock(return_value=valid_claims)

    with patch("app.services.report_agent.ReportManager.save_evidence_map") as mock_save:
        agent._save_evidence_section(
            "report_abc123", 1, "Erster Eindruck", "Ausführlicher Abschnitt-Text."
        )
        mock_save.assert_called_once()
        persisted_payload = mock_save.call_args[0][1]

    # Erneute Validierung des persistierten Dicts
    re_validated = EvidenceMapModel.model_validate(persisted_payload)
    assert re_validated.schema_version == 3
    assert len(re_validated.sections) == 1
    assert re_validated.sections[0].section_index == 1


def test_save_evidence_section_routes_orphans_to_gaps(tmp_path):
    """P2.1: Low-Orphans werden vor Persistenz aus claims[] entfernt."""
    agent = _make_agent(tmp_path)
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent.evidence_map = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "report_id": "report_abc123",
        "simulation_id": "sim_test",
        "global_evidence": [],
        "sections": [],
    }
    agent._build_claims_for_section = MagicMock(return_value=[
        {
            "claim_id": "claim_01",
            "claim_text": "Die Personas reagieren vermutlich skeptisch auf die Kampagne.",
            "confidence_label": "low",
            "confidence_score": 0.15,
            "evidence": [],
            "audit_trail": [
                {
                    "type": "model_generated_inference",
                    "source": "validator",
                    "snippet": "no_direct_evidence_bound",
                }
            ],
        }
    ])

    with patch("app.services.report_agent.ReportManager.save_evidence_map") as mock_save:
        agent._save_evidence_section(
            "report_abc123", 1, "Erster Eindruck", "Ausführlicher Abschnitt-Text."
        )
        persisted_payload = mock_save.call_args[0][1]

    section = EvidenceMapModel.model_validate(persisted_payload).sections[0]
    assert section.claims == []
    assert len(section.hypotheses) == 1
    assert len(section.data_gaps) == 1
    # Der Evidence-Index ist hier leer — zu dieser Aussage liegt tatsächlich
    # nichts vor. Das ist die eine Konstellation, in der ein Data Gap zu Recht
    # entsteht; ein bloß gescheitertes Binding erzeugt seit der Data-Gap-
    # Semantik keinen mehr (siehe tests/regression/test_data_gap_semantics.py).
    assert section.data_gaps[0].gap_reason == "source_information_absent"


def test_duplicate_bindings_do_not_raise_single_source_confidence(tmp_path):
    """Doppelte Bindings machen aus einem Claim keinen Mehrquellen-Claim.

    #1301: Seit der Deckel-Kalibrierung darf ``compute_confidence`` einem
    Single-Source-Claim mit starkem Match (>= 0.85) mehr als 0.59 zugestehen
    -- hier 0.89/"high" (Verified-Schranke greift weiterhin, da nur eine
    Quelle vorliegt, siehe ``confidence_calculator.py:271-273``). Die
    eigentliche Dedup-Invariante ("zwei Bindings derselben Evidence-ID
    ergeben keine zweite Quelle") zeigt sich deshalb nicht mehr am rohen
    Score, sondern daran, dass ``_finalize_section_claims`` das Label über
    ``auto_downgrade_unsupported_high_claims`` (ADR-0002 Anker 4,
    Cross-Stakeholder-Pflicht für "high") auf "low" zurückstuft, weil hinter
    der duplizierten Quelle keine zweite Stakeholder-Gruppe steht.
    """
    from app.services.confidence_calculator import compute_confidence  # noqa: PLC0415

    agent = _make_agent(tmp_path)
    evidence_id = "ev_0123456789abcdef0123456789abcdef"
    evidence = {
        "type": "graph_fact",
        "source": "panorama_search",
        "snippet": "Dieselbe Quelle wurde doppelt an den Claim gebunden.",
        "match_score": 0.95,
        "supports_claim": True,
    }
    confidence_score, confidence_label = compute_confidence([evidence, evidence])
    claim = {
        "claim_id": "claim_01",
        "claim_text": "Eine doppelt gebundene Quelle bleibt nur eine Quelle.",
        "confidence_label": confidence_label,
        "confidence_score": confidence_score,
        "evidence": [
            {"evidence_id": evidence_id, "supports_claim": True},
            {"evidence_id": evidence_id, "supports_claim": True},
        ],
    }

    finalized, hypotheses, _, _decisions = agent._finalize_section_claims([claim])

    assert len(finalized) == 1
    assert confidence_score <= 0.89
    assert confidence_label != "verified"
    assert finalized[0]["confidence_label"] == "low"
    assert {item["evidence_id"] for item in finalized[0]["evidence"]} == {evidence_id}
    assert hypotheses == []


def test_duplicate_producer_key_preserves_first_record() -> None:
    from app.services.report_agent.evidence import register_evidence_record

    evidence_map = {"evidence_index": {}}
    first = {
        "producer_key": "graph-node:17",
        "type": "graph_fact",
        "source": "graph",
        "snippet": "Erster unveränderlicher Payload.",
        "source_kind": "graph_relation",
    }
    conflicting = {
        **first,
        "snippet": "Abweichender späterer Payload.",
    }

    registered_first = register_evidence_record(
        evidence_map, first, scope_id="sim-17"
    )
    registered_conflict = register_evidence_record(
        evidence_map, conflicting, scope_id="sim-17"
    )

    evidence_id = registered_first["evidence_id"]
    assert registered_conflict == registered_first
    assert evidence_map["evidence_index"][evidence_id]["snippet"] == first["snippet"]
