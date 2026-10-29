"""Kanonisches Deep-Modul für Claim-Qualifikation, Quellenidentität und Belegdichte.

Bündelt die fachliche Qualifikation von Claim-Bindings gegen den kanonischen
``evidence_index`` an einer Stelle (Architecture Deepening Slice #1):

1. **Beleg-Auflösung (Q5)**: Jedes Binding in ``claim.evidence[]`` wird gegen
   ``evidence_index[evidence_id]`` aufgelöst. Der kanonische Record trägt
   Herkunft und Identität; das Binding trägt die claim-relativen Felder
   (``match_score``, ``retrieval_score``, ``entailment``, ``supports_claim``,
   ``contradicts_claim``). Disqualifikationen aus Record *oder* Binding
   (``supports_claim=False``, ``counts_for_confidence=False``, disqualifizierende
   ``provenance_class`` oder ``source_kind="inferred"``) setzen sich immer durch.
2. **Stimme vs. Dokumentanker (Q3)**:
   - **Stimme** (``voice_key``) bezeichnet ausschließlich eine simulierte Persona
     (``agent:<id>``, ``agent:<name>``, ``group:<gruppe>`` inkl. Namens- und
     Gruppen-Kollisionsauflösung nach ADR-0002 / #1778).
   - **Dokumentanker** (``document_anchor``) bezeichnet ausschließlich das
     Quellendokument eines Primär-/Korpusbelegs (``doc:<id>`` aus
     ``source_doc_id``/``doc_id``/``seed_doc:<id>#chunk``).
   - Für die Unabhängigkeitszählung (ADR-0002-S) fließen beide getrennt ermittelten
     Identitäten in ``independent_source_keys`` zusammen.
3. **Geltungsbereich, Trägerschaft & Belegdichte (Q2)**:
   ``ConfidenceScope``, ``AggregationBasis``, ``has_agent_grounded_evidence``,
   Stakeholder-Gruppen-Zählung und ``EvidenceDensity`` lesen aus derselben
   qualifizierten Belegmenge.
4. **ReportMode-Gating & Ein-Quellen-Abstufung (Q4)**:
   ``evaluate_claim_mode_gate`` und ``should_downgrade_single_source`` kapseln
   die Modus-Entscheidung (``strict`` / ``balanced`` / ``explorative``) vor dem
   Export in ``ReportV3``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Tuple

from ...contracts.evidence_density_contract import EvidenceDensity
from ...contracts.report_contract import (
    EvidenceSourceKind,
    counts_for_confidence,
    has_two_action_voices,
)

AggregationBasis = Literal["seed", "persona", "aggregat", "datenluecke"]
ConfidenceScope = Literal[
    "simulation_consensus", "simulation_single_voice", "evidence", "empirical"
]
ConfidenceLabelLiteral = Literal["speculative", "low", "medium", "high", "verified"]
ClaimTypeLiteral = Literal["empirical", "analytical", "recommendation", "structural"]

#: Quellengattungen, die den Claim an etwas außerhalb der Simulation binden.
EVIDENCE_BOUND_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "seed_corpus",
        "graph_edge",
        "graph_relation",
        "web_source",
    }
)

#: Quellengattungen, die aus der Simulation stammen.
SIMULATION_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        EvidenceSourceKind.agent_quote.value,
        EvidenceSourceKind.agent_action.value,
    }
)

#: Claim-relative Bindungsfelder am Claim-Eintrag (Schema v3).
CLAIM_RELATIVE_FIELDS: frozenset[str] = frozenset(
    {
        "match_score",
        "retrieval_score",
        "entailment",
        "entailment_reason",
        "supports_claim",
        "contradicts_claim",
    }
)

#: Provenance-Klassen, die keinen Claim als stützender Beleg tragen dürfen.
DISQUALIFYING_PROVENANCE_CLASSES: frozenset[str] = frozenset(
    {
        "template_scaffold",
        "hypothesis",
        "unverified",
        "inferred",
    }
)

#: Auffangtypen zählen nicht als kontrollierte Rollenfamilie (#1248).
GENERIC_ENTITY_TYPES: frozenset[str] = frozenset(
    {"person", "organization", "entity", "node", "unknown", "other"}
)

_BASIS_FOR_DOMINANT_KIND: Mapping[str, AggregationBasis] = {
    "seed_corpus": "seed",
    "agent_quote": "persona",
}

_CLAIM_TYPES: frozenset[str] = frozenset(
    {"empirical", "analytical", "recommendation", "structural"}
)
_VALID_CONFIDENCE: frozenset[str] = frozenset(
    {"speculative", "low", "medium", "high", "verified"}
)

_VERIFIED_STRONG_MATCH: float = 0.85
_SINGLE_SOURCE_CAP: float = 0.59
_CAP_TOLERANCE: float = 1e-9
_ACTION_TYPE: str = "agent_action"
_CHUNK_SUFFIX_RE = re.compile(r":(?:chunk[s_:]?|page[s_:]?|p[:_]?)\d+$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QualifiedEvidenceBinding:
    """Aufgelöster, gegen den kanonischen Index qualifizierter Einzelbeleg."""

    evidence_id: str
    resolved: dict[str, Any]
    source_kind: str
    evidence_type: str
    supports_claim: bool
    contradicts_claim: bool
    entailment: str
    match_score: Optional[float]
    counts_for_confidence: bool
    is_qualifying_support: bool
    voice_key: Optional[str]
    document_anchor: Optional[str]
    independent_source_key: tuple[str, str]
    role_family_key: Optional[str]


@dataclass(frozen=True)
class QualifiedClaimEvidence:
    """Vollständig qualifizierte Belegmenge eines Claims (SSoT für #1)."""

    bindings: tuple[QualifiedEvidenceBinding, ...]
    supporting: tuple[QualifiedEvidenceBinding, ...]
    contradicting: tuple[QualifiedEvidenceBinding, ...]
    related_only: tuple[QualifiedEvidenceBinding, ...]
    valid_evidence_refs: tuple[str, ...]
    supporting_source_kinds: tuple[str, ...]
    supporting_stakeholder_groups: frozenset[str]
    independent_voices: frozenset[str]
    document_anchors: frozenset[str]
    independent_source_keys: tuple[tuple[str, str], ...]
    distinct_independent_sources: int
    supporting_voices_count: int
    has_agent_grounded_evidence: bool
    verified_reachable: bool
    confidence_scope: ConfidenceScope
    aggregation_basis: AggregationBasis


@dataclass(frozen=True)
class ClaimGateDecision:
    """Ergebnis des ReportMode- und Ein-Quellen-Gates für einen Claim."""

    accepted: bool
    confidence: ConfidenceLabelLiteral
    single_source_downgraded: bool
    text_confidence: Optional[ConfidenceLabelLiteral]
    claim_type: Optional[ClaimTypeLiteral]
    drop_reason: Optional[str]
    qualified_evidence: QualifiedClaimEvidence


# ---------------------------------------------------------------------------
# 1. Kanonische Beleg-Auflösung & Disqualifikation (Q5)
# ---------------------------------------------------------------------------


def _has_disqualifying_provenance(mapping: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(mapping, Mapping):
        return False
    prov_class = str(mapping.get("provenance_class") or "").strip().lower()
    if prov_class in DISQUALIFYING_PROVENANCE_CLASSES:
        return True
    if str(mapping.get("source_kind") or "").strip().lower() == "inferred":
        return True
    return False


def is_qualifying_support(
    item: Any,
    record: Optional[Mapping[str, Any]] = None,
    *,
    strict_provenance: bool = False,
) -> bool:
    """Prüft, ob ein Claim-Binding als stützender Beleg zählt (ADR-0022 §4, Befund 1.1).

    Ein Beleg stützt nur, wenn ``supports_claim is True`` am Binding gilt, der
    kanonische Record dem nicht widerspricht (``supports_claim is False``) und
    weder Binding noch Record aus manueller Graph-Handarbeit stammen.
    Mit ``strict_provenance=True`` werden zusätzlich disqualifizierende
    ``provenance_class``-Werte und ``source_kind="inferred"`` ausgeschlossen.
    """
    if not isinstance(item, Mapping) or item.get("supports_claim") is not True:
        return False
    if isinstance(record, Mapping) and record.get("supports_claim") is False:
        return False
    if not counts_for_confidence(item):
        return False
    if isinstance(record, Mapping) and not counts_for_confidence(record):
        return False
    if strict_provenance and (
        _has_disqualifying_provenance(item) or _has_disqualifying_provenance(record)
    ):
        return False
    return True


def _overlay_disqualifications(
    merged: Dict[str, Any],
    entry: Mapping[str, Any],
    record: Optional[Mapping[str, Any]],
) -> None:
    """Stellt sicher, dass Disqualifikationen aus Binding oder Record nie verloren gehen."""
    if entry.get("supports_claim") is False or (
        isinstance(record, Mapping) and record.get("supports_claim") is False
    ):
        merged["supports_claim"] = False
    if not counts_for_confidence(entry):
        merged["graph_origin"] = entry.get("graph_origin")
    elif isinstance(record, Mapping) and not counts_for_confidence(record):
        merged["graph_origin"] = record.get("graph_origin")


def resolve_claim_evidence_item(
    entry: Mapping[str, Any],
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Löst ein einzelnes Claim-Binding gegen ``evidence_index`` auf (Q5).

    Der kanonische Record im ``evidence_index`` ist autoritativ für Herkunft und
    Identität; das Binding ergänzt die claim-relativen Felder
    (``CLAIM_RELATIVE_FIELDS``) sowie Felder, die im Record fehlen. Explizite
    Disqualifikationen aus Binding oder Record setzen sich immer durch.
    """
    index = evidence_index or {}
    evidence_id = str(entry.get("evidence_id") or "")
    raw_record = index.get(evidence_id) if evidence_id else None
    record = raw_record if isinstance(raw_record, Mapping) else None

    if record is None:
        return dict(entry)

    merged: Dict[str, Any] = {k: v for k, v in entry.items() if v is not None}
    merged.update(record)
    for key in CLAIM_RELATIVE_FIELDS:
        if key in entry and entry[key] is not None:
            merged[key] = entry[key]
    _overlay_disqualifications(merged, entry, record)
    return merged


def resolve_claim_evidence_list(
    evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Löst eine Liste von Claim-Bindings gegen ``evidence_index`` auf."""
    if not isinstance(evidence, list):
        return []
    return [
        resolve_claim_evidence_item(entry, evidence_index)
        for entry in evidence
        if isinstance(entry, Mapping)
    ]


def supporting_entries_for_claim(
    claim: Mapping[str, Any],
    evidence_index: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Deduplizierte, qualifiziert stützende Belege eines Claims (Befund 1.1)."""
    merged: Dict[str, Dict[str, Any]] = {}
    raw_evidence = claim.get("evidence") if isinstance(claim, Mapping) else None
    for entry in raw_evidence or []:
        if not isinstance(entry, Mapping):
            continue
        evidence_id = entry.get("evidence_id")
        if not evidence_id or entry.get("supports_claim") is not True:
            continue
        key = str(evidence_id)
        if key in merged:
            continue
        raw_record = evidence_index.get(key) if isinstance(evidence_index, Mapping) else None
        record = raw_record if isinstance(raw_record, Mapping) else None
        if not is_qualifying_support(entry, record, strict_provenance=True):
            continue
        combined = resolve_claim_evidence_item(entry, evidence_index)
        if not is_qualifying_support(combined, record, strict_provenance=True):
            continue
        merged[key] = combined
    return list(merged.values())


# ---------------------------------------------------------------------------
# 2. Stimme (Persona) vs. Dokumentanker (Primärquelle) (Q3)
# ---------------------------------------------------------------------------


def _normalised(value: Any) -> str:
    """Vergleichsform eines Namens: Whitespace-Kollaps und casefold."""
    return " ".join(str(value or "").split()).casefold()


def _looks_like_technical_id(token: str) -> bool:
    """Prüft, ob ein normalisierter Suffix eine technische Agenten-ID ist."""
    if not token:
        return False
    if token.isdigit():
        return True
    for prefix in ("agent_", "id_", "persona_"):
        if token.startswith(prefix) and token[len(prefix) :].isdigit():
            return True
    return False


def _first_source_field(
    sources: Sequence[Mapping[str, Any]],
    field: str,
    *,
    allow_raw: bool = False,
) -> str:
    """Liest den ersten nicht-leeren normalisierten Feldwert aus ``sources``."""
    for source in sources:
        val = _normalised(source.get(field))
        if not val and allow_raw:
            raw = source.get("raw")
            val = _normalised(raw.get(field)) if isinstance(raw, Mapping) else ""
        if val:
            return val
    return ""


def _parse_voice_key_token(
    vk: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Klassifiziert einen normalisierten ``voice_key`` als ``(id_key, name_key, other_vk)``."""
    if ":" not in vk:
        if _looks_like_technical_id(vk):
            return f"agent:{vk}", None, None
        return None, None, f"voice:{vk}"
    prefix, rest = vk.split(":", 1)
    rest = rest.strip()
    if not rest:
        return None, None, None
    if prefix in ("agent_id", "id") or (prefix == "agent" and _looks_like_technical_id(rest)):
        return f"agent:{rest}", None, None
    if prefix in ("name", "agent_name", "agent"):
        return None, f"agent:{rest}", None
    return None, None, f"{prefix}:{rest}"


def _extract_voice_identity_parts(
    item: Mapping[str, Any],
    record: Optional[Mapping[str, Any]],
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Zerlegt die Persona-Hinweise aus ``record`` und ``item`` in kanonische Tokens."""
    sources = [s for s in (record, item) if isinstance(s, Mapping)]
    aid = _first_source_field(sources, "agent_id", allow_raw=True)
    id_key: Optional[str] = f"agent:{aid}" if aid else None
    name_key: Optional[str] = None
    other_vk: Optional[str] = None

    for source in sources:
        vk = _normalised(source.get("voice_key"))
        if not vk:
            continue
        vk_id, vk_name, vk_other = _parse_voice_key_token(vk)
        id_key = id_key or vk_id
        name_key = name_key or vk_name
        other_vk = other_vk or vk_other

    name = _first_source_field(sources, "agent_name", allow_raw=True)
    if name and name_key is None:
        name_key = f"agent:{name}"

    group = _first_source_field(sources, "persona_stakeholder_group", allow_raw=True)
    if not group:
        group = _first_source_field(sources, "stakeholder_group", allow_raw=True)
    group_key: Optional[str] = f"group:{group}" if group else None

    return id_key, name_key, other_vk, group_key


def resolve_voice_key(
    item: Mapping[str, Any],
    record: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """Identität der **Stimme** (Persona) hinter einem Beleg, oder ``None``."""
    id_key, name_key, other_vk, group_key = _extract_voice_identity_parts(item, record)
    return id_key or other_vk or name_key or group_key


def _build_name_to_ids_map(
    parts_list: Sequence[tuple[Optional[str], Optional[str], Optional[str], Optional[str]]],
) -> dict[str, set[str]]:
    name_to_ids: dict[str, set[str]] = {}
    for id_key, name_key, _, _ in parts_list:
        if id_key and name_key:
            name_to_ids.setdefault(name_key, set()).add(id_key)
    return name_to_ids


def _resolve_primary_voice_candidate(
    id_key: Optional[str],
    name_key: Optional[str],
    other_vk: Optional[str],
    group_key: Optional[str],
    name_to_ids: Mapping[str, set[str]],
) -> Optional[str]:
    primary = id_key or other_vk or name_key or group_key
    if primary is not None and id_key is None and other_vk is None and primary == name_key:
        linked_ids = name_to_ids.get(name_key)
        if linked_ids and len(linked_ids) == 1:
            primary = next(iter(linked_ids))
    return primary


def _apply_group_fallback_collision(
    candidate: Optional[str],
    id_key: Optional[str],
    name_key: Optional[str],
    other_vk: Optional[str],
    group_key: Optional[str],
    group_to_speakers: Mapping[str, set[str]],
) -> Optional[str]:
    if (
        candidate is not None
        and candidate == group_key
        and (not id_key and not name_key and not other_vk)
    ):
        speakers = group_to_speakers.get(group_key)
        if speakers:
            return sorted(speakers)[0]
    return candidate


def resolve_canonical_voice_keys(
    pairs: Sequence[tuple[Mapping[str, Any], Optional[Mapping[str, Any]]]],
) -> list[Optional[str]]:
    """Löst Stimmen-Schlüssel über eine Folge von ``(item, record)``-Paaren auf."""
    parts_list = [_extract_voice_identity_parts(item, record) for item, record in pairs]
    name_to_ids = _build_name_to_ids_map(parts_list)

    group_to_speakers: dict[str, set[str]] = {}
    resolved_candidates: list[Optional[str]] = []
    for id_key, name_key, other_vk, group_key in parts_list:
        primary = _resolve_primary_voice_candidate(
            id_key, name_key, other_vk, group_key, name_to_ids
        )
        speaker_identity = id_key or other_vk or (primary if primary != group_key else None)
        if speaker_identity and group_key:
            group_to_speakers.setdefault(group_key, set()).add(speaker_identity)
        resolved_candidates.append(primary)

    return [
        _apply_group_fallback_collision(
            candidate, id_key, name_key, other_vk, group_key, group_to_speakers
        )
        for candidate, (id_key, name_key, other_vk, group_key) in zip(
            resolved_candidates, parts_list
        )
    ]


def _extract_doc_from_anchor(anchor: str) -> Optional[str]:
    for pfx in ("seed_doc:", "seed-doc:", "doc:"):
        if anchor.startswith(pfx):
            rest = anchor[len(pfx) :].strip()
            if "#" in rest:
                doc_part = rest.split("#", 1)[0].strip()
            else:
                doc_part = _CHUNK_SUFFIX_RE.sub("", rest).strip()
            if doc_part:
                return f"doc:{doc_part}"
    return None


def _seed_doc_key_from_mapping(record: Mapping[str, Any]) -> Optional[str]:
    """Ermittelt den kanonischen **Dokumentanker** (``doc:<id>``) eines Primärbelegs."""
    for field in ("source_doc_id", "document_id", "doc_id"):
        val = record.get(field)
        if val is not None and str(val).strip():
            return f"doc:{str(val).strip()}"

    anchor = str(record.get("source_id_anchor") or "").strip()
    if anchor:
        doc_from_anchor = _extract_doc_from_anchor(anchor)
        if doc_from_anchor:
            return doc_from_anchor
        return f"anchor:{anchor}"

    kind = str(record.get("source_kind") or record.get("type") or "").strip().lower()
    if kind in {"seed_corpus", "seed_document", "document"}:
        source = str(record.get("source") or "").strip()
        if source:
            doc_part = source.split("#")[0]
            return f"doc:{doc_part}"

    return None


def resolve_document_anchor(
    item: Mapping[str, Any],
    record: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """Ermittelt den **Dokumentanker** eines Belegs (``doc:<id>``), oder ``None``.

    Im Gegensatz zu ``resolve_voice_key`` (Stimme einer simulierten Persona)
    identifiziert der Dokumentanker das Ursprungsdokument im Seed-Korpus,
    sodass mehrere Chunks desselben Dokuments als *eine* Quelle zählen (Q3, Befund 1.2).
    """
    if isinstance(record, Mapping):
        doc_key = _seed_doc_key_from_mapping(record)
        if doc_key:
            return doc_key
    if isinstance(item, Mapping):
        return _seed_doc_key_from_mapping(item)
    return None


def _normalize_entry_pair(
    entry: Any,
) -> tuple[Mapping[str, Any], Optional[Mapping[str, Any]]]:
    if isinstance(entry, tuple) and len(entry) == 2:
        it, rec = entry
        it_map = it if isinstance(it, Mapping) else {}
        rec_map = rec if isinstance(rec, Mapping) else None
        return it_map, rec_map
    if isinstance(entry, Mapping):
        return entry, entry
    return {}, None


def _fallback_field(
    item: Mapping[str, Any],
    record: Optional[Mapping[str, Any]],
    *keys: str,
) -> str:
    for k in keys:
        val = item.get(k)
        if val is not None and str(val).strip():
            return str(val).strip()
        if record is not None:
            rval = record.get(k)
            if rval is not None and str(rval).strip():
                return str(rval).strip()
    return ""


def _resolve_non_voice_key(
    item: Mapping[str, Any],
    record: Optional[Mapping[str, Any]],
    index: int,
) -> tuple[str, str]:
    doc_key = resolve_document_anchor(item, record)
    if doc_key:
        return ("doc", str(doc_key))

    source_val = _fallback_field(item, record, "source")
    if source_val:
        type_val = _fallback_field(item, record, "type", "source_kind") or "source"
        return ("source", f"{type_val}:{source_val}")

    eid = _fallback_field(item, record, "evidence_id")
    if eid:
        return ("ref", eid)
    return ("inline", str(index))


def resolve_independent_source_keys(
    items_or_pairs: Sequence[Any],
) -> list[tuple[str, str]]:
    """Löst eine Sequenz von Belegen in eindeutige Unabhängigkeitsschlüssel auf.

    Trennt intern **Stimme** (``("voice", voice_key)``) und **Dokumentanker**
    (``("doc", document_anchor)``) und führt beide für die Unabhängigkeitszählung
    (ADR-0002-S) zusammen.
    """
    normalized_pairs = [_normalize_entry_pair(entry) for entry in items_or_pairs]
    voice_keys = resolve_canonical_voice_keys(normalized_pairs)

    keys: list[tuple[str, str]] = []
    for i, (item, record) in enumerate(normalized_pairs):
        vk = voice_keys[i]
        if vk:
            keys.append(("voice", str(vk)))
        else:
            keys.append(_resolve_non_voice_key(item, record, i))

    return keys


def count_independent_sources(items_or_pairs: Sequence[Any]) -> int:
    """Anzahl unabhängiger Quellen über Stimmen, Dokumentanker und sonstige Quellen."""
    return len(set(resolve_independent_source_keys(items_or_pairs)))


def count_independent_sources_for_refs(
    evidence_refs: Iterable[str],
    raw_evidence: Any,
    evidence_index: Mapping[str, Any],
) -> int:
    """Zählt unabhängige Stützquellen unter den gültigen ``evidence_refs`` eines Claims."""
    items_by_eid: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw_evidence, list):
        for item in raw_evidence:
            if isinstance(item, dict) and item.get("evidence_id"):
                eid = str(item.get("evidence_id"))
                if eid not in items_by_eid and item.get("supports_claim") is True:
                    items_by_eid[eid] = item

    pairs: list[tuple[Dict[str, Any], Optional[Mapping[str, Any]]]] = []
    for eid in evidence_refs:
        item = items_by_eid.get(eid) or {"evidence_id": eid}
        record = evidence_index.get(eid) if isinstance(evidence_index, Mapping) else None
        record_map = record if isinstance(record, Mapping) else None
        pairs.append((item, record_map))

    return count_independent_sources(pairs)


# ---------------------------------------------------------------------------
# 3. Herkunft, Geltungsbereich, Rollenfamilien & Agent-Grounding (Q2)
# ---------------------------------------------------------------------------


def _effective_source_kind(
    item: Mapping[str, Any],
    record: Optional[Mapping[str, Any]],
) -> str:
    """Ermittelt die Quellengattung eines Bindings (Inline-Override vor Index-Fallback)."""
    kind = str(item.get("source_kind") or "").strip()
    if not kind and isinstance(record, Mapping):
        kind = str(record.get("source_kind") or "").strip()
    return kind


def supporting_source_kinds(
    evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> list[str]:
    """Quellengattungen der stützenden Items, in Reihenfolge des Auftretens."""
    if not isinstance(evidence, list):
        return []
    index = evidence_index or {}
    kinds: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        record = index.get(str(item.get("evidence_id") or ""))
        record_map = record if isinstance(record, Mapping) else None
        if not is_qualifying_support(item, record_map):
            continue
        kinds.append(_effective_source_kind(item, record_map))
    return kinds


def count_supporting_voices(
    evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> int:
    """Anzahl verschiedener Stimmen unter den stützenden Items (#1766)."""
    if not isinstance(evidence, list):
        return 0
    index = evidence_index or {}
    qualifying_pairs: list[tuple[Mapping[str, Any], Optional[Mapping[str, Any]]]] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        record = index.get(str(item.get("evidence_id") or ""))
        record_map = record if isinstance(record, Mapping) else None
        if not is_qualifying_support(item, record_map):
            continue
        qualifying_pairs.append((item, record_map))

    resolved: set[str] = set()
    unresolved = False
    for key in resolve_canonical_voice_keys(qualifying_pairs):
        if key is None:
            unresolved = True
        else:
            resolved.add(key)
    if resolved:
        return len(resolved)
    return 1 if unresolved else 0


def derive_confidence_scope(
    evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> ConfidenceScope:
    """Leitet den Geltungsbereich aus den stützenden Evidence-Items ab."""
    kinds = supporting_source_kinds(evidence, evidence_index)
    if any(kind in EVIDENCE_BOUND_SOURCE_KINDS for kind in kinds):
        return "evidence"
    if kinds and count_supporting_voices(evidence, evidence_index) < 2:
        return "simulation_single_voice"
    return "simulation_consensus"


def derive_aggregation_basis(
    evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> AggregationBasis:
    """Leitet die Trägerschaft aus der dominanten Quellengattung ab."""
    kinds = supporting_source_kinds(evidence, evidence_index)
    if not kinds:
        return "datenluecke"
    dominant, count = Counter(kinds).most_common(1)[0]
    if count * 2 <= len(kinds):
        return "aggregat"
    return _BASIS_FOR_DOMINANT_KIND.get(dominant, "aggregat")


def role_family_key_for_entry(entry: Mapping[str, Any]) -> Optional[str]:
    """Kanonischer Rollenfamilien-/Gruppenschlüssel eines ``agent_quote``-Belegs (#1248)."""
    family = " ".join(str(entry.get("persona_role_family") or "").split()).casefold()
    if family and family not in GENERIC_ENTITY_TYPES:
        return f"family:{family}"
    group = " ".join(str(entry.get("persona_stakeholder_group") or "").split()).casefold()
    if group:
        return f"title:{group}"
    return None


def supporting_stakeholder_groups(
    evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> frozenset[str]:
    """Unterschiedliche Stakeholder-Gruppen unter stützenden ``agent_quote``-Belegen."""
    resolved_list = (
        resolve_claim_evidence_list(evidence, evidence_index)
        if evidence_index is not None
        else [e for e in (evidence or []) if isinstance(e, Mapping)]
    )
    groups: set[str] = set()
    for entry in resolved_list:
        if not counts_for_confidence(entry):
            continue
        if entry.get("source_kind") != "agent_quote":
            continue
        if not entry.get("supports_claim"):
            continue
        key = role_family_key_for_entry(entry)
        if key:
            groups.add(key)
    return frozenset(groups)


def count_supporting_stakeholder_groups(
    evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> int:
    """Anzahl unterschiedlicher Stakeholder-Gruppen unter stützender ``agent_quote``-Evidence."""
    return len(supporting_stakeholder_groups(evidence, evidence_index))


def has_agent_grounded_evidence(
    evidence: Any,
    *,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> bool:
    """Prüft ADR-0002 Stufe ``agent_grounded`` (für ``medium``)."""
    has_agent_quote = False
    has_seed_corpus = False
    action_voices: List[Tuple[Any, Any]] = []
    index = evidence_index or {}
    for entry in evidence or []:
        if not isinstance(entry, Mapping):
            continue
        record = index.get(str(entry.get("evidence_id") or ""))
        source = record if isinstance(record, Mapping) else entry
        if not counts_for_confidence(entry) or not counts_for_confidence(source):
            continue
        if entry.get("supports_claim") is False or source.get("supports_claim") is False:
            continue
        sk = source.get("source_kind")
        if sk == "agent_quote" and source.get("quote"):
            has_agent_quote = True
        elif sk == "seed_corpus":
            has_seed_corpus = True
        if entry.get("supports_claim", source.get("supports_claim")) is True:
            action_voices.append((sk, source.get("voice_key")))
    return (has_agent_quote and has_seed_corpus) or has_two_action_voices(action_voices)


def verified_reachable(evidence: Sequence[Mapping[str, Any]]) -> bool:
    """Trägt diese Evidence die Stufe ``verified`` auch ohne Handarbeit?"""
    has_strong_match = any(
        float(entry.get("match_score") or 0.0) >= _VERIFIED_STRONG_MATCH
        for entry in evidence
        if "match_score" in entry
    )
    return has_strong_match and count_independent_sources(evidence) >= 2


def valid_evidence_refs_for_claim(
    claim: Mapping[str, Any],
    evidence_index: Mapping[str, Any],
) -> List[str]:
    """Extrahiert deduplizierte, unterstützende ``evidence_id``-Referenzen eines Claims."""
    refs: List[str] = []
    raw_evidence = claim.get("evidence") if isinstance(claim, Mapping) else None
    for item in raw_evidence or []:
        if not isinstance(item, Mapping):
            continue
        raw_id = item.get("evidence_id")
        if not raw_id or item.get("supports_claim") is not True:
            continue
        if not counts_for_confidence(item):
            continue
        eid = str(raw_id)
        idx_entry = evidence_index.get(eid) if isinstance(evidence_index, Mapping) else None
        if isinstance(idx_entry, Mapping) and not counts_for_confidence(idx_entry):
            continue
        if eid not in refs:
            refs.append(eid)
    return refs


# ---------------------------------------------------------------------------
# 4. Deep Qualification Entry Point (QualifiedClaimEvidence)
# ---------------------------------------------------------------------------


def _classify_binding_entailment(
    binding: QualifiedEvidenceBinding,
) -> Literal["supporting", "contradicting", "related"]:
    if binding.contradicts_claim or binding.entailment == "CONTRADICTED":
        return "contradicting"
    if binding.is_qualifying_support:
        return "supporting"
    return "related"


def _build_qualified_binding(
    item: Mapping[str, Any],
    record: Optional[Mapping[str, Any]],
    resolved: dict[str, Any],
    voice_key: Optional[str],
    indep_key: tuple[str, str],
) -> QualifiedEvidenceBinding:
    eid = str(item.get("evidence_id") or resolved.get("evidence_id") or "")
    sk = _effective_source_kind(item, record)
    ev_type = str(resolved.get("type") or sk or "")
    counts = counts_for_confidence(item) and (
        counts_for_confidence(record) if isinstance(record, Mapping) else True
    )
    qualifying = is_qualifying_support(item, record, strict_provenance=True)
    raw_score = resolved.get("match_score")
    match_score = (
        float(raw_score)
        if raw_score is not None
        and isinstance(raw_score, (int, float))
        and not isinstance(raw_score, bool)
        else None
    )
    doc_anchor = resolve_document_anchor(item, record)
    role_key = role_family_key_for_entry(resolved) if sk == "agent_quote" and qualifying else None
    return QualifiedEvidenceBinding(
        evidence_id=eid,
        resolved=resolved,
        source_kind=sk,
        evidence_type=ev_type,
        supports_claim=bool(resolved.get("supports_claim") is True),
        contradicts_claim=bool(resolved.get("contradicts_claim") is True),
        entailment=str(resolved.get("entailment") or "").upper(),
        match_score=match_score,
        counts_for_confidence=counts,
        is_qualifying_support=qualifying,
        voice_key=voice_key,
        document_anchor=doc_anchor,
        independent_source_key=indep_key,
        role_family_key=role_key,
    )


def _extract_raw_evidence_items(claim_or_evidence: Any) -> list[Mapping[str, Any]]:
    raw_list = (
        claim_or_evidence.get("evidence")
        if isinstance(claim_or_evidence, Mapping)
        else claim_or_evidence
    )
    return [entry for entry in (raw_list or []) if isinstance(entry, Mapping)]


def _partition_qualified_bindings(
    items: Sequence[Mapping[str, Any]],
    index: Mapping[str, Any],
) -> tuple[
    list[QualifiedEvidenceBinding],
    list[QualifiedEvidenceBinding],
    list[QualifiedEvidenceBinding],
    list[QualifiedEvidenceBinding],
]:
    pairs: list[tuple[Mapping[str, Any], Optional[Mapping[str, Any]]]] = []
    resolved_dicts: list[dict[str, Any]] = []
    for item in items:
        eid = str(item.get("evidence_id") or "")
        raw_rec = index.get(eid) if eid else None
        rec = raw_rec if isinstance(raw_rec, Mapping) else None
        pairs.append((item, rec))
        resolved_dicts.append(resolve_claim_evidence_item(item, index))

    voice_keys = resolve_canonical_voice_keys(pairs)
    indep_keys = resolve_independent_source_keys(pairs)

    all_bindings: list[QualifiedEvidenceBinding] = []
    supporting: list[QualifiedEvidenceBinding] = []
    contradicting: list[QualifiedEvidenceBinding] = []
    related_only: list[QualifiedEvidenceBinding] = []
    seen_supporting_ids: set[str] = set()

    for item, (_, rec), resolved, vk, ik in zip(
        items, pairs, resolved_dicts, voice_keys, indep_keys
    ):
        qb = _build_qualified_binding(item, rec, resolved, vk, ik)
        all_bindings.append(qb)
        bucket = _classify_binding_entailment(qb)
        if bucket == "contradicting":
            contradicting.append(qb)
        elif bucket == "supporting":
            if not qb.evidence_id or qb.evidence_id not in seen_supporting_ids:
                if qb.evidence_id:
                    seen_supporting_ids.add(qb.evidence_id)
                supporting.append(qb)
        else:
            related_only.append(qb)

    return all_bindings, supporting, contradicting, related_only


def qualify_claim_evidence(
    claim_or_evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> QualifiedClaimEvidence:
    """Qualifiziert alle Belege eines Claims in einem Durchlauf (Deep Module SSoT).

    Akzeptiert entweder ein Claim-Dict (mit ``claim["evidence"]``) oder direkt
    eine ``evidence``-Liste. Liefert ``QualifiedClaimEvidence`` mit strikt
    getrennten **Stimmen** (``independent_voices``) und **Dokumentankern**
    (``document_anchors``) sowie dem zusammengeführten Unabhängigkeitsschlüssel
    (``independent_source_keys``).
    """
    items = _extract_raw_evidence_items(claim_or_evidence)
    index: Mapping[str, Any] = evidence_index if isinstance(evidence_index, Mapping) else {}
    all_bindings, supporting, contradicting, related_only = _partition_qualified_bindings(
        items, index
    )

    supporting_pairs = [
        (b.resolved, index.get(b.evidence_id) if b.evidence_id in index else None)
        for b in supporting
    ]
    supporting_indep_keys = tuple(resolve_independent_source_keys(supporting_pairs))
    supporting_voice_keys = resolve_canonical_voice_keys(supporting_pairs)

    voices = frozenset(vk for vk in supporting_voice_keys if vk is not None)
    doc_anchors = frozenset(
        b.document_anchor for b in supporting if b.document_anchor is not None
    )
    groups = frozenset(b.role_family_key for b in supporting if b.role_family_key is not None)
    valid_refs = (
        tuple(valid_evidence_refs_for_claim({"evidence": items}, index))
        if items
        else ()
    )

    counted_resolved = [b.resolved for b in all_bindings if b.counts_for_confidence]
    return QualifiedClaimEvidence(
        bindings=tuple(all_bindings),
        supporting=tuple(supporting),
        contradicting=tuple(contradicting),
        related_only=tuple(related_only),
        valid_evidence_refs=valid_refs,
        supporting_source_kinds=tuple(supporting_source_kinds(items, index)),
        supporting_stakeholder_groups=groups,
        independent_voices=voices,
        document_anchors=doc_anchors,
        independent_source_keys=supporting_indep_keys,
        distinct_independent_sources=len(set(supporting_indep_keys)),
        supporting_voices_count=count_supporting_voices(items, index),
        has_agent_grounded_evidence=has_agent_grounded_evidence(items, evidence_index=index),
        verified_reachable=verified_reachable(counted_resolved),
        confidence_scope=derive_confidence_scope(items, index),
        aggregation_basis=derive_aggregation_basis(items, index),
    )


# ---------------------------------------------------------------------------
# 5. ReportMode-Gating & Ein-Quellen-Abstufung (Q4)
# ---------------------------------------------------------------------------


def claim_type_of(claim: Mapping[str, Any]) -> Optional[ClaimTypeLiteral]:
    value = claim.get("claim_type")
    return value if value in _CLAIM_TYPES else None  # type: ignore[return-value]


def wording_confidence(
    claim_type: Optional[str],
    confidence: ConfidenceLabelLiteral,
) -> Optional[ConfidenceLabelLiteral]:
    """Issue #1400: der Wortlaut-Hinweis gilt nur Tatsachenbehauptungen."""
    return confidence if claim_type in (None, "empirical") else None


def should_downgrade_single_source(
    independent_sources: int,
    confidence: str,
    claim_type: Optional[str],
) -> bool:
    """Prüft, ob ein Claim wegen Einzelquelle auf ``low`` abgestuft werden muss."""
    if independent_sources > 1:
        return False
    if confidence in {"high", "verified"}:
        return True
    return confidence == "medium" and claim_type not in ("structural", "recommendation")


def evaluate_claim_mode_gate(
    claim: Mapping[str, Any],
    evidence_index: Mapping[str, Any],
    *,
    report_mode: Optional[str] = None,
    recorded_text_confidence: Optional[ConfidenceLabelLiteral] = None,
) -> ClaimGateDecision:
    """Bewertet einen Claim gegen Ein-Quellen-Deckel und ``report_mode`` (Q4)."""
    qualified = qualify_claim_evidence(claim, evidence_index)
    label = str(claim.get("confidence_label") or "speculative")
    confidence: ConfidenceLabelLiteral = (
        label if label in _VALID_CONFIDENCE else "speculative"  # type: ignore[assignment]
    )
    c_type = claim_type_of(claim)

    if not qualified.valid_evidence_refs:
        return ClaimGateDecision(
            accepted=False,
            confidence=confidence,
            single_source_downgraded=False,
            text_confidence=recorded_text_confidence,
            claim_type=c_type,
            drop_reason="no_valid_evidence_refs",
            qualified_evidence=qualified,
        )

    statement = str(claim.get("claim_text") or claim.get("claim") or "").strip()
    if len(statement) < 8:
        return ClaimGateDecision(
            accepted=False,
            confidence=confidence,
            single_source_downgraded=False,
            text_confidence=recorded_text_confidence,
            claim_type=c_type,
            drop_reason="statement_too_short",
            qualified_evidence=qualified,
        )

    indep_count = count_independent_sources_for_refs(
        qualified.valid_evidence_refs,
        claim.get("evidence"),
        evidence_index,
    )
    single_source_downgraded = False
    single_source_text_conf: Optional[ConfidenceLabelLiteral] = None
    if should_downgrade_single_source(indep_count, confidence, c_type):
        single_source_downgraded = True
        single_source_text_conf = wording_confidence(c_type, confidence)
        confidence = "low"

    effective_text_conf = (
        recorded_text_confidence
        if recorded_text_confidence and recorded_text_confidence != confidence
        else single_source_text_conf
    )

    if report_mode == "strict" and confidence in {"speculative", "low"}:
        return ClaimGateDecision(
            accepted=False,
            confidence=confidence,
            single_source_downgraded=single_source_downgraded,
            text_confidence=effective_text_conf,
            claim_type=c_type,
            drop_reason="strict_mode_low_confidence",
            qualified_evidence=qualified,
        )

    return ClaimGateDecision(
        accepted=True,
        confidence=confidence,
        single_source_downgraded=single_source_downgraded,
        text_confidence=effective_text_conf,
        claim_type=c_type,
        drop_reason=None,
        qualified_evidence=qualified,
    )


# ---------------------------------------------------------------------------
# 6. Belegdichte (EvidenceDensity) aus qualifizierten Belegen (Q2)
# ---------------------------------------------------------------------------


def _is_at_single_source_cap(claim: Mapping[str, Any]) -> bool:
    score = claim.get("confidence_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return False
    return abs(float(score) - _SINGLE_SOURCE_CAP) <= _CAP_TOLERANCE


def _ratio(count: int, total: int) -> Optional[float]:
    return count / total if total else None


def compute_evidence_density(evidence_map: Mapping[str, Any]) -> EvidenceDensity:
    """Zählt die Belegdichte der Claims einer Evidence-Map über ``supporting_entries_for_claim``."""
    raw_index = evidence_map.get("evidence_index") if isinstance(evidence_map, Mapping) else None
    evidence_index: Mapping[str, Any] = raw_index if isinstance(raw_index, Mapping) else {}
    raw_sections = evidence_map.get("sections") if isinstance(evidence_map, Mapping) else None

    total = without = single = multi = multi_independent = at_cap = with_action = 0
    links_by_type: Counter[str] = Counter()

    for section in raw_sections or []:
        if not isinstance(section, Mapping):
            continue
        for claim in section.get("claims") or []:
            if not isinstance(claim, Mapping):
                continue
            total += 1
            at_cap += _is_at_single_source_cap(claim)
            supporting = supporting_entries_for_claim(claim, evidence_index)
            if not supporting:
                without += 1
                continue
            kinds = [str(entry.get("type") or "unknown") for entry in supporting]
            links_by_type.update(kinds)
            if len(supporting) == 1:
                single += 1
            else:
                multi += 1
                multi_independent += count_independent_sources(supporting) >= 2
            with_action += _ACTION_TYPE in kinds

    return EvidenceDensity(
        claims_total=total,
        claims_without_support=without,
        claims_single_support=single,
        claims_multi_support=multi,
        claims_multi_independent=multi_independent,
        claims_at_single_source_cap=at_cap,
        claims_with_action_support=with_action,
        supporting_links_by_type=dict(sorted(links_by_type.items())),
        single_support_ratio=_ratio(single, total),
        action_support_ratio=_ratio(with_action, total),
        single_source_cap_ratio=_ratio(at_cap, total),
        multi_independent_ratio=_ratio(multi_independent, total),
    )


__all__ = [
    "AggregationBasis",
    "CLAIM_RELATIVE_FIELDS",
    "ClaimGateDecision",
    "ClaimTypeLiteral",
    "ConfidenceLabelLiteral",
    "ConfidenceScope",
    "DISQUALIFYING_PROVENANCE_CLASSES",
    "EVIDENCE_BOUND_SOURCE_KINDS",
    "GENERIC_ENTITY_TYPES",
    "QualifiedClaimEvidence",
    "QualifiedEvidenceBinding",
    "SIMULATION_SOURCE_KINDS",
    "claim_type_of",
    "compute_evidence_density",
    "count_independent_sources",
    "count_independent_sources_for_refs",
    "count_supporting_stakeholder_groups",
    "count_supporting_voices",
    "derive_aggregation_basis",
    "derive_confidence_scope",
    "evaluate_claim_mode_gate",
    "has_agent_grounded_evidence",
    "is_qualifying_support",
    "qualify_claim_evidence",
    "resolve_canonical_voice_keys",
    "resolve_claim_evidence_item",
    "resolve_claim_evidence_list",
    "resolve_document_anchor",
    "resolve_independent_source_keys",
    "resolve_voice_key",
    "role_family_key_for_entry",
    "should_downgrade_single_source",
    "supporting_entries_for_claim",
    "supporting_source_kinds",
    "supporting_stakeholder_groups",
    "valid_evidence_refs_for_claim",
    "verified_reachable",
    "wording_confidence",
]
