"""RFC-4180-konformer CSV-Export für strukturierte Report-Tabellen.

Keine Flask-Abhängigkeit — pure Funktionen, direkt testbar.

Tabellen:
- personas  → Felder aus contracts.report_v3.Persona
- segments  → Felder aus contracts.report_v3.Segment
- claims    → Felder aus contracts.report_contract.ReportClaimModel (evidence-map)

Sub-Slice P4.2, Refs PLAN.md §5.2
"""
from __future__ import annotations

import csv
import io
from typing import Any


def _writer(buf: io.StringIO) -> csv.writer:
    """csv.writer mit RFC-4180-Dialekt (CRLF, quoting=MINIMAL)."""
    return csv.writer(buf, dialect="excel")


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------

_PERSONA_COLUMNS = [
    "id",
    "voice_register",
    "alter_range",
    "beruf",
    "region",
    "bildungsgrad",
    "haushaltseinkommen",
    "needs",
    "values",
    "evidence_refs",
]


def personas_to_csv(personas: list[dict[str, Any]]) -> str:
    """Wandelt eine Liste von Persona-Dicts in RFC-4180-CSV um.

    Felder die Listen sind (needs, values, evidence_refs) werden
    als semikolongetrennter String serialisiert.
    """
    buf = io.StringIO()
    w = _writer(buf)
    w.writerow(_PERSONA_COLUMNS)
    for p in personas:
        w.writerow([
            p.get("id", ""),
            p.get("voice_register", ""),
            p.get("alter_range", ""),
            p.get("beruf", ""),
            p.get("region", ""),
            p.get("bildungsgrad") or "",
            p.get("haushaltseinkommen") or "",
            ";".join(p.get("needs") or []),
            ";".join(p.get("values") or []),
            ";".join(p.get("evidence_refs") or []),
        ])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------

_SEGMENT_COLUMNS = [
    "id",
    "name",
    "beschreibung",
    "persona_ids",
    "kontaktwahrscheinlichkeit_prozent",
]


def segments_to_csv(segments: list[dict[str, Any]]) -> str:
    """Wandelt eine Liste von Segment-Dicts in RFC-4180-CSV um."""
    buf = io.StringIO()
    w = _writer(buf)
    w.writerow(_SEGMENT_COLUMNS)
    for s in segments:
        kp = s.get("kontaktwahrscheinlichkeit_prozent")
        w.writerow([
            s.get("id", ""),
            s.get("name", ""),
            s.get("beschreibung", ""),
            ";".join(s.get("persona_ids") or []),
            "" if kp is None else str(kp),
        ])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

_CLAIM_COLUMNS = [
    "claim_id",
    "claim_text",
    "confidence_label",
    "confidence_score",
    "section_index",
    "section_title",
    "evidence_count",
    "notes",
]


def claims_to_csv(sections: list[dict[str, Any]]) -> str:
    """Wandelt eine Liste von evidence-map-Sections in RFC-4180-CSV der Claims um.

    ``sections`` entspricht ``EvidenceMapModel.sections`` (list[ReportSectionModel]).
    Jeder Claim wird mit section_index + section_title angereichert.
    """
    buf = io.StringIO()
    w = _writer(buf)
    w.writerow(_CLAIM_COLUMNS)
    for section in sections:
        sec_idx = section.get("section_index", "")
        sec_title = section.get("section_title", "")
        for claim in section.get("claims") or []:
            w.writerow([
                claim.get("claim_id", ""),
                claim.get("claim_text", ""),
                claim.get("confidence_label", ""),
                claim.get("confidence_score", ""),
                sec_idx,
                sec_title,
                len(claim.get("evidence") or []),
                claim.get("notes") or "",
            ])
    return buf.getvalue()
