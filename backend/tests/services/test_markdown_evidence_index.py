"""Issue #1160 H — der Markdown-Export löst seine Belegkennungen auf.

Der MD-Export zeigte in Claim- und Multiplier-Tabellen nur `evidence_refs`-IDs.
JSON und ZIP tragen die Provenance vollständig, Markdown nicht — wer den Report
so las, sah Verweise ohne Belege. Das trifft ausgerechnet das Format, das
weitergereicht und ausgedruckt wird.

Aufgelöst wird in einem eigenen Abschnitt am Ende, nicht durch breitere
Tabellen weiter oben: dieselbe Evidence stützt oft mehrere Claims, und die
Tabellen bleiben so lesbar.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.contracts.report_contract import EvidenceRecordModel
from app.contracts.report_v3 import Claim, ReportV3
from app.services.report_agent.markdown_renderer import (
    render_evidence_index,
    render_report_v3,
)

EVIDENCE_ID = "ev_00000000000000000000000000000001"
SECOND_EVIDENCE_ID = "ev_00000000000000000000000000000002"


def _record(
    evidence_id: str = EVIDENCE_ID,
    *,
    source_kind: str = "seed_corpus",
    quote: str | None = "Das Vorhaben startet im dritten Quartal.",
    snippet: str = "Kontext rund um den Quartalsstart aus dem Briefing.",
    stakeholder_group: str | None = None,
) -> EvidenceRecordModel:
    return EvidenceRecordModel(
        evidence_id=evidence_id,
        producer_key="briefing.md#absatz-4",
        type="graph_fact",  # type: ignore[arg-type]
        source="briefing.md",
        snippet=snippet,
        quote=quote,
        source_kind=source_kind,  # type: ignore[arg-type]
        persona_stakeholder_group=stakeholder_group,
    )


def _report(**index: EvidenceRecordModel) -> ReportV3:
    return ReportV3(
        schema_version=4,
        report_id="rep-1160h",
        generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        evidence_index=dict(index),
        claims=[
            Claim(
                id="claim_01",
                statement="Die Zielgruppe erwartet einen Start im dritten Quartal.",
                evidence_refs=list(index),
                confidence="medium",
                aggregation_basis="persona",
            )
        ]
        if index
        else [],
    )


def test_der_nachweis_loest_die_kennung_zur_quelle_auf() -> None:
    table = render_evidence_index(_report(**{EVIDENCE_ID: _record()}))

    assert EVIDENCE_ID in table
    assert "briefing.md#absatz-4" in table, "ohne Producer bleibt der Verweis unauflösbar"
    assert "briefing.md" in table


def test_die_quellengattung_steht_im_klartext() -> None:
    """`seed_corpus` sagt einem Leser ohne Codekenntnis nichts."""
    table = render_evidence_index(_report(**{EVIDENCE_ID: _record()}))

    assert "Seed-Dokument" in table
    assert "seed_corpus" not in table


def test_ein_unbekannter_gattungswert_wird_unveraendert_gezeigt() -> None:
    """Kommt eine Gattung hinzu, ohne dass die Beschriftung nachgezogen wird,
    steht der Rohwert da — nicht eine leere Zelle, die wie „keine Quelle“
    aussieht."""
    table = render_evidence_index(
        _report(
            **{
                EVIDENCE_ID: _record(
                    source_kind="agent_quote", stakeholder_group="Belegschaft"
                )
            }
        )
    )
    assert "Agentenzitat" in table


def test_das_originalzitat_geht_dem_kontext_vor() -> None:
    """Der Auszug soll den Beleg zeigen, nicht den Absatz, in dem er stand."""
    table = render_evidence_index(_report(**{EVIDENCE_ID: _record()}))

    assert "Das Vorhaben startet im dritten Quartal." in table
    assert "Kontext rund um den Quartalsstart" not in table


def test_ohne_zitat_tritt_der_snippet_an_seine_stelle() -> None:
    table = render_evidence_index(_report(**{EVIDENCE_ID: _record(quote=None)}))

    assert "Kontext rund um den Quartalsstart" in table


def test_lange_ausz_uege_werden_gekuerzt() -> None:
    """Ein Snippet darf 2000 Zeichen haben — in einer Tabellenzelle wäre das
    unlesbar. Der Nachweis soll zuordnen, nicht die Quelle ersetzen."""
    table = render_evidence_index(
        _report(**{EVIDENCE_ID: _record(quote=None, snippet="A" * 900)})
    )

    longest_cell = max((cell.strip() for cell in table.split("|")), key=len)
    assert len(longest_cell) < 300
    assert "…" in table


def test_der_nachweis_ist_stabil_sortiert() -> None:
    """Zwei Renderläufe desselben Reports ergeben dieselbe Datei — sonst
    rauschen Diffs zwischen zwei Exporten desselben Berichts."""
    index = {SECOND_EVIDENCE_ID: _record(SECOND_EVIDENCE_ID), EVIDENCE_ID: _record()}
    first = render_evidence_index(_report(**index))
    second = render_evidence_index(_report(**dict(reversed(list(index.items())))))

    assert first == second
    assert first.index(EVIDENCE_ID) < first.index(SECOND_EVIDENCE_ID)


def test_ein_report_ohne_evidence_sagt_das_ausdruecklich() -> None:
    table = render_evidence_index(_report())

    assert "Keine Evidence-Records" in table


def test_der_gesamtreport_enthaelt_den_abschnitt() -> None:
    markdown = render_report_v3(_report(**{EVIDENCE_ID: _record()}))

    assert "## Evidenz-Nachweise" in markdown
    # Der Abschnitt steht hinter den Tabellen, deren Kennungen er auflöst.
    assert markdown.index("## Claims") < markdown.index("## Evidenz-Nachweise")
    assert "briefing.md#absatz-4" in markdown
