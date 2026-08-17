"""Issue #1304 (S3) — der Simulationsbeitrag ist eine Zahl, keine Behauptung.

Die Kritik am Referenzlauf lautete: 24 Runden Simulation, keine einzige
validierte Aussage auf einer Agentenaktion. Der Befund war richtig und
unbelegbar zugleich — es gab keine Zahl, gegen die man ihn hätte prüfen können.
"""

from __future__ import annotations

from typing import Any, Dict

from app.contracts.report_v3 import SimulationContribution
from app.services.report_agent.simulation_contribution import (
    compute_simulation_contribution,
)


def _record(evidence_id: str, source_kind: str) -> Dict[str, Any]:
    return {"evidence_id": evidence_id, "source_kind": source_kind}


def _claim(claim_id: str, *supporting: str, related: tuple[str, ...] = ()) -> Dict[str, Any]:
    evidence = [
        {"evidence_id": evidence_id, "supports_claim": True} for evidence_id in supporting
    ]
    evidence += [
        {"evidence_id": evidence_id, "supports_claim": False} for evidence_id in related
    ]
    return {"claim_id": claim_id, "claim_text": "Eine Aussage.", "evidence": evidence}


def _map(claims: list[Dict[str, Any]], index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "schema_version": 3,
        "evidence_index": index,
        "sections": [{"section_index": 1, "claims": claims}],
    }


def test_referenzlauf_ohne_aktionsbeleg_ergibt_null_prozent():
    """Der gemeldete Zustand: alles über Interviews, nichts aus Phase 3."""
    result = compute_simulation_contribution(_map(
        [_claim("claim_01", "ev_a"), _claim("claim_02", "ev_b")],
        {
            "ev_a": _record("ev_a", "agent_quote"),
            "ev_b": _record("ev_b", "seed_corpus"),
        },
    ))

    assert result["validated_claims"] == 2
    assert result["claims_with_simulation_evidence"] == 1  # das Interview
    assert result["claims_with_action_evidence"] == 0
    assert result["action_share"] == 0.0
    assert result["simulation_share"] == 0.5


def test_notwendig_und_nur_beteiligt_werden_getrennt_gezaehlt():
    """Ein zweiter Beleg trägt die Aussage womöglich ebenso — das zählt anders."""
    result = compute_simulation_contribution(_map(
        [
            _claim("claim_01", "ev_action"),  # nur Aktion → notwendig
            _claim("claim_02", "ev_action", "ev_doc"),  # Aktion + Dokument
        ],
        {
            "ev_action": _record("ev_action", "agent_action"),
            "ev_doc": _record("ev_doc", "seed_corpus"),
        },
    ))

    assert result["claims_with_action_evidence"] == 2
    assert result["claims_requiring_action_evidence"] == 1
    assert result["action_share"] == 1.0
    assert result["action_necessary_share"] == 0.5


def test_nur_thematisch_verwandte_evidence_traegt_nichts():
    """``supports_claim=False`` ist kein Beleg — sonst zählt Ähnlichkeit als Beitrag."""
    result = compute_simulation_contribution(_map(
        [_claim("claim_01", "ev_doc", related=("ev_action",))],
        {
            "ev_doc": _record("ev_doc", "seed_corpus"),
            "ev_action": _record("ev_action", "agent_action"),
        },
    ))

    assert result["validated_claims"] == 1
    assert result["claims_with_action_evidence"] == 0


def test_claim_ohne_stuetzenden_beleg_zaehlt_nicht_als_validiert():
    result = compute_simulation_contribution(_map(
        [_claim("claim_01", related=("ev_doc",))],
        {"ev_doc": _record("ev_doc", "seed_corpus")},
    ))

    assert result["validated_claims"] == 0
    assert result["action_share"] is None, (
        "Ohne Messbasis behauptet 0.0 einen fehlenden Beitrag, wo nichts gemessen wurde"
    )


def test_unaufloesbare_referenz_verhindert_ein_notwendig():
    """Ein Beleg, den der Index nicht kennt, darf kein 'ausschließlich' begründen."""
    result = compute_simulation_contribution(_map(
        [_claim("claim_01", "ev_action", "ev_unknown")],
        {"ev_action": _record("ev_action", "agent_action")},
    ))

    assert result["claims_with_action_evidence"] == 1
    assert result["claims_requiring_action_evidence"] == 0


def test_leere_evidenzkarte_ist_kein_fehler():
    for empty in (None, {}, {"sections": []}):
        result = compute_simulation_contribution(empty)
        assert result["validated_claims"] == 0
        assert result["simulation_share"] is None


def test_ergebnis_passt_in_den_vertrag():
    result = compute_simulation_contribution(_map(
        [_claim("claim_01", "ev_action")],
        {"ev_action": _record("ev_action", "agent_action")},
    ))
    model = SimulationContribution.model_validate(result)
    assert model.action_necessary_share == 1.0


def test_build_report_v3_haengt_den_beitrag_ans_artefakt():
    from app.models.report import Report, ReportStatus  # noqa: PLC0415
    from app.services.report_agent.manager import ReportManager  # noqa: PLC0415

    evidence_id = "ev_" + "a" * 32
    evidence_map = _map(
        [_claim("claim_01", evidence_id)],
        {
            evidence_id: {
                "evidence_id": evidence_id,
                "producer_key": "sim:action:1",
                "source_kind": "agent_action",
                "type": "agent_action",
                "source": "sim",
                "snippet": "Persona hat einen Beitrag verfasst.",
            }
        },
    )
    evidence_map["report_id"] = "report_1304"
    evidence_map["simulation_id"] = "sim_1304"

    report = Report(
        report_id="report_1304",
        simulation_id="sim_1304",
        graph_id="graph_1304",
        simulation_requirement="Test",
        status=ReportStatus.COMPLETED,
    )

    migrated = ReportManager.build_report_v3(report, evidence_map)

    assert migrated.simulation_contribution is not None
    assert migrated.simulation_contribution.claims_with_action_evidence == 1


def test_renderer_weist_den_beitrag_aus():
    from app.services.report_agent.markdown_renderer import (  # noqa: PLC0415
        render_simulation_contribution,
    )

    class _Report:
        simulation_contribution = SimulationContribution.model_validate(
            compute_simulation_contribution(_map(
                [_claim("claim_01", "ev_action"), _claim("claim_02", "ev_doc")],
                {
                    "ev_action": _record("ev_action", "agent_action"),
                    "ev_doc": _record("ev_doc", "seed_corpus"),
                },
            ))
        )

    rendered = render_simulation_contribution(_Report())

    assert "1 von 2" in rendered
    assert "50.0 %" in rendered


def test_renderer_bleibt_ehrlich_ohne_messung():
    from app.services.report_agent.markdown_renderer import (  # noqa: PLC0415
        render_simulation_contribution,
    )

    class _Report:
        simulation_contribution = None

    assert "unbekannt" in render_simulation_contribution(_Report())
