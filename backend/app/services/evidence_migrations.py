"""Evidence-Map-Migration v1 -> v2, P2.1-Anker-Migration und v2 -> ReportV3.

Sub-Slice 02a — Refs #107.
Sub-Slice P2.1 — Evidence-Anker-Pflicht für medium/high-Claims.
Sub-Slice P3.1 — ReportV3-Persistenz (PLAN.md §4.1).

- ``migrate_v1_to_v2`` hebt persistierte Evidence-Maps auf schema_version=2.
- ``migrate_legacy_claims_to_anchored`` entfernt orphan Claims VOR Validator,
  damit Bestands-evidence-map.json nicht beim Reload an
  ``ReportClaimModel.non_low_claims_need_evidence`` scheitern.
- ``migrate_v2_to_v3`` baut aus einem v2-Report-Dict ein dict, das
  ``ReportV3.model_validate()`` besteht. ``CURRENT_SCHEMA_VERSION`` bleibt 2 —
  es ist die Evidence-Map-Schema-Version, NICHT die Report-Container-Version.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

CURRENT_SCHEMA_VERSION = 2

# Confidence-Labels, die einen Evidence-Anker erfordern (P2.1).
_ANCHOR_REQUIRED_LABELS = frozenset({"medium", "high", "verified"})


def migrate_v1_to_v2(raw: Optional[dict]) -> Optional[dict]:
    """Hebt eine persistierte Evidence-Map auf schema_version=2.

    - ``None`` und bereits auf v2 stehende Maps werden unverändert zurückgegeben.
    - Mutiert das übergebene Dict in-place (entspricht dem Plan-Snippet aus
      PLAN.md Teil D.2) und reicht es zurück, damit Caller wahlweise
      Rückgabewert oder Original verwenden können.
    - Section-Einträge erben ``schema_version`` auf v2.
    """
    if raw is None:
        return None
    if raw.get("schema_version") == CURRENT_SCHEMA_VERSION:
        return raw

    raw["schema_version"] = CURRENT_SCHEMA_VERSION
    sections = raw.get("sections") or []
    for section in sections:
        if isinstance(section, dict):
            section["schema_version"] = CURRENT_SCHEMA_VERSION
    return raw


def migrate_legacy_claims_to_anchored(raw: Optional[dict]) -> Optional[dict]:
    """P2.1: Überführt Claims ohne Evidence-Anker in data_gaps.

    Verhindert, dass alte ``evidence-map.json``-Dateien beim Reload durch
    den ``ReportClaimModel``-Validator (``non_low_claims_need_evidence``)
    abgelehnt werden.

    Regeln (spiegeln ``_finalize_section_claims`` in agent.py):
    - Claim ohne Evidence + ``confidence_label`` in {medium, high, verified}
      → entfernen aus ``claims[]``, anhängen an ``data_gaps[]`` mit
      ``gap_reason="no_evidence_bound"``.
    - Claim ohne Evidence + ``confidence_label=low`` oder kein Label
      → unverändert lassen (Validator erlaubt das).
    - Hypotheses- und Data-Gaps-Felder werden initialisiert, falls sie
      in der Section noch nicht existieren.

    Gibt ``None`` zurück, wenn ``raw`` None ist. Mutiert das übergebene Dict.
    """
    if raw is None:
        return None

    sections = raw.get("sections") or []
    for section in sections:
        if not isinstance(section, dict):
            continue

        section.setdefault("hypotheses", [])
        section.setdefault("data_gaps", [])

        claims = section.get("claims") or []
        surviving_claims = []

        for claim in claims:
            if not isinstance(claim, dict):
                surviving_claims.append(claim)
                continue

            evidence = claim.get("evidence") or []
            label = str(claim.get("confidence_label") or "").lower()

            if not evidence and label in _ANCHOR_REQUIRED_LABELS:
                index = len(section["data_gaps"]) + 1
                claim_text = (
                    str(claim.get("claim_text") or claim.get("claim") or "").strip()
                    or "Legacy claim ohne Evidence-Text."
                )[:1000]
                section["data_gaps"].append({
                    "gap_id": f"gap_{index:02d}",
                    "claim_text": claim_text,
                    "gap_reason": "no_evidence_bound",
                    "suggested_fix": "Evidence per Graph- oder Agent-Tool nachreichen.",
                })
            else:
                surviving_claims.append(claim)

        section["claims"] = surviving_claims

    return raw


def migrate_v2_to_v3(
    raw: dict,
    *,
    simulation_id: Optional[str] = None,
) -> dict:
    """Wandelt ein v2-Report-dict in ein ReportV3-valides dict.

    Die Funktion arbeitet additiv: v2-Persistenz bleibt unangetastet.
    Claims und DataGaps werden aus der Evidence-Map-Struktur abgeleitet;
    Personas, Segments, FrictionPoints und TrustSignals werden als leere
    Listen emittiert (ggf. mit einem erläuternden DataGap-Eintrag).

    Args:
        raw: Bereits geladenes v2-Report-dict (z. B. aus meta.json oder
             dem evidence_map-dict).
        simulation_id: Optionale Simulation-ID für DataGap-Hinweise.

    Returns:
        dict passend für ``ReportV3.model_validate()``.
    """
    report_id: str = str(raw.get("report_id") or "unknown")
    generated_at: str = datetime.now(timezone.utc).isoformat()

    claims: list[dict] = []
    data_gaps: list[dict] = []

    sections = raw.get("sections") or []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_index = int(section.get("section_index") or 0)

        for claim in section.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            claim_id = str(
                claim.get("claim_id") or f"claim_{len(claims) + 1:02d}"
            )
            evidence_items = [
                item for item in (claim.get("evidence") or [])
                if isinstance(item, dict)
            ]
            evidence_refs = []
            for idx, item in enumerate(evidence_items, 1):
                ref = str(
                    item.get("source_id_anchor")
                    or item.get("anchor")
                    or item.get("source")
                    or f"section_{section_index}:{claim_id}:evidence_{idx:02d}"
                ).strip()
                evidence_refs.append(
                    ref or f"section_{section_index}:{claim_id}:evidence_{idx:02d}"
                )

            if not evidence_refs:
                continue

            statement = str(
                claim.get("claim_text") or claim.get("claim") or ""
            ).strip()
            if len(statement) < 8:
                continue

            label = str(claim.get("confidence_label") or "low")
            if label in {"high", "verified"}:
                confidence = "high"
            elif label == "medium":
                confidence = "medium"
            else:
                confidence = "low"

            claims.append(
                {
                    "id": claim_id,
                    "statement": statement,
                    "evidence_refs": evidence_refs,
                    "confidence": confidence,
                    "aggregation_basis": "persona",
                }
            )

        for gap in section.get("data_gaps") or []:
            if not isinstance(gap, dict):
                continue
            gap_id = str(
                gap.get("gap_id") or f"gap_{len(data_gaps) + 1:02d}"
            )
            claim_text = str(gap.get("claim_text") or "")
            reason = str(gap.get("gap_reason") or "").strip()
            description = claim_text
            if reason:
                description = f"{claim_text} ({reason})" if claim_text else reason
            description = description.strip() or "Datenluecke ohne Claim-Text."
            suggested_fix = gap.get("suggested_fix")
            data_gaps.append(
                {
                    "id": gap_id,
                    "beschreibung": description,
                    "severity": "medium",
                    "suggested_fixes": (
                        [str(suggested_fix)] if suggested_fix else []
                    ),
                }
            )

        for hypothesis in section.get("hypotheses") or []:
            if not isinstance(hypothesis, dict):
                continue
            hypothesis_id = str(
                hypothesis.get("hypothesis_id")
                or f"hypothesis_{len(data_gaps) + 1:02d}"
            )
            text = str(hypothesis.get("hypothesis_text") or "").strip()
            if not text:
                continue
            data_gaps.append(
                {
                    "id": hypothesis_id,
                    "beschreibung": text,
                    "severity": "low",
                    "suggested_fixes": [
                        str(item)
                        for item in (hypothesis.get("suggested_evidence") or [])
                        if str(item).strip()
                    ],
                }
            )

    if not raw.get("personas"):
        hint = "Persona-Daten nicht in v2-Persistenz enthalten"
        if simulation_id:
            hint += f" (simulation_id={simulation_id})"
        hint += " — Personas aus Persona-Storage nachzuladen."
        data_gaps.append(
            {
                "id": "dg-migration-personas",
                "beschreibung": hint,
                "severity": "low",
                "suggested_fixes": [
                    "Persona-Storage über simulation_id laden und Personas ergänzen."
                ],
            }
        )

    return {
        "schema_version": 3,
        "report_id": report_id,
        "generated_at": generated_at,
        "personas": [],
        "segments": [],
        "claims": claims,
        "multipliers": [],
        "friction_points": [],
        "trust_signals": [],
        "change_recommendations": [],
        "project_impacts": [],
        "positioning_variants": [],
        "content_ideas": [],
        "data_gaps": data_gaps,
    }
