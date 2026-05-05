from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

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
        "global_evidence": global_evidence,
        "sections": [],
    }
    return EvidenceMapModel.model_validate(payload).model_dump(mode="json")


def record_evidence_item(
    active_section_evidence: Optional[List[Dict[str, Any]]],
    item: Dict[str, Any],
) -> List[Dict[str, Any]]:
    target = list(active_section_evidence or [])
    target.append(item)
    return target


def resolve_embedder(
    *,
    cached: Any,
    logger: Any,
) -> Optional[Callable[[str], List[float]]]:
    if cached != "missing":
        return cached
    try:
        from ...storage.embedding_service import EmbeddingService

        service = EmbeddingService()
        return service.embed
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug(f"EvidenceBinder: kein Embedder verfügbar ({exc!r})")
        return None


def normalize_claims_for_contract(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for claim in claims:
        item = dict(claim)
        item.pop("claim", None)
        item.pop("confidence", None)
        item.pop("evidence_items", None)
        normalized.append(item)
    return normalized


def normalize_sections_for_contract(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized_sections: List[Dict[str, Any]] = []
    for section in sections:
        item = {k: v for k, v in dict(section).items() if k != "schema_version"}
        item["section_title"] = (item.get("section_title") or "Recovered section").strip()
        summary = (item.get("section_summary") or item.get("section_title") or "Recovered summary").strip()
        item["section_summary"] = summary
        claims = normalize_claims_for_contract(item.get("claims") or [])
        if not claims:
            claims = [{
                "claim_id": "claim_01",
                "claim_text": "No claim candidate extracted from this section.",
                "confidence_score": 0.0,
                "confidence_label": "low",
                "evidence": [],
                "notes": "Recovered section without persisted claims.",
                "audit_trail": [],
            }]
        item["claims"] = claims
        normalized_sections.append(item)
    return normalized_sections


__all__ = [
    "init_evidence_map",
    "normalize_claims_for_contract",
    "normalize_sections_for_contract",
    "record_evidence_item",
    "resolve_embedder",
]
