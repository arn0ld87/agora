from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from ..evidence_migrations import normalize_persisted_evidence_map
from ..graph.graph_dtos import graph_origin_of

#: Präfix des kanonischen Seed-Dokument-Ankers (ADR-0013, Issue #1154).
_SEED_DOC_ANCHOR_PREFIX = "seed_doc:"

_SEED_DOC_ANCHOR_RE = re.compile(r"seed_doc:(?P<document_id>[^#]+)#chunk:(?P<chunk_id>\d+)")


def document_role_of(
    provenance: Optional[Dict[str, Any]],
    document_roles: Optional[Dict[str, str]],
) -> Optional[str]:
    """Dokument-Rolle eines Graph-Fakts über seine Provenance (Issue #1240).

    ``None`` bei unbekannter Herkunft oder Standardrolle — geraten wird nicht.
    """
    if not isinstance(provenance, dict) or not document_roles:
        return None
    document_id = str(provenance.get("document_id") or "").strip()
    return document_roles.get(document_id) if document_id else None


def provenance_graph_origin(provenance: Optional[Dict[str, Any]]) -> Optional[str]:
    """Herkunftsmarke einer Retrieval-Provenance — oder ``None`` (ADR-0022 §2).

    ``None`` bei fehlender Provenance und bei extrahierten Elementen: der Fakt
    bleibt dann ein gewöhnlicher Graph-Fakt. Ein unbekannter Markenwert gilt wie
    ein fehlender (``graph_origin_of`` filtert ihn).
    """
    if not isinstance(provenance, dict):
        return None
    return graph_origin_of(provenance)


def build_seed_document_anchor(provenance: Optional[Dict[str, Any]]) -> Optional[str]:
    """``seed_doc:<document_id>#chunk:<chunk_id>`` — oder ``None`` (ADR-0013).

    Erwartet die Retrieval-Provenance aus Issue #1152
    (``provenance_at(...)``). Beide Bestandteile sind Pflicht: Ohne
    ``chunk_id`` zeigt der Anker auf ein ganzes Dokument statt auf die Stelle,
    aus der der Fakt stammt, und wäre nicht mehr überprüfbar. Mehrdeutige oder
    fehlende Herkunft ergibt ``None`` — der Fakt bleibt dann ``graph_relation``,
    statt einen Dokumentbezug zu behaupten, den niemand nachschlagen kann.

    Autorengegebene Quellen-Labels aus dem Chunk-Text (etwa ``A1``–``J1``)
    gehen hier bewusst NICHT ein: sie sind über mehrere Uploads nicht
    eindeutig, zwei Dateien mit gleichem Label und gleicher Chunk-Nummer
    ergäben denselben Anker (Codex-Review zu PR #1153, ADR-0013 Punkt 2).
    """
    if not isinstance(provenance, dict):
        return None
    document_id = str(provenance.get("document_id") or "").strip()
    chunk_id = provenance.get("chunk_id")
    if not document_id or not isinstance(chunk_id, int) or isinstance(chunk_id, bool):
        return None
    anchor = f"{_SEED_DOC_ANCHOR_PREFIX}{document_id}#chunk:{chunk_id}"
    # ``EvidenceRecordModel.source_id_anchor`` ist auf 200 Zeichen begrenzt.
    # Ein gekappter Anker wäre nicht mehr auflösbar — dann lieber keiner.
    if len(anchor) > 200:
        return None
    # Schreib- und Lesepfad müssen dieselbe Regel anwenden. Sonst entsteht ein
    # Record, den der Schreibpfad für verankert hält und der Lesepfad nicht —
    # er würde bei jedem Laden abgestuft und umgeschlüsselt und wechselte so
    # dauerhaft seine Identität. Deshalb prüft der Bau mit dem Leser gegen
    # (negative Chunk-Nummer, ``#`` in der Dokument-ID).
    return anchor if is_verified_seed_document_anchor(anchor) else None


def is_verified_seed_document_anchor(anchor: Any) -> bool:
    """Prüft, ob ``anchor`` das kanonische Seed-Dokument-Format trägt.

    Gegenstück zu :func:`build_seed_document_anchor` für den Lesepfad: ein
    persistiertes ``seed_corpus``-Item ohne solchen Anker ist nicht als
    Dokumentfakt überprüfbar (ADR-0013).
    """
    if not isinstance(anchor, str):
        return False
    return _SEED_DOC_ANCHOR_RE.fullmatch(anchor.strip()) is not None


# ---------------------------------------------------------------------------
# M11.8e — Quote-Anchor-Validator
# ---------------------------------------------------------------------------

_QUOTE_TAG_RE = re.compile(
    r"<simulated_quote\s+([^>]+)>(.*?)</simulated_quote>",
    re.DOTALL,
)
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
# Issue #1249: ``_SEED_DOC_PREFIX`` ist mit der Praefix-Ausnahme entfallen.
# Sie war die einzige Verwendung — ein Anker wird jetzt unabhaengig von seinem
# Praefix gegen ``known_anchors`` geprueft.


@dataclass(frozen=True)
class QuoteValidationResult:
    """Ergebnis der <simulated_quote>-Anker-Validierung für einen Report-Abschnitt."""

    valid: bool
    quotes: List[Dict[str, Any]] = field(default_factory=list)
    invalid_quotes: List[Dict[str, Any]] = field(default_factory=list)
    unbound_evidence_refs: List[str] = field(default_factory=list)
    missing_evidence_refs: List[str] = field(default_factory=list)


def _extract_known_anchors(evidence_map: Union[Dict[str, Any], Any]) -> set:
    """Extrahiert alle bekannten source_id_anchor-Werte aus der EvidenceMap.

    Unterstützt sowohl rohe dicts (agent.evidence_map) als auch
    EvidenceMapModel-Instanzen.
    """
    known: set = set()
    if hasattr(evidence_map, "evidence_index"):
        # EvidenceMapModel-Instanz
        for evidence_id, item in evidence_map.evidence_index.items():
            known.add(evidence_id)
            anchor = getattr(item, "source_id_anchor", None)
            if anchor:
                known.add(anchor)
    elif isinstance(evidence_map, dict):
        evidence_map = normalize_persisted_evidence_map(evidence_map) or evidence_map
        for evidence_id, item in (evidence_map.get("evidence_index") or {}).items():
            known.add(evidence_id)
            anchor = item.get("source_id_anchor")
            if anchor:
                known.add(anchor)
    return known


def validate_quote_anchors(
    section_text: str,
    evidence_map: Union[Dict[str, Any], Any],
    persona_ids: List[str],
) -> QuoteValidationResult:
    """Parst <simulated_quote>-Tags und prüft Bindung an EvidenceMap + Persona-Plan.

    Args:
        section_text: Der vollständige Markdown-Text eines generierten Abschnitts.
        evidence_map: Die aktuelle EvidenceMap (raw dict oder EvidenceMapModel-Instanz).
        persona_ids: Liste bekannter Persona-IDs aus dem Report-Plan.

    Returns:
        QuoteValidationResult mit valid=True nur wenn alle Quotes korrekt
        annotiert sind (persona_id vorhanden + bekannt, seed_anchor vorhanden).
        Ein vorhandener, aber nicht aufloesbarer Anker macht das Zitat nicht
        ungueltig, erscheint aber in ``unbound_evidence_refs`` — seit #1249
        unabhaengig davon, ob er ein ``ev_``- oder ein ``seed_doc:``-Anker ist.
        Sections ohne Quotes → valid=True.
    """
    known_anchors = _extract_known_anchors(evidence_map)
    persona_id_set = set(persona_ids)

    valid_quotes: List[Dict[str, Any]] = []
    invalid_quotes: List[Dict[str, Any]] = []
    unbound_refs: List[str] = []

    for match in _QUOTE_TAG_RE.finditer(section_text):
        attrs_raw = match.group(1)
        text = match.group(2).strip()
        raw_tag = match.group(0)

        attrs = dict(_ATTR_RE.findall(attrs_raw))
        persona_id = attrs.get("persona_id")
        seed_anchor = attrs.get("seed_anchor")

        reasons: List[str] = []

        if not persona_id:
            reasons.append("missing persona_id")
        elif persona_id_set and persona_id not in persona_id_set:
            # Nur prüfen wenn die Whitelist nicht leer ist; leere Liste = unkonfiguriert
            reasons.append(f"unknown persona_id={persona_id!r}")

        if not seed_anchor:
            reasons.append("missing seed_anchor")
        elif seed_anchor not in known_anchors:
            if not reasons:
                unbound_refs.append(seed_anchor)

        if reasons:
            invalid_quotes.append(
                {
                    "raw": raw_tag,
                    "persona_id": persona_id,
                    "seed_anchor": seed_anchor,
                    "text": text,
                    "reason": "; ".join(reasons),
                }
            )
        else:
            valid_quotes.append(
                {
                    "persona_id": persona_id,
                    "seed_anchor": seed_anchor,
                    "text": text,
                }
            )

    # valid=True wenn keine Invalid-Quotes und keine ungebundenen Refs vorhanden.
    # Sections ohne Quotes → valid=True (Aufrufer entscheidet ob Pflicht).
    is_valid = len(invalid_quotes) == 0 and len(unbound_refs) == 0

    return QuoteValidationResult(
        valid=is_valid,
        quotes=valid_quotes,
        invalid_quotes=invalid_quotes,
        unbound_evidence_refs=unbound_refs,
        missing_evidence_refs=[],  # Reserviert für Claim-DTO-Pflichtfelder (separater Slice)
    )


__all__ = [
    "QuoteValidationResult",
    "_ATTR_RE",
    "_QUOTE_TAG_RE",
    "_SEED_DOC_ANCHOR_PREFIX",
    "_SEED_DOC_ANCHOR_RE",
    "_extract_known_anchors",
    "build_seed_document_anchor",
    "document_role_of",
    "is_verified_seed_document_anchor",
    "provenance_graph_origin",
    "validate_quote_anchors",
]
