"""Issue #1324 — ungebundene Evidence-Refs landen im Artefakt, nicht nur im Log.

``QuoteValidationResult.unbound_evidence_refs`` wurde befüllt und an zwei
Stellen in ``section_pipeline`` geloggt — geschrieben wurde es nirgends. Ein
Leser des persistierten Reports sah damit nicht, welcher zitierte Beleg nie
gebunden wurde, obwohl genau das den Statuswechsel auf ``incomplete``
erklärt.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.contracts.report_contract import ReportSectionModel
from app.services.report_agent.evidence import QuoteValidationResult
from app.services.report_agent.section_pipeline import _validate_quotes_with_repair


class _Section:
    def __init__(self, title: str) -> None:
        self.title = title
        self.metadata: Dict[str, Any] = {}
        self.content = ""


class _Agent:
    def __init__(self) -> None:
        self.evidence_map: Dict[str, Any] = {}
        self.persona_ids: List[str] = ["persona_1"]


class _Ctx:
    """Minimaler SectionContext-Ersatz: nur was ``_validate_quotes_with_repair`` liest."""

    report_mode = "balanced"
    outline = None
    previous_sections: List[Any] = []
    report_id = "report_1324"

    def __init__(self, results: List[QuoteValidationResult]) -> None:
        self._results = list(results)

    def validate_quotes(self, *_args: Any, **_kwargs: Any) -> QuoteValidationResult:
        return self._results.pop(0)

    def generate_section(self, *_args: Any, **_kwargs: Any) -> str:
        return "Reparierter Abschnitt."


UNBOUND = ["ev_never_bound_01", "ev_never_bound_02"]


def _failing_result() -> QuoteValidationResult:
    return QuoteValidationResult(
        valid=False,
        quotes=[],
        invalid_quotes=[{"seed_anchor": "ev_never_bound_01"}],
        unbound_evidence_refs=list(UNBOUND),
    )


def test_failed_repair_returns_the_unbound_refs():
    """Nach gescheitertem Repair müssen die Refs den Aufrufer erreichen."""
    agent = _Agent()
    section = _Section("Beobachtete Reaktionsmuster")
    ctx = _Ctx([_failing_result(), _failing_result()])

    content, failed, unbound = _validate_quotes_with_repair(
        agent, section, ctx, "Inhalt mit Zitat.", section_index=1
    )

    assert failed is True
    assert unbound == UNBOUND
    assert content == "Reparierter Abschnitt."


def test_valid_section_reports_no_unbound_refs():
    agent = _Agent()
    section = _Section("Beobachtete Reaktionsmuster")
    ctx = _Ctx([QuoteValidationResult(valid=True)])

    content, failed, unbound = _validate_quotes_with_repair(
        agent, section, ctx, "Inhalt.", section_index=1
    )

    assert (failed, unbound, content) == (False, [], "Inhalt.")


def test_section_contract_persists_unbound_refs():
    """Das Vertragsfeld existiert und überlebt den Round-Trip."""
    section = ReportSectionModel.model_validate({
        "section_index": 1,
        "section_title": "Beobachtete Reaktionsmuster",
        "section_summary": "Zusammenfassung.",
        "unbound_evidence_refs": UNBOUND,
    })

    assert section.unbound_evidence_refs == UNBOUND
    assert ReportSectionModel.model_validate(
        section.model_dump()
    ).unbound_evidence_refs == UNBOUND


def test_unbound_refs_default_to_empty_for_bestandsartefakte():
    """Ein vor #1324 geschriebener Abschnitt kennt das Feld nicht — kein Fehler."""
    section = ReportSectionModel.model_validate({
        "section_index": 1,
        "section_title": "Kurzfazit",
        "section_summary": "Zusammenfassung.",
    })

    assert section.unbound_evidence_refs == []
