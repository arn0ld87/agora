"""Evidence-Map-Migration v1 -> v2, P2.1-Anker-Migration und v2 -> ReportV3.

Sub-Slice 02a — Refs #107.
Sub-Slice P2.1 — Evidence-Anker-Pflicht für medium/high-Claims.
Sub-Slice P3.1 — ReportV3-Persistenz (PLAN.md §4.1).
P3.1-Followup — Echte Persona/Segment/FrictionPoint/TrustSignal-Aggregation
  in ``migrate_v2_to_v3`` (PLAN.md §4.1).

- ``migrate_v1_to_v2`` hebt persistierte Evidence-Maps auf schema_version=2.
- ``migrate_legacy_claims_to_anchored`` entfernt orphan Claims VOR Validator,
  damit Bestands-evidence-map.json nicht beim Reload an
  ``ReportClaimModel.non_low_claims_need_evidence`` scheitern.
- ``migrate_v2_to_v3`` baut aus einem v2-Report-Dict ein dict, das
  ``ReportV3.model_validate()`` besteht. ``CURRENT_SCHEMA_VERSION`` bleibt 2 —
  es ist die Evidence-Map-Schema-Version, NICHT die Report-Container-Version.
  Neu (P3.1-Followup): Personas aus ``artifact_store`` (``reddit_profiles``),
  Segments per Gruppen-Aggregation, FrictionPoints/TrustSignals aus
  Sections mit Keyword-Matching auf Section-Titel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .artifact_store import SimulationArtifactStore

CURRENT_SCHEMA_VERSION = 2

# Confidence-Labels, die einen Evidence-Anker erfordern (P2.1).
_ANCHOR_REQUIRED_LABELS = frozenset({"medium", "high", "verified"})

# Section-Titel-Schlüsselwörter für FrictionPoints und TrustSignals.
_FRICTION_KEYWORDS = frozenset({"reibungspunkt", "reibungs", "friction", "hindernis", "barriere"})
_TRUST_KEYWORDS = frozenset({"vertrauenssignal", "vertrauens", "trust", "cialdini"})

# Signal-Type-Fallback für TrustSignals aus Section-Claims.
_DEFAULT_TRUST_SIGNAL_TYPE = "authority"

# Erlaubte voice_register-Werte (gespiegelt aus report_v3.Persona).
_VALID_VOICE_REGISTERS = frozenset({"formal-de", "neutral-de", "technical-de", "skeptisch-de"})
_DEFAULT_VOICE_REGISTER = "neutral-de"


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


def _resolve_evidence_refs(
    claim: dict[str, Any],
    section_index: int,
    claim_id: str,
) -> list[str]:
    """Extrahiert Evidence-Refs aus einem Claim-dict."""
    evidence_items = [
        item for item in (claim.get("evidence") or [])
        if isinstance(item, dict)
    ]
    refs: list[str] = []
    for idx, item in enumerate(evidence_items, 1):
        ref = str(
            item.get("source_id_anchor")
            or item.get("anchor")
            or item.get("source")
            or f"section_{section_index}:{claim_id}:evidence_{idx:02d}"
        ).strip()
        refs.append(ref or f"section_{section_index}:{claim_id}:evidence_{idx:02d}")
    return refs


def _label_to_confidence(label: str) -> str:
    """Normalisiert ein Confidence-Label auf low/medium/high."""
    if label in {"high", "verified"}:
        return "high"
    if label == "medium":
        return "medium"
    return "low"


def _section_title_matches(section_title: str, keywords: frozenset[str]) -> bool:
    """True wenn ein Keyword im Section-Titel vorkommt (case-insensitive)."""
    lower = section_title.lower()
    return any(kw in lower for kw in keywords)


def _load_personas_from_store(
    simulation_id: str,
    artifact_store: "SimulationArtifactStore",
) -> list[dict[str, Any]]:
    """Liest reddit_profiles aus dem Artifact-Store für simulation_id."""
    profiles = artifact_store.read_json(simulation_id, "reddit_profiles", default=None)
    if not isinstance(profiles, list):
        return []
    return [p for p in profiles if isinstance(p, dict)]


def _map_profile_to_persona(profile: dict[str, Any], index: int) -> dict[str, Any]:
    """Mappt ein reddit_profiles-Eintrag auf ein Persona-dict für ReportV3."""
    user_id = str(profile.get("user_id") or profile.get("source_entity_uuid") or f"p{index:03d}")
    persona_id = f"persona_{user_id}"

    raw_vr = str(profile.get("voice_register") or "").strip()
    voice_register = raw_vr if raw_vr in _VALID_VOICE_REGISTERS else _DEFAULT_VOICE_REGISTER

    age = profile.get("age")
    alter_range = str(int(age)) if isinstance(age, (int, float)) and age > 0 else "unbekannt"

    beruf = str(profile.get("profession") or profile.get("name") or "").strip() or "unbekannt"
    region = str(profile.get("country") or profile.get("location") or "DACH").strip() or "DACH"

    needs: list[str] = []
    topics = profile.get("interested_topics")
    if isinstance(topics, list):
        needs = [str(t) for t in topics if str(t).strip()]
    elif isinstance(topics, str) and topics.strip():
        needs = [t.strip() for t in topics.split(",") if t.strip()]

    evidence_refs: list[str] = []
    src_uuid = profile.get("source_entity_uuid")
    if src_uuid:
        evidence_refs.append(f"entity:{src_uuid}")

    return {
        "id": persona_id,
        "voice_register": voice_register,
        "alter_range": alter_range,
        "beruf": beruf,
        "region": region,
        "needs": needs,
        "values": [],
        "evidence_refs": evidence_refs,
    }


def _aggregate_segments(personas: list[dict[str, Any]], profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregiert Personas nach Segment-Tag (aus reddit_profiles) zu Segmenten."""
    # segment_name → {"persona_ids": [...], "beschreibung": "..."}
    segment_map: dict[str, dict[str, Any]] = {}

    for profile, persona in zip(profiles, personas):
        seg_tag = str(
            profile.get("segment")
            or profile.get("source_entity_type")
            or "sonstige"
        ).strip() or "sonstige"

        if seg_tag not in segment_map:
            segment_map[seg_tag] = {
                "persona_ids": [],
                "source_entity_type": str(profile.get("source_entity_type") or "").strip(),
            }
        segment_map[seg_tag]["persona_ids"].append(persona["id"])

    segments: list[dict[str, Any]] = []
    for idx, (seg_name, seg_data) in enumerate(sorted(segment_map.items()), 1):
        seg_id = f"segment_{idx:02d}"
        persona_ids = seg_data["persona_ids"]
        beschreibung = (
            f"Segment '{seg_name}' mit {len(persona_ids)} Persona(s)."
        )
        segments.append({
            "id": seg_id,
            "name": seg_name,
            "beschreibung": beschreibung,
            "persona_ids": persona_ids,
        })

    return segments


def migrate_v2_to_v3(
    raw: dict,
    *,
    simulation_id: Optional[str] = None,
    artifact_store: "Optional[SimulationArtifactStore]" = None,
) -> dict:
    """Wandelt ein v2-Report-dict in ein ReportV3-valides dict.

    Die Funktion arbeitet additiv: v2-Persistenz bleibt unangetastet.
    Claims und DataGaps werden aus der Evidence-Map-Struktur abgeleitet.

    Neu (P3.1-Followup): Wenn ``simulation_id`` und ``artifact_store``
    übergeben werden, aggregiert die Funktion echte Daten:
    - Personas: aus ``reddit_profiles`` im Artifact-Store.
    - Segments: aus Persona-Segment-Tags (Gruppen-Aggregation).
    - FrictionPoints: aus Sections mit Keyword "Reibungspunkt" in Section-Titel.
    - TrustSignals: aus Sections mit Keyword "Vertrauenssignal" in Section-Titel.

    Fallback: Wenn kein Artifact-Store übergeben wird oder keine Personas
    gefunden werden, bleibt der DataGap-Marker ``dg-migration-personas``
    wie bisher erhalten.

    Args:
        raw: Bereits geladenes v2-Report-dict (z. B. aus meta.json oder
             dem evidence_map-dict).
        simulation_id: Optionale Simulation-ID für Artifact-Store-Lookup
             und DataGap-Hinweise.
        artifact_store: Optionaler Artifact-Store für Persona-Daten.
             Wenn None, wird keine Persona-Aggregation durchgeführt.

    Returns:
        dict passend für ``ReportV3.model_validate()``.
    """
    report_id: str = str(raw.get("report_id") or "unknown")
    generated_at: str = datetime.now(timezone.utc).isoformat()

    claims: list[dict] = []
    data_gaps: list[dict] = []
    friction_points: list[dict] = []
    trust_signals: list[dict] = []

    sections = raw.get("sections") or []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_index = int(section.get("section_index") or 0)
        section_title = str(section.get("section_title") or "")

        is_friction_section = _section_title_matches(section_title, _FRICTION_KEYWORDS)
        is_trust_section = _section_title_matches(section_title, _TRUST_KEYWORDS)

        for claim in section.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            claim_id = str(
                claim.get("claim_id") or f"claim_{len(claims) + 1:02d}"
            )
            evidence_refs = _resolve_evidence_refs(claim, section_index, claim_id)

            if not evidence_refs:
                continue

            statement = str(
                claim.get("claim_text") or claim.get("claim") or ""
            ).strip()
            if len(statement) < 8:
                continue

            label = str(claim.get("confidence_label") or "low")
            confidence = _label_to_confidence(label)

            if is_friction_section:
                # Severity aus Confidence ableiten
                severity = confidence  # "low" | "medium" | "high"
                friction_points.append({
                    "id": claim_id,
                    "beschreibung": statement,
                    "severity": severity,
                    "affected_persona_ids": list(claim.get("persona_ids") or []),
                    "evidence_refs": evidence_refs,
                })
            elif is_trust_section:
                trust_signals.append({
                    "id": claim_id,
                    "beschreibung": statement,
                    "signal_type": _DEFAULT_TRUST_SIGNAL_TYPE,
                    "evidence_refs": evidence_refs,
                })
            else:
                claims.append({
                    "id": claim_id,
                    "statement": statement,
                    "evidence_refs": evidence_refs,
                    "confidence": confidence,
                    "aggregation_basis": "persona",
                })

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

    # --- Persona-Aggregation (P3.1-Followup) ---
    personas: list[dict] = []
    segments: list[dict] = []

    # Zuerst v2-interne Personas prüfen (falls schon im dict vorhanden)
    raw_personas = raw.get("personas") or []
    if raw_personas and isinstance(raw_personas, list):
        personas = [p for p in raw_personas if isinstance(p, dict)]

    # Wenn keine internen Personas, aus Artifact-Store lesen
    if not personas and artifact_store is not None and simulation_id:
        profiles = _load_personas_from_store(simulation_id, artifact_store)
        if profiles:
            personas = [
                _map_profile_to_persona(profile, idx)
                for idx, profile in enumerate(profiles, 1)
            ]
            segments = _aggregate_segments(personas, profiles)

    # DataGap-Marker wenn keine Personas gefunden
    if not personas:
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
        "personas": personas,
        "segments": segments,
        "claims": claims,
        "multipliers": [],
        "friction_points": friction_points,
        "trust_signals": trust_signals,
        "change_recommendations": [],
        "project_impacts": [],
        "positioning_variants": [],
        "content_ideas": [],
        "data_gaps": data_gaps,
    }
