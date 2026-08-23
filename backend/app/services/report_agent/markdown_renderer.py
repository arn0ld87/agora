from __future__ import annotations

from typing import Iterable

from ...contracts.report_v3 import (
    ChangeRecommendation,
    Claim,
    DataGap,
    FrictionPoint,
    Hypothesis,
    Persona,
    ReportV3,
    Segment,
    Threshold,
    TrustSignal,
)


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("\n", " ").replace("|", "\\|").strip()


def _list_cell(values: Iterable[object]) -> str:
    return ", ".join(_cell(value) for value in values if _cell(value)) or "-"


def _table(headers: list[str], rows: list[list[object]], empty_text: str) -> str:
    if not rows:
        return f"_{empty_text}_"
    header = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join(_cell(value) for value in row) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def render_persona_table(personas: list[Persona]) -> str:
    return _table(
        ["ID", "Voice", "Alter", "Beruf", "Region", "Needs", "Values"],
        [
            [
                persona.id,
                persona.voice_register,
                persona.alter_range,
                persona.beruf,
                persona.region,
                _list_cell(persona.needs),
                _list_cell(persona.values),
            ]
            for persona in personas
        ],
        "Keine Personas im ReportV3-Artefakt.",
    )


def render_segment_table(segments: list[Segment]) -> str:
    return _table(
        ["ID", "Name", "Beschreibung", "Personas", "Kontaktwahrscheinlichkeit"],
        [
            [
                segment.id,
                segment.name,
                segment.beschreibung,
                _list_cell(segment.persona_ids),
                (
                    f"{segment.kontaktwahrscheinlichkeit_prozent:.1f}%"
                    if segment.kontaktwahrscheinlichkeit_prozent is not None
                    else "-"
                ),
            ]
            for segment in segments
        ],
        "Keine Segmente im ReportV3-Artefakt.",
    )


# Issue #1160 A: Der Geltungsbereich steht als Klartext neben dem Label.
# "high" allein sagt nicht, ob dahinter Quellen oder uebereinstimmende
# simulierte Agenten stehen — genau diese Verwechslung soll die Spalte
# verhindern.
_CONFIDENCE_SCOPE_LABELS = {
    "simulation_consensus": "Simulationskonsens",
    "evidence": "Quellenbindung",
    "empirical": "Empirische Daten",
}


def _confidence_cell(claim: Claim) -> str:
    """Label, bei nachtraeglicher Abstufung mit Herkunft des Wortlauts (#1012).

    Der ``statement``-Text bleibt unveraendert — er stammt vom Modell und
    wird nicht nachtraeglich umgeschrieben. Sichtbar wird stattdessen, dass
    seine Formulierung aus einer hoeheren Stufe kommt und deshalb sicherer
    klingen kann, als das Label deckt.
    """
    if claim.text_confidence and claim.text_confidence != claim.confidence:
        return f"{claim.confidence} (Wortlaut: {claim.text_confidence})"
    return str(claim.confidence)


def render_claim_table(claims: list[Claim]) -> str:
    return _table(
        ["ID", "Confidence", "Geltungsbereich", "Basis", "Statement", "Evidence"],
        [
            [
                claim.id,
                _confidence_cell(claim),
                # Bestands-Artefakte ohne das Feld: "-" statt einer Behauptung
                # ueber einen Geltungsbereich, der nie erfasst wurde.
                _CONFIDENCE_SCOPE_LABELS.get(claim.confidence_scope or "", "-"),
                claim.aggregation_basis,
                claim.statement,
                _list_cell(claim.evidence_refs),
            ]
            for claim in claims
        ],
        "Keine Claims im ReportV3-Artefakt.",
    )


def render_top10_list(
    items: list[FrictionPoint | TrustSignal | ChangeRecommendation],
) -> str:
    if not items:
        return "_Keine Top-10-Eintraege im ReportV3-Artefakt._"
    lines: list[str] = []
    for index, item in enumerate(items[:10], 1):
        title = getattr(item, "titel", None) or getattr(item, "beschreibung", None) or item.id
        rank = getattr(item, "severity", None) or getattr(item, "priority", None) or "-"
        lines.append(f"{index}. **{_cell(title)}** ({_cell(rank)})")
    return "\n".join(lines)


def render_data_gaps(gaps: list[DataGap]) -> str:
    return _table(
        ["ID", "Severity", "Beschreibung", "Hypothese", "Suggested Fixes"],
        [
            [
                gap.id,
                gap.severity,
                gap.beschreibung,
                # Issue #1319: leer, wenn die Luecke keine Hypothese als
                # Gegenstueck hat — der Verweis zeigt nur auf IDs, die in der
                # Hypothesentabelle desselben Artefakts stehen.
                gap.related_hypothesis_id or "",
                _list_cell(gap.suggested_fixes),
            ]
            for gap in gaps
        ],
        "Keine Data Gaps im ReportV3-Artefakt.",
    )


def render_hypotheses_table(hypotheses: list[Hypothesis]) -> str:
    return _table(
        ["ID", "Hypothese", "Rationale", "Suggested Evidence", "Score"],
        [
            [
                hypothesis.id,
                hypothesis.hypothesis_text,
                hypothesis.rationale,
                _list_cell(hypothesis.suggested_evidence),
                f"{hypothesis.confidence_score:.2f}",
            ]
            for hypothesis in hypotheses
        ],
        "Keine Hypothesen im ReportV3-Artefakt.",
    )


# Issue #1160 E: Herkunft im Klartext. Ein Leser muss auf einen Blick sehen,
# ob eine Zahl im Auftragsdokument stand oder ob ein Sprachmodell sie plausibel
# fand — als Enum-Wert leistet das Feld genau das nicht.
_THRESHOLD_ORIGIN_LABELS = {
    "document_requirement": "Vorgabe aus Dokument",
    "empirical_data": "aus Daten abgeleitet",
    "external_standard": "externer Standard",
    "operator_policy": "Betreiber-Festlegung",
    "model_proposal": "Modellvorschlag",
    "simulation_proposal": "Simulationsvorschlag",
}

_THRESHOLD_PURPOSE_LABELS = {
    "alert": "Alarmschwelle",
    "target": "Zielwert",
    "limit": "Obergrenze",
    "baseline": "Ausgangswert",
}

_THRESHOLD_EVIDENCE_STATUS_LABELS = {
    "verified": "belegt",
    "derived": "abgeleitet",
    "heuristic": "unbelegt",
}


def render_threshold_table(thresholds: list[Threshold]) -> str:
    """Operative Zahlen mit ihrer Herkunft — Issue #1160 E.

    Zahlen wie „>90 % Traffic-Baseline" sehen im Fliesstext alle gleich aus,
    unabhaengig davon, ob sie aus dem Auftragsdokument, aus gemessenen Daten
    oder aus einem Modellvorschlag stammen. Diese Tabelle macht den
    Unterschied lesbar; der Fliesstext bleibt unangetastet.
    """
    return _table(
        ["Bezeichnung", "Wert", "Rolle", "Herkunft", "Beleglage", "Evidence"],
        [
            [
                threshold.label,
                # Ganze Zahlen ohne Nachkommastelle: "80 percent" statt
                # "80.0 percent" — der Wert wird gelesen, nicht gerechnet.
                # Datumsangaben (#1343) erscheinen als ISO-Wert ohne Einheit.
                threshold.display_value,
                _THRESHOLD_PURPOSE_LABELS.get(threshold.purpose, threshold.purpose),
                _THRESHOLD_ORIGIN_LABELS.get(threshold.origin, threshold.origin),
                _THRESHOLD_EVIDENCE_STATUS_LABELS.get(
                    threshold.evidence_status, threshold.evidence_status
                ),
                _list_cell(threshold.evidence_refs),
            ]
            for threshold in thresholds
        ],
        "Keine operativen Zahlen im ReportV3-Artefakt.",
    )


def _render_generic_table(title: str, rows: list[list[object]], headers: list[str]) -> str:
    return f"## {title}\n\n" + _table(headers, rows, f"Keine Eintraege fuer {title}.")


_MODE_BANNER: dict[str, str] = {
    "strict": "> **Report-Modus:** strict — Nur belegte Claims, harter Anchor-Validator.",
    "balanced": "> **Report-Modus:** balanced — Belegte Claims plus markierte Hypothesen.",
    "explorative": "> **Report-Modus:** explorative — Alle Claims durch, EXPLORATIVE-Modus.",
}


def render_evidence_status(report: ReportV3) -> str:
    """Kompakte Statusübersicht: was ist belegt, was Hypothese, was fehlt.

    Macht den Balanced-Modus sichtbar (validierte Claims + markierte
    Hypothesen) und stellt klar, dass Simulationsaussagen keine empirische
    Nutzerforschung sind — der Leser sieht den Evidenzstand, bevor er den
    narrativen Text liest.
    """
    table = _table(
        ["Status", "Anzahl", "Bedeutung"],
        [
            [
                "Validierte Claims",
                len(report.claims),
                "Durch kanonische Evidence-Referenzen belegt",
            ],
            [
                "Hypothesen",
                len(report.hypotheses),
                "Plausibel, aber ohne bindende Evidence — nicht als Fakt lesen",
            ],
            [
                "Data Gaps",
                len(report.data_gaps),
                "Fehlende Informationen, die eine belastbare Aussage verhindern",
            ],
            # Issue #1012: Diese Zahl steht bewusst hier — vor dem narrativen
            # Text. Ein nachtraeglich abgestufter Claim behaelt seine
            # urspruengliche, oft deklarative Formulierung; wer den Fliesstext
            # liest, soll das vorher wissen.
            [
                "Nachtraeglich abgestuft",
                sum(
                    1
                    for claim in report.claims
                    if claim.text_confidence and claim.text_confidence != claim.confidence
                ),
                "Wortlaut stammt aus einer hoeheren Vertrauensstufe — nicht als "
                "Formulierung der aktuellen Stufe lesen",
            ],
        ],
        "Kein Evidenzstatus verfügbar.",
    )
    return (
        "## Evidenzstatus\n\n"
        + table
        + "\n\n> Persona-Zitate und Interviewaussagen in diesem Report stammen "
        "aus **simulierten Agenten**. Sie sind Simulationsevidenz und keine "
        "empirische Nutzerforschung."
    )


# Issue #1160 H: Klartext statt Enum-Wert. Wer den Report als Markdown liest,
# soll nicht erst nachschlagen muessen, was ``seed_corpus`` bedeutet.
_SOURCE_KIND_LABELS = {
    "seed_corpus": "Seed-Dokument",
    "agent_quote": "Agentenzitat",
    "agent_action": "Agentenaktion",
    "graph_relation": "Graph-Relation",
    "web_source": "Web-Quelle",
    "inferred": "abgeleitet",
}

# Ein Snippet darf bis zu 2000 Zeichen lang sein (EvidenceRecordModel). In einer
# Markdown-Tabellenzelle waere das unlesbar; der Nachweis soll die Zuordnung
# ermoeglichen, nicht die Quelle ersetzen.
_EVIDENCE_SNIPPET_MAX = 240


def _shorten(text: str, limit: int = _EVIDENCE_SNIPPET_MAX) -> str:
    cleaned = _cell(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def render_evidence_index(report: ReportV3) -> str:
    """Loest die ``evidence_refs``-IDs der Tabellen zu ihren Quellen auf.

    Issue #1160 H: Der Markdown-Export zeigte nur Belegkennungen. JSON und ZIP
    tragen die Provenance vollstaendig, Markdown nicht — wer den Report so las,
    sah Verweise ohne Belege. Das ist besonders unguenstig, weil Markdown das
    Format ist, das weitergereicht und ausgedruckt wird.

    Bewusst ein eigener Abschnitt am Ende statt breiterer Tabellen weiter oben:
    dieselbe Evidence stuetzt oft mehrere Claims, und die Tabellen bleiben so
    lesbar. Die Aufloesung funktioniert wie ein Quellenverzeichnis.
    """
    return _table(
        ["Evidence-ID", "Gattung", "Producer", "Quelle", "Auszug"],
        [
            [
                evidence_id,
                _SOURCE_KIND_LABELS.get(
                    record.source_kind.value, record.source_kind.value
                ),
                record.producer_key,
                record.source,
                # Das Originalzitat ist der bessere Beleg, wo es existiert —
                # der Snippet ist nur der Kontext, aus dem es stammt.
                _shorten(record.quote or record.snippet),
            ]
            for evidence_id, record in sorted(report.evidence_index.items())
        ],
        "Keine Evidence-Records im ReportV3-Artefakt.",
    )


def render_simulation_snapshot(report: ReportV3) -> str:
    """Weist aus, auf welchem Simulationsstand der Report beruht (Issue #1192).

    Ein Report darf auf einem Zwischenstand beruhen — er darf nur nicht
    verschweigen, dass er es tut. Fehlt der Snapshot ganz, stammt der Report
    aus der Zeit vor dieser Ausweisung; dann ist "unbekannt" die einzige
    ehrliche Aussage.
    """
    snapshot = getattr(report, "simulation_snapshot", None)
    if snapshot is None:
        return "Simulationsstand: `unbekannt` (vor Einführung der Standausweisung erzeugt)"

    von_gesamt = (
        f" von {snapshot.total_rounds}" if snapshot.total_rounds else ""
    )
    if snapshot.simulation_running:
        return (
            f"Simulationsstand: **Zwischenstand** — {snapshot.rounds_completed}"
            f"{von_gesamt} Runden abgeschlossen; die Simulation lief zum "
            f"Startzeitpunkt dieses Reports noch weiter. Spätere Runden sind "
            f"nicht eingeflossen."
        )
    return (
        f"Simulationsstand: {snapshot.rounds_completed}{von_gesamt} Runden "
        f"abgeschlossen; die Simulation lief zum Startzeitpunkt nicht mehr."
    )


def render_simulation_contribution(report: ReportV3) -> str:
    """Weist aus, wie viel die Simulation zu den validierten Aussagen beitraegt.

    Issue #1304 (S3). Der Wert gehoert neben den Simulationsstand: 24 Runden
    auszuweisen und zu verschweigen, dass keine einzige Aussage darauf beruht,
    waere die halbe Wahrheit.
    """
    contribution = getattr(report, "simulation_contribution", None)
    if contribution is None:
        return (
            "Simulationsbeitrag: `unbekannt` (vor Einfuehrung der Messung erzeugt)"
        )
    if not contribution.validated_claims:
        return (
            "Simulationsbeitrag: keine validierte Aussage im Artefakt — "
            "es gibt nichts zu messen."
        )

    def _pct(share: float | None) -> str:
        return "—" if share is None else f"{share * 100:.1f} %"

    return "\n\n".join([
        (
            f"Simulationsbeitrag: {contribution.claims_with_action_evidence} von "
            f"{contribution.validated_claims} validierten Aussagen stuetzen sich "
            f"auf eine beobachtete Agentenaktion "
            f"({_pct(contribution.action_share)}); bei "
            f"{contribution.claims_requiring_action_evidence} ist sie der einzige "
            f"stuetzende Beleg ({_pct(contribution.action_necessary_share)})."
        ),
        _table(
            ["Kennzahl", "Aussagen", "Anteil"],
            [
                [
                    "validiert (mit stuetzendem Beleg)",
                    str(contribution.validated_claims),
                    "100.0 %",
                ],
                [
                    "davon mit Simulationsbeleg (Aktion oder Interview)",
                    str(contribution.claims_with_simulation_evidence),
                    _pct(contribution.simulation_share),
                ],
                [
                    "davon mit Aktionsbeleg (Phase 3)",
                    str(contribution.claims_with_action_evidence),
                    _pct(contribution.action_share),
                ],
                [
                    "davon ausschliesslich auf Aktionsbelegen",
                    str(contribution.claims_requiring_action_evidence),
                    _pct(contribution.action_necessary_share),
                ],
            ],
            "Kein Simulationsbeitrag messbar.",
        ),
    ])


def render_report_v3(report: ReportV3) -> str:
    mode = getattr(report, "report_mode", "balanced") or "balanced"
    banner = _MODE_BANNER.get(mode, _MODE_BANNER["balanced"])
    parts = [
        "# Agora ReportV3",
        f"Report-ID: `{_cell(report.report_id)}`",
        f"Generiert: `{report.generated_at.isoformat()}`",
        render_simulation_snapshot(report),
        render_simulation_contribution(report),
        banner,
        render_evidence_status(report),
        "## Persona-Tabelle",
        render_persona_table(report.personas),
        "## Segment-Tabelle",
        render_segment_table(report.segments),
        "## Claims",
        render_claim_table(report.claims),
        "## Multipliers",
        _table(
            ["ID", "Name", "Kategorie", "Reichweite", "Evidence"],
            [
                [item.id, item.name, item.kategorie, item.reichweite_score, _list_cell(item.evidence_refs)]
                for item in report.multipliers
            ],
            "Keine Multipliers im ReportV3-Artefakt.",
        ),
        "## Friction Points",
        render_top10_list(report.friction_points),
        "## Trust Signals",
        render_top10_list(report.trust_signals),
        "## Change Recommendations",
        render_top10_list(report.change_recommendations),
        _render_generic_table(
            "Project Impacts",
            [
                [item.id, item.confidence, item.beschreibung, _list_cell(item.affected_segments)]
                for item in report.project_impacts
            ],
            ["ID", "Confidence", "Beschreibung", "Segmente"],
        ),
        _render_generic_table(
            "Positioning Variants",
            [
                [item.id, item.titel, item.claim_text, _list_cell(item.ziel_persona_ids)]
                for item in report.positioning_variants
            ],
            ["ID", "Titel", "Claim", "Personas"],
        ),
        _render_generic_table(
            "Content Ideas",
            [
                [item.id, item.format, item.titel, _list_cell(item.persona_ids)]
                for item in report.content_ideas
            ],
            ["ID", "Format", "Titel", "Personas"],
        ),
        "## Operative Zahlen",
        render_threshold_table(report.thresholds),
        "## Hypothesen ohne Evidence",
        render_hypotheses_table(report.hypotheses),
        "## Data Gaps",
        render_data_gaps(report.data_gaps),
        # Issue #1160 H: zuletzt, weil es ein Nachschlagewerk ist — die
        # Belegkennungen in den Tabellen darueber werden hier aufloesbar.
        "## Evidenz-Nachweise",
        render_evidence_index(report),
    ]
    return "\n\n".join(parts).rstrip() + "\n"


__all__ = [
    "render_claim_table",
    "render_data_gaps",
    "render_simulation_contribution",
    "render_evidence_index",
    "render_evidence_status",
    "render_hypotheses_table",
    "render_persona_table",
    "render_report_v3",
    "render_segment_table",
    "render_threshold_table",
    "render_top10_list",
]
