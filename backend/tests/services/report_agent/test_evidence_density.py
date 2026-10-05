"""Belegdichte je Bericht (Issue #1779, Schritt 2.1).

Beim Abschluss des Berichts zählt ``evidence_density.json``, wie dicht die
Claims belegt sind: ohne, mit einem, mit mehreren und mit unabhängigen
stützenden Belegen.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest
from pydantic import ValidationError

from app.contracts.evidence_density_contract import EvidenceDensity
from app.services.report_agent.evidence_density import (
    EVIDENCE_DENSITY_FILENAME,
    compute_evidence_density,
    load_evidence_density,
    save_evidence_density,
)
from app.services.run_budget import BudgetExceededError


def _link(evidence_id: str, *, supports: bool = True, **extra: Any) -> Dict[str, Any]:
    return {"evidence_id": evidence_id, "supports_claim": supports, "entailment": "entails", **extra}


def _claim(score: float, *links: Dict[str, Any]) -> Dict[str, Any]:
    return {"confidence_score": score, "evidence": list(links)}


def _evidence_map() -> Dict[str, Any]:
    return {
        "sections": [
            {
                "claims": [
                    # 1: ohne stützenden Beleg (nur ein nicht stützender Eintrag)
                    _claim(0.4, _link("e-doc", supports=False)),
                    # 2: genau ein Interview, am Ein-Quellen-Deckel
                    _claim(0.59, _link("e-int-a1")),
                    # 3: zwei Interviews derselben Stimme: multi, nicht unabhängig
                    _claim(0.59, _link("e-int-a1"), _link("e-int-a2")),
                    # 4: zwei Stimmen: multi und unabhängig
                    _claim(0.8, _link("e-int-a1"), _link("e-int-b1")),
                    # 5: stützende Simulationshandlung
                    _claim(0.7, _link("e-act-c", supports=True), _link("e-doc", supports=False)),
                    # Nicht-Dict-Einträge werden übersprungen.
                    "kein-claim",
                ]
            },
            "kein-abschnitt",
            {"claims": None},
        ],
        "evidence_index": {
            "e-doc": {"type": "document", "source": "seed.pdf"},
            "e-int-a1": {"type": "agent_interview", "source": "interview", "voice_key": "agent:1"},
            "e-int-a2": {"type": "agent_interview", "source": "interview", "voice_key": "agent:1"},
            "e-int-b1": {"type": "agent_interview", "source": "interview", "voice_key": "agent:2"},
            "e-act-c": {"type": "agent_action", "source": "simulation_actions", "voice_key": "agent:3"},
        },
    }


def test_zaehlt_die_belegdichte_der_claims():
    density = compute_evidence_density(_evidence_map())

    assert density.claims_total == 5
    assert density.claims_without_support == 1
    assert density.claims_single_support == 2
    assert density.claims_multi_support == 2
    assert density.claims_multi_independent == 1
    assert density.claims_at_single_source_cap == 2
    assert density.claims_with_action_support == 1
    # Der nicht stützende Eintrag zählt nirgends mit.
    assert density.supporting_links_by_type == {"agent_action": 1, "agent_interview": 5}
    assert density.single_support_ratio == pytest.approx(2 / 5)
    assert density.action_support_ratio == pytest.approx(1 / 5)
    assert density.single_source_cap_ratio == pytest.approx(2 / 5)
    assert density.multi_independent_ratio == pytest.approx(1 / 5)


def test_felder_des_claim_eintrags_ueberschreiben_den_index():
    # Der Index kennt keine Stimme, der Claim-Eintrag trägt sie: gleiche Stimme
    # heißt keine Unabhängigkeit.
    evidence_map = {
        "sections": [
            {
                "claims": [
                    _claim(
                        0.6,
                        _link("e1", voice_key="agent:7"),
                        _link("e2", voice_key="agent:7"),
                    )
                ]
            }
        ],
        "evidence_index": {
            "e1": {"type": "agent_interview", "voice_key": "agent:1"},
            "e2": {"type": "agent_interview", "voice_key": "agent:2"},
        },
    }

    density = compute_evidence_density(evidence_map)

    assert density.claims_multi_support == 1
    assert density.claims_multi_independent == 0


def test_belegart_aus_dem_claim_eintrag_hat_vorrang_unbekannte_art_ist_unknown():
    evidence_map = {
        "sections": [
            {"claims": [_claim(0.7, _link("e1", type="agent_action"), _link("e-fehlt"))]}
        ],
        "evidence_index": {"e1": {"type": "document"}},
    }

    density = compute_evidence_density(evidence_map)

    assert density.supporting_links_by_type == {"agent_action": 1, "unknown": 1}
    assert density.claims_with_action_support == 1


def test_leere_evidence_map_hat_nullzaehler_und_keine_quoten():
    for empty in ({}, {"sections": [], "evidence_index": {}}, {"sections": None}):
        density = compute_evidence_density(empty)

        assert density.claims_total == 0
        assert density.claims_without_support == 0
        assert density.claims_single_support == 0
        assert density.claims_multi_support == 0
        assert density.claims_multi_independent == 0
        assert density.claims_at_single_source_cap == 0
        assert density.claims_with_action_support == 0
        assert density.supporting_links_by_type == {}
        assert density.single_support_ratio is None
        assert density.action_support_ratio is None
        assert density.single_source_cap_ratio is None
        assert density.multi_independent_ratio is None


def test_vertrag_lehnt_inkonsistente_summen_ab():
    with pytest.raises(ValidationError, match="must equal claims_total"):
        EvidenceDensity(claims_total=3, claims_single_support=1)


def test_vertrag_lehnt_unbekannte_felder_ab():
    with pytest.raises(ValidationError):
        EvidenceDensity.model_validate({"claims_total": 0, "unbekannt": 1})


def test_speichern_und_laden_rundlauf(tmp_path):
    density = compute_evidence_density(_evidence_map())

    path = save_evidence_density(str(tmp_path), density)

    assert path == str(tmp_path / EVIDENCE_DENSITY_FILENAME)
    stored = json.loads((tmp_path / EVIDENCE_DENSITY_FILENAME).read_text(encoding="utf-8"))
    assert stored["claims_total"] == 5
    assert load_evidence_density(str(tmp_path)) == density


def test_laden_ohne_oder_mit_defekter_datei_liefert_none(tmp_path):
    assert load_evidence_density(str(tmp_path)) is None
    (tmp_path / EVIDENCE_DENSITY_FILENAME).write_text("{kaputt", encoding="utf-8")
    assert load_evidence_density(str(tmp_path)) is None


# ---------------------------------------------------------------------------
# Persistenz beim Abschluss. Der ganze Workflow ist zu schwer aufzusetzen;
# getestet wird die Hilfsfunktion, die ``generate_report`` und
# ``_build_partial_report`` nach ``save_report`` aufrufen, und danach die
# Verdrahtung des Teil-Reports.
# ---------------------------------------------------------------------------


class _Agent:
    def __init__(self, evidence_map: Any) -> None:
        self.evidence_map = evidence_map


@pytest.fixture
def reports_dir(monkeypatch, tmp_path):
    from app.services.report_agent.manager import ReportManager

    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    return tmp_path


def test_abschluss_schreibt_die_datei_auch_fuer_incomplete(reports_dir):
    from app.models.report import Report, ReportStatus
    from app.services.report_agent import workflow

    report = Report(
        report_id="report-1",
        simulation_id="sim-1",
        graph_id="g-1",
        simulation_requirement="x",
        status=ReportStatus.INCOMPLETE,
    )

    workflow._persist_evidence_density(_Agent(_evidence_map()), report.report_id)

    stored = load_evidence_density(str(reports_dir / "report-1"))
    assert stored is not None
    assert stored.claims_total == 5
    assert stored.claims_multi_independent == 1


def test_abschluss_ohne_dict_evidence_map_schreibt_nichts(reports_dir):
    from app.services.report_agent import workflow

    workflow._persist_evidence_density(_Agent(None), "report-2")

    assert not (reports_dir / "report-2" / EVIDENCE_DENSITY_FILENAME).exists()


def test_schreibfehler_bricht_den_bericht_nicht_ab_und_wird_protokolliert(
    reports_dir, monkeypatch
):
    from unittest.mock import MagicMock

    from app.services.report_agent import workflow

    def _boom(*_a: Any, **_k: Any) -> str:
        raise PermissionError("evidence_density.json")

    log = MagicMock()
    monkeypatch.setattr(workflow, "save_evidence_density", _boom)
    monkeypatch.setattr(workflow, "logger", log)

    workflow._persist_evidence_density(_Agent(_evidence_map()), "report-3")

    log.warning.assert_called_once()
    assert "evidence_density.json" in log.warning.call_args.args[0]
    log.info.assert_not_called()


def test_budgetabbruch_wird_nicht_geschluckt(reports_dir, monkeypatch):
    from app.services.report_agent import workflow

    def _budget(*_a: Any, **_k: Any) -> str:
        raise BudgetExceededError("tokens", 10, 5)

    monkeypatch.setattr(workflow, "save_evidence_density", _budget)

    with pytest.raises(BudgetExceededError):
        workflow._persist_evidence_density(_Agent(_evidence_map()), "report-4")


def test_teil_report_schreibt_die_belegdichte(reports_dir):
    from unittest.mock import MagicMock, patch

    from app.models.report import Report, ReportOutline, ReportSection, ReportStatus
    from app.services.report_agent import workflow
    from app.services.report_agent.manager import ReportManager

    report = Report(
        report_id="report-5",
        simulation_id="sim-1",
        graph_id="g-1",
        simulation_requirement="x",
        status=ReportStatus.GENERATING,
    )
    outline = ReportOutline(
        title="T",
        summary="S",
        sections=[ReportSection(title=f"S{i}", content="", description="") for i in range(3)],
    )
    agent = MagicMock()
    agent.evidence_map = _evidence_map()
    ReportManager._ensure_report_folder("report-5")

    with (
        patch.object(ReportManager, "assemble_full_report", return_value="md"),
        patch.object(ReportManager, "save_report"),
        patch.object(ReportManager, "update_progress"),
        patch("app.config.Config.REPORT_REQUIREMENT_CHECKER_ENABLED", False),
    ):
        result = workflow._build_partial_report(
            report,
            report_id="report-5",
            completed_section_titles=["S0"],
            outline=outline,
            agent=agent,
            progress_callback=None,
        )

    # Zwei von drei Sections fehlen: ehrliches INCOMPLETE, Zählung trotzdem da.
    assert result.status == ReportStatus.INCOMPLETE
    stored = load_evidence_density(str(reports_dir / "report-5"))
    assert stored is not None
    assert stored.claims_total == 5
