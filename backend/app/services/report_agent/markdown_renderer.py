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


def render_claim_table(claims: list[Claim]) -> str:
    return _table(
        ["ID", "Confidence", "Basis", "Statement", "Evidence"],
        [
            [
                claim.id,
                claim.confidence,
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
        ["ID", "Severity", "Beschreibung", "Suggested Fixes"],
        [
            [gap.id, gap.severity, gap.beschreibung, _list_cell(gap.suggested_fixes)]
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


def _render_generic_table(title: str, rows: list[list[object]], headers: list[str]) -> str:
    return f"## {title}\n\n" + _table(headers, rows, f"Keine Eintraege fuer {title}.")


_MODE_BANNER: dict[str, str] = {
    "strict": "> **Report-Modus:** strict — Nur belegte Claims, harter Anchor-Validator.",
    "balanced": "> **Report-Modus:** balanced — Belegte Claims plus markierte Hypothesen.",
    "explorative": "> **Report-Modus:** explorative — Alle Claims durch, EXPLORATIVE-Modus.",
}


def render_report_v3(report: ReportV3) -> str:
    mode = getattr(report, "report_mode", "balanced") or "balanced"
    banner = _MODE_BANNER.get(mode, _MODE_BANNER["balanced"])
    parts = [
        "# Agora ReportV3",
        f"Report-ID: `{_cell(report.report_id)}`",
        f"Generiert: `{report.generated_at.isoformat()}`",
        banner,
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
        "## Hypothesen ohne Evidence",
        render_hypotheses_table(report.hypotheses),
        "## Data Gaps",
        render_data_gaps(report.data_gaps),
    ]
    return "\n\n".join(parts).rstrip() + "\n"


__all__ = [
    "render_claim_table",
    "render_data_gaps",
    "render_hypotheses_table",
    "render_persona_table",
    "render_report_v3",
    "render_segment_table",
    "render_top10_list",
]
