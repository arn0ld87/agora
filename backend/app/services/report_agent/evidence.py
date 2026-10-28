# ruff: noqa: F401, E402, F811
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:  # pragma: no cover — nur fuer die Typannotation
    from .evidence_ledger import EvidenceCoverageLedger

from ...contracts import EvidenceRecordModel
from ...contracts.report_contract import (
    SEED_DOC_ANCHOR_PREFIX,
    counts_for_confidence,
    has_two_action_voices,
)
from ..confidence_calculator import _count_independent_sources
from ..evidence_identity import build_evidence_id
from ..evidence_migrations import normalize_persisted_evidence_map
from ..graph.graph_dtos import graph_origin_of
from .evidence_claims import (
    TEXT_CONFIDENCE_DOWNGRADE_EVENT,
    _CLAIM_RELATIVE_FIELDS,
    _PLACEHOLDER_TEXTS,
    _VERIFIED_STRONG_MATCH,
    _count_supporting_stakeholder_groups,
    _filter_placeholder_items,
    _hand_work_downgrade_target,
    _is_placeholder,
    _record_text_confidence_downgrade,
    _resolved_evidence,
    _verified_reachable,
    auto_downgrade_unsupported_high_claims,
    downgrade_medium_without_agent_grounded,
    has_agent_grounded_evidence,
    normalize_claims_for_contract,
    normalize_sections_for_contract,
    text_confidence_label_of,
)
from .evidence_degradation import (
    _FALLBACK_RATIONALE,
    _MAX_HYPOTHESIS_FIELD_LEN,
    _MIN_HYPOTHESIS_TEXT_LEN,
    _collect_existing_hypothesis_ids,
    _next_hypothesis_id,
    degrade_sections_for_violations,
)
from .evidence_quotes import (
    QuoteValidationResult,
    _ATTR_RE,
    _QUOTE_TAG_RE,
    _SEED_DOC_ANCHOR_PREFIX,
    _SEED_DOC_ANCHOR_RE,
    _extract_known_anchors,
    build_seed_document_anchor,
    document_role_of,
    is_verified_seed_document_anchor,
    provenance_graph_origin,
    validate_quote_anchors,
)
from .schemas import CURRENT_SCHEMA_VERSION, EvidenceMapModel


def init_evidence_map(
    *,
    report_id: str,
    simulation_id: str,
    global_evidence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    payload = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "report_id": report_id,
        "simulation_id": simulation_id,
        "evidence_index": {},
        "global_evidence_refs": [],
        "sections": [],
    }
    for item in global_evidence:
        record = register_evidence_record(payload, item, scope_id=simulation_id)
        if record is not None:
            payload["global_evidence_refs"].append(record["evidence_id"])
    return EvidenceMapModel.model_validate(payload).model_dump(mode="json")


_TYPE_TO_SOURCE_KIND: Dict[str, str] = {
    "seed_corpus": "seed_corpus",
    "seed_document": "seed_corpus",
    "agent_post": "agent_quote",
    "agent_quote": "agent_quote",
    "agent_interview": "agent_quote",
    "agent_action": "agent_action",
    "agent_behavior": "agent_action",
    "graph_fact": "graph_relation",
    "relationship_chain": "graph_relation",
    "entity_summary": "graph_relation",
    "graph_metric": "graph_relation",
    "graph_metric_status": "graph_relation",
    "graph_relation": "graph_relation",
    "web_search_result": "web_source",
    "web_fetch": "web_source",
    "web_source": "web_source",
}

_VALID_SOURCE_KINDS: frozenset[str] = frozenset(
    {"seed_corpus", "agent_quote", "agent_action", "graph_relation", "web_source", "inferred"}
)


def normalize_source_kind(item: Dict[str, Any]) -> str:
    """Ermittelt die Provenance eines Evidence-Items.

    Ein explizit gesetztes ``source_kind`` gewinnt — inklusive ``inferred``,
    wenn ein Caller einen Modellableitungs-Fakt bewusst so markiert. Sonst
    entscheidet der interne ``type``. Was sich nicht zuordnen lässt, wird
    ``inferred`` — niemals ``seed_corpus``: ein Simulations-Post ist kein
    Dokumentfakt, und eine unbekannte Herkunft erst recht nicht.
    """
    explicit = str(item.get("source_kind") or "").strip()
    if explicit in _VALID_SOURCE_KINDS:
        return explicit

    item_type = str(item.get("type") or "").strip().lower()
    return _TYPE_TO_SOURCE_KIND.get(item_type, "inferred")


def record_evidence_item(
    active_section_evidence: Optional[List[Dict[str, Any]]],
    item: Dict[str, Any],
) -> List[Dict[str, Any]]:
    target = list(active_section_evidence or [])
    enriched = dict(item)
    enriched.setdefault("source_kind", normalize_source_kind(item))
    target.append(enriched)
    return target


def register_evidence_record(
    evidence_map: Dict[str, Any],
    item: Dict[str, Any],
    *,
    scope_id: str,
    ledger: Optional["EvidenceCoverageLedger"] = None,
) -> Optional[Dict[str, Any]]:
    """Validiert und registriert ein Producer-Item mit explizitem Schluessel.

    ``ledger`` protokolliert den Verbleib quantitativer Fakten. Ohne es
    verschwanden im Referenzlauf sechs belegte Zahlenwerte zwischen
    Tool-Ergebnis und Index, ohne dass irgendwo stand, warum — die Rueckgabe
    ``None`` und ein Dedup-Treffer sahen fuer den Aufrufer gleich aus.
    """

    producer_key = str(item.get("producer_key") or "").strip()
    if not producer_key:
        if ledger is not None:
            ledger.dropped(item, "missing_producer_key")
        return None
    source_kind = normalize_source_kind(item)
    payload = {key: value for key, value in item.items() if key not in _CLAIM_RELATIVE_FIELDS}
    payload.update(
        {
            "evidence_id": build_evidence_id(scope_id, source_kind, producer_key),
            "producer_key": producer_key,
            "source_kind": source_kind,
        }
    )
    # Issue #1300: Ein seed_doc:-Anker auf Interview-Evidence ist eine
    # erfundene Dokumentherkunft — der Contract-Validator
    # ``agent_quote_rejects_seed_doc_anchor`` lehnt sie hart ab. An dieser
    # Producer-Boundary wird sie stattdessen entfernt: das Interview-Item
    # behält seine ev_-Identität und persona_stakeholder_group, statt als
    # ganzer Record verloren zu gehen (dieselbe Defensive-Linie wie
    # ``_filter_placeholder_items``). Der Schreibpfad für echte
    # Dokumentfakten (``_graph_fact_item`` -> seed_corpus) bleibt unberührt.
    if source_kind == "agent_quote" and str(payload.get("source_id_anchor") or "").startswith(
        SEED_DOC_ANCHOR_PREFIX
    ):
        payload.pop("source_id_anchor", None)
    record = EvidenceRecordModel.model_validate(payload).model_dump(mode="json")
    evidence_index = evidence_map.setdefault("evidence_index", {})
    existing = evidence_index.get(record["evidence_id"])
    if existing is not None:
        # Gewollt: zwei Suchen liefern denselben Fakt. Fuer die Buchfuehrung
        # ist das trotzdem kein Verschwinden — der Fakt ist unter der
        # bestehenden ID im Index und bleibt auffindbar.
        if ledger is not None:
            ledger.canonicalized(item, str(existing.get("evidence_id") or ""))
        return existing
    evidence_index[record["evidence_id"]] = record
    if ledger is not None:
        ledger.canonicalized(item, str(record["evidence_id"]))
    return record


def resolve_embedder(
    *,
    cached: Any,
    logger: Any,
) -> Optional[Callable[[str], List[float]]]:
    if cached != "missing":
        return cached
    from ..embedding_configurations.runtime import EmbeddingRuntimeConfigurationError

    try:
        from ...storage.embedding_service import EmbeddingService

        service = EmbeddingService()
        return service.embed
    except EmbeddingRuntimeConfigurationError:
        raise
    except Exception as exc:  # pragma: no cover - environment dependent  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.debug(f"EvidenceBinder: kein Embedder verfügbar ({exc!r})")
        return None


__all__ = [
    "QuoteValidationResult",
    "TEXT_CONFIDENCE_DOWNGRADE_EVENT",
    "_ATTR_RE",
    "_CLAIM_RELATIVE_FIELDS",
    "_FALLBACK_RATIONALE",
    "_MAX_HYPOTHESIS_FIELD_LEN",
    "_MIN_HYPOTHESIS_TEXT_LEN",
    "_PLACEHOLDER_TEXTS",
    "_QUOTE_TAG_RE",
    "_SEED_DOC_ANCHOR_PREFIX",
    "_SEED_DOC_ANCHOR_RE",
    "_TYPE_TO_SOURCE_KIND",
    "_VALID_SOURCE_KINDS",
    "_VERIFIED_STRONG_MATCH",
    "_collect_existing_hypothesis_ids",
    "_count_independent_sources",
    "_count_supporting_stakeholder_groups",
    "_extract_known_anchors",
    "_filter_placeholder_items",
    "_hand_work_downgrade_target",
    "_is_placeholder",
    "_next_hypothesis_id",
    "_record_text_confidence_downgrade",
    "_resolved_evidence",
    "_verified_reachable",
    "auto_downgrade_unsupported_high_claims",
    "build_seed_document_anchor",
    "counts_for_confidence",
    "degrade_sections_for_violations",
    "document_role_of",
    "downgrade_medium_without_agent_grounded",
    "graph_origin_of",
    "has_agent_grounded_evidence",
    "has_two_action_voices",
    "init_evidence_map",
    "is_verified_seed_document_anchor",
    "normalize_claims_for_contract",
    "normalize_persisted_evidence_map",
    "normalize_sections_for_contract",
    "normalize_source_kind",
    "provenance_graph_origin",
    "record_evidence_item",
    "register_evidence_record",
    "resolve_embedder",
    "text_confidence_label_of",
    "validate_quote_anchors",
]
