"""Search-Relevance-Verdict Contract (Pydantic v2).

Codex-Review (PR #1744): ``SearchResult.relevance`` war ein handgeschriebenes
``Dict[str, Any]``, das ``graph_reader.py::_apply_relevance_verdict`` baut und
``SearchResult.to_dict()`` unverändert in die öffentliche Antwort von
``POST /report/tools/search`` durchreicht, sobald die semantische Suche auf
``local_search`` zurückfällt (f001, Slice `search-effect`). Als API-Grenze
gehört die Form in einen Vertrag statt in ein lose typisiertes Dict, das ohne
Validierung driften könnte (AGENTS.md, Contracts-first).

Aufruf zum Schema-Dump: ``cd backend && uv run python -m app.contracts.dump_schemas``
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .decision_contract import DecisionProviderName

_STRICT = ConfigDict(extra="forbid")


class SearchRelevanceVerdict(BaseModel):
    """Relevanz-Verdikt des Decision Layers über den bestbewerteten
    ``local_search``-Treffer — NUR im Modus ``authoritative`` gesetzt
    (``graph_reader.py::_apply_relevance_verdict``). ``shadow``/``disabled``
    liefern kein ``SearchRelevanceVerdict`` (``SearchResult.relevance`` bleibt
    ``None``, das Feld fehlt dann im Payload — byte-gleiches Verhalten zu vor
    diesem Slice).

    ``top_fact_relevant=True`` bei ``probability_yes is None`` ist Absicht,
    kein Default: eine erschöpfte Fallback-Kette (``provider="unresolved"``)
    liefert laut Vertrag kein ``probability_yes`` — fail-open heißt hier, den
    Fakt NICHT zu entfernen, solange kein belastbares Verdikt vorliegt.
    """

    model_config = _STRICT

    top_fact_relevant: bool
    provider: DecisionProviderName
    probability_yes: float | None = Field(default=None, ge=0.0, le=1.0)
    #: ``True`` heißt: das Verdikt kam vom Rule-Rückfall, nicht direkt von
    #: Jev (``DecisionResult.fallback_chain == ["jev", "rule"]``).
    fallback: bool


__all__ = ["SearchRelevanceVerdict"]
