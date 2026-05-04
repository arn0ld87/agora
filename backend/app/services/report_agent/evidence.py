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


__all__ = [
    "init_evidence_map",
    "record_evidence_item",
    "resolve_embedder",
]
