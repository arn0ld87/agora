"""OntologyManager + OntologyMutationService (Issue #11).

Allows the NER pipeline to flag *novel* entities — names that don't map
onto any existing type in the graph's ontology — and, depending on the
configured mode, integrate them as new types on the fly.

Three modes (``Config.ONTOLOGY_MUTATION_MODE``):

* ``disabled`` — novel concepts are dropped; ontology never changes.
* ``review_only`` — patches land in a review buffer (audit log) but are
  NOT applied. Humans / follow-up tooling can promote them later.
* ``auto`` — patches are applied immediately when their confidence score
  clears ``Config.ONTOLOGY_MUTATION_MIN_CONFIDENCE`` (default 0.6).

Confidence scoring today is a deterministic heuristic (see
``score_concept``); an LLM-backed scorer can be swapped in through the
``scorer=`` constructor param without touching callers.

Thread-safety: ``OntologyManager`` guards every read-modify-write cycle
with a per-graph ``threading.Lock``. Two concurrent patches on the same
graph serialize; patches on different graphs run in parallel.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Protocol

from ..storage import GraphStorage
from ..utils.logger import get_logger

logger = get_logger("agora.ontology_mutation")


_LABEL_SAFE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def sanitize_entity_type(value: Any) -> Optional[str]:
    """Mirror of ``_sanitize_label`` in neo4j_storage, but reusable outside Neo4j.

    Returns a Cypher-safe label name or ``None`` when the input cannot be
    sanitised (empty after strip, still non-ASCII, reserved ``Entity``).
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or stripped == "Entity":
        return None
    normalized = re.sub(r"\s+", "_", stripped)
    normalized = re.sub(r"[^A-Za-z0-9_]", "", normalized)
    if not _LABEL_SAFE_RE.match(normalized):
        return None
    return normalized


@dataclass
class OntologyPatch:
    """A proposed addition to a graph's ontology."""

    graph_id: str
    novel_type: str
    sanitised_type: str
    sample_entity: str
    context: str
    confidence: float
    mode: str
    suggested_at: str = field(default_factory=lambda: datetime.now().isoformat())
    applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "novel_type": self.novel_type,
            "sanitised_type": self.sanitised_type,
            "sample_entity": self.sample_entity,
            "context": self.context,
            "confidence": round(self.confidence, 4),
            "mode": self.mode,
            "suggested_at": self.suggested_at,
            "applied": self.applied,
        }


class ConceptScorer(Protocol):
    def __call__(self, novel_type: str, sample_entity: str, context: str) -> float:
        """Return a confidence score in ``[0.0, 1.0]`` for promoting the concept."""
        ...


def default_heuristic_scorer(
    novel_type: str, sample_entity: str, context: str
) -> float:
    """Cheap, deterministic scorer used when no LLM scorer is wired in.

    Heuristic:
    * Penalise types that are generic placeholders (``Thing``, ``Misc``, …).
    * Favour types that look like well-formed, ASCII-only nouns.
    * Slight bonus when the novel type shows up verbatim in the context.
    """
    score = 0.5
    lower = (novel_type or "").lower().strip()
    if lower in {"thing", "misc", "other", "object", "entity", "item"}:
        return 0.0
    if sanitize_entity_type(novel_type) is None:
        return 0.0
    # Length heuristics — single-letter types are noise, very long types
    # tend to be LLM hallucinations rather than real ontology additions.
    if len(lower) < 3:
        score -= 0.2
    elif len(lower) > 30:
        score -= 0.2
    else:
        score += 0.1
    # Verbatim mention in the surrounding context → extra signal.
    if context and lower in context.lower():
        score += 0.2
    # PascalCase / TitleCase input = likely intentional category name.
    if novel_type[:1].isupper():
        score += 0.1
    return max(0.0, min(1.0, score))


class OntologyManager:
    """Thread-safe wrapper around ``GraphStorage.get_ontology / set_ontology``.

    Use ``update(graph_id, patch)`` to merge a patch into the stored
    ontology atomically (read-modify-write under a per-graph lock).
    """

    def __init__(self, storage: GraphStorage) -> None:
        self._storage = storage
        self._locks: Dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, graph_id: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(graph_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[graph_id] = lock
            return lock

    def get(self, graph_id: str) -> Dict[str, Any]:
        return self._storage.get_ontology(graph_id) or {}

    def contains_type(self, graph_id: str, type_name: str) -> bool:
        ontology = self.get(graph_id)
        types = ontology.get("entity_types") or ontology.get("node_types") or []
        if isinstance(types, dict):
            types = list(types.keys())
        return any(
            (t.get("name") if isinstance(t, dict) else str(t)) == type_name
            for t in types
        )

    def update(self, graph_id: str, patch: OntologyPatch) -> Dict[str, Any]:
        """Merge ``patch`` into the ontology. Idempotent on duplicate types."""
        lock = self._lock_for(graph_id)
        with lock:
            ontology = dict(self.get(graph_id))
            entity_types = list(ontology.get("entity_types") or [])
            existing_names = {
                (t.get("name") if isinstance(t, dict) else str(t))
                for t in entity_types
            }
            if patch.sanitised_type not in existing_names:
                entity_types.append(
                    {
                        "name": patch.sanitised_type,
                        "origin": "mutation",
                        "source_entity": patch.sample_entity,
                        "confidence": round(patch.confidence, 4),
                        "added_at": patch.suggested_at,
                    }
                )
                ontology["entity_types"] = entity_types
                self._storage.set_ontology(graph_id, ontology)
                patch.applied = True
                logger.info(
                    "Ontology patch applied: graph=%s type=%s confidence=%.2f",
                    graph_id,
                    patch.sanitised_type,
                    patch.confidence,
                )
            else:
                logger.debug(
                    "Ontology patch skipped (type already present): graph=%s type=%s",
                    graph_id,
                    patch.sanitised_type,
                )
            return ontology


class OntologyMutationService:
    """Evaluate novel concepts and, per mode, apply or just log them."""

    MODE_DISABLED = "disabled"
    MODE_REVIEW_ONLY = "review_only"
    MODE_AUTO = "auto"
    _MODES = (MODE_DISABLED, MODE_REVIEW_ONLY, MODE_AUTO)

    def __init__(
        self,
        manager: OntologyManager,
        *,
        mode: str = MODE_DISABLED,
        min_confidence: float = 0.6,
        scorer: Optional[ConceptScorer] = None,
        audit_sink: Optional[Callable[[OntologyPatch], None]] = None,
        max_audit_log: int = 1000,
    ) -> None:
        if mode not in self._MODES:
            raise ValueError(
                f"Unknown ontology mutation mode {mode!r} "
                f"(expected one of: {', '.join(self._MODES)})"
            )
        self._manager = manager
        self._mode = mode
        self._min_confidence = float(min_confidence)
        self._scorer: ConceptScorer = scorer or default_heuristic_scorer
        self._audit_sink = audit_sink
        self._audit_lock = threading.Lock()
        self._audit_log: List[OntologyPatch] = []
        self._max_audit = int(max_audit_log)

    @property
    def mode(self) -> str:
        return self._mode

    def evaluate(
        self,
        graph_id: str,
        novel_type: str,
        sample_entity: str,
        context: str = "",
    ) -> Optional[OntologyPatch]:
        """Score the concept and, if appropriate, build a patch.

        Returns the :class:`OntologyPatch` when a mutation was *proposed*
        (regardless of whether it was applied). In ``disabled`` mode or
        when sanitisation fails, returns ``None``.
        """
        if self._mode == self.MODE_DISABLED:
            return None

        sanitised = sanitize_entity_type(novel_type)
        if sanitised is None:
            logger.debug("Skipping unusable novel type: %r", novel_type)
            return None

        if self._manager.contains_type(graph_id, sanitised):
            return None

        confidence = float(self._scorer(novel_type, sample_entity, context) or 0.0)
        patch = OntologyPatch(
            graph_id=graph_id,
            novel_type=novel_type,
            sanitised_type=sanitised,
            sample_entity=sample_entity,
            context=context,
            confidence=confidence,
            mode=self._mode,
        )

        if self._mode == self.MODE_AUTO and confidence >= self._min_confidence:
            try:
                self._manager.update(graph_id, patch)
            except Exception as exc:  # noqa: BLE001 — log, keep running
                logger.error(
                    "Ontology mutation auto-apply failed: graph=%s type=%s err=%s",
                    graph_id,
                    sanitised,
                    exc,
                )

        self._record(patch)
        return patch

    def evaluate_batch(
        self,
        graph_id: str,
        novel_entities: List[Dict[str, str]],
    ) -> List[OntologyPatch]:
        patches = []
        for entry in novel_entities:
            patch = self.evaluate(
                graph_id,
                novel_type=entry.get("type", ""),
                sample_entity=entry.get("name", ""),
                context=entry.get("context", ""),
            )
            if patch is not None:
                patches.append(patch)
        return patches

    def _record(self, patch: OntologyPatch) -> None:
        with self._audit_lock:
            self._audit_log.append(patch)
            if len(self._audit_log) > self._max_audit:
                # Trim oldest half — cheap amortised O(1) per insert.
                self._audit_log = self._audit_log[-self._max_audit :]
        if self._audit_sink is not None:
            try:
                self._audit_sink(patch)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ontology audit sink raised: %s", exc)

    def audit_log(self, graph_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._audit_lock:
            items = list(self._audit_log)
        if graph_id:
            items = [p for p in items if p.graph_id == graph_id]
        return [p.to_dict() for p in items]


__all__ = [
    "OntologyManager",
    "OntologyMutationService",
    "OntologyPatch",
    "ConceptScorer",
    "default_heuristic_scorer",
    "sanitize_entity_type",
]
