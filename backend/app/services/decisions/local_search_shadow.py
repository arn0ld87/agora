"""Shadow-Pilot des Decision Layer (f005, Slice `decision-pilot`, Task
`shadow-usecase`): lokale Keyword-Relevanzbewertung.

Use Case: Nach der lokalen Keyword-Suche (``app.services.graph.graph_reader
::local_search``) trifft dieses Modul GENAU EINE zusätzliche Entscheidung —
wirkt das bestbewertete Ergebnis für die Anfrage relevant? — und
telemetriert sie nur, ohne sie je zu verwenden (ADR-0016, Confidence-
Zustand ``shadow``). Die bestehende Keyword-Sortierung und der
Rückgabewert von ``local_search`` bleiben unverändert; ein Fehler in
diesem Modul darf ``local_search`` nie zum Absturz bringen (siehe
:func:`shadow_relevance_check`).

Bewusst genau EIN Aufruf pro Suche, nicht einer je Treffer: ``local_search``
iteriert über potenziell alle Kanten/Knoten eines Graphen; ein Decision-
Aufruf pro Treffer wäre ein neuer, unbegrenzter Kostenfaktor auf einem
heißen Retrieval-Pfad — das widerspräche "kleiner, risikoarmer Use Case"
(f005-Auftrag, Abschnitt 3, "Retrieval-Entscheidungen"). Ausgewählt aus der
Decision Map (docs/research/f005/decision-map.md, Abschnitt
"Pilotvorschlag"): LocalSearch/PanoramaSearch-Relevanzbewertung hat laut
dortiger Einordnung "geringe Schreibwirkung" — anders als die dort
ebenfalls genannte Persona-Eligibility-Vorprüfung, die tief in eine
mehrfach für Randfälle korrigierte Generierungsfunktion eingreifen müsste
(``oasis_profile_llm.py::_generate_profile_with_llm``, Issues #1246/#1247/
#1461).

Provider: ``RuleProvider`` mit einer deterministischen, kostenlosen Regel
auf dem bereits berechneten Keyword-Score. Kein LLM- oder Jev-Aufruf in
diesem ersten Schritt — ``local_search`` hat heute keinen ``LLMClient`` zur
Hand, und ihn nur für diesen Piloten durch mehrere Aufrufer zu threaden
wäre eine größere, hier nicht gerechtfertigte Änderung. Der Use Case bleibt
austauschbar: jeder ``DecisionProvider`` (Rule/LLM/Fake/Jev) erfüllt
denselben Aufruf über den injizierbaren ``provider``-Parameter.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from app.contracts.decision_contract import DecisionQuestion, DecisionState, NoulQuestion
from app.repositories.decision_provider import DecisionProvider, decision_layer_mode
from app.services.decisions.rule_provider import RuleOutcome, RuleProvider
from app.utils.logger import get_logger

logger = get_logger("agora.decisions.local_search_shadow")

_USE_CASE_ID = "local-search-relevance"

#: ``local_search`` vergibt 100 für einen exakten Query-Treffer, 10 je
#: getroffenes Keyword (``graph_reader.py::match_score``) — 10 heißt:
#: mindestens ein Keyword hat getroffen.
_RELEVANCE_THRESHOLD = 10


def _relevance_rule(state: DecisionState, _question: DecisionQuestion) -> RuleOutcome:
    """Regel: Score des bestbewerteten Treffers >= Schwelle → wahrscheinlich Ja.

    ``_question`` nimmt bewusst ``DecisionQuestion`` (die volle Union) statt
    nur ``NoulQuestion``, obwohl dieser Use Case nur mit ``NoulQuestion``
    aufruft: ``RuleProvider.rule_fn`` ist als ``Callable[[DecisionState,
    DecisionQuestion], RuleOutcome]`` typisiert (Funktionsparameter sind
    kontravariant), eine auf ``NoulQuestion`` verengte Regelfunktion ist
    damit kein gültiges Argument."""
    raw_top_score = state.state.get("top_score", 0) if isinstance(state.state, dict) else 0
    top_score = raw_top_score if isinstance(raw_top_score, (int, float)) else 0
    probability_yes = 1.0 if float(top_score) >= _RELEVANCE_THRESHOLD else 0.0
    return RuleOutcome(answer=None, confidence=1.0, probability_yes=probability_yes)


def _context_hash(query: str, fact: str) -> str:
    """SHA-256 über Query und Fakt — Telemetrie referenziert den Hash, nie
    den Klartext (ADR-0016, Abschnitt Security)."""
    return hashlib.sha256(f"{query}\n{fact}".encode()).hexdigest()[:16]


def shadow_relevance_check(
    query: str,
    top_fact: Optional[str],
    top_score: int,
    *,
    provider: Optional[DecisionProvider] = None,
) -> None:
    """Trifft GENAU EINE Shadow-Entscheidung über das bestbewertete
    ``local_search``-Ergebnis, wenn ``AGORA_DECISION_LAYER_MODE=shadow``
    steht (Default ``disabled`` — dann tut diese Funktion nichts).

    Wirft nie: ein Fehler in der Decision Layer darf die eigentliche Suche
    nicht beeinflussen. ``provider`` ist injizierbar für Tests und für
    einen künftigen Wechsel auf LLM/Fake/Jev, ohne diese Funktion selbst
    zu ändern.
    """
    if decision_layer_mode(_USE_CASE_ID) != "shadow":
        return
    if not top_fact:
        return
    try:
        state = DecisionState(
            use_case_id=_USE_CASE_ID,
            state={"top_score": top_score},
            context_hash=_context_hash(query, top_fact),
        )
        active_provider = provider or RuleProvider(
            use_case_id=_USE_CASE_ID, rule_fn=_relevance_rule
        )
        result = active_provider.decide(state, NoulQuestion())
        shadow_result = result.model_copy(update={"shadow": True})
        logger.info(
            "decision_layer_shadow use_case=%s provider=%s probability_yes=%s "
            "confidence=%s model_version=%s cost_micros=%s latency_ms=%d "
            "request_id=%s context_hash=%s",
            shadow_result.use_case_id,
            shadow_result.provider,
            shadow_result.probability_yes,
            shadow_result.confidence,
            shadow_result.model_version,
            shadow_result.cost_micros,
            shadow_result.latency_ms,
            shadow_result.request_id,
            state.context_hash,
        )
    except Exception:  # noqa: BLE001 - Shadow-Fehler duerfen die Suche nie stoeren
        # ``logger.exception`` hängt den Traceback an, und der enthält die
        # Message der Ausnahme. Die Adapter dieses Projekts halten ihre
        # Fehlermeldungen deshalb payload-frei (``_shape``/``_bounded`` in
        # ``jev_provider``/``llm_provider``). Für eine künftige Ausnahme aus
        # einem fremden SDK gilt das nicht automatisch — wird hier ein
        # externer Provider verdrahtet, ist vor dem Scharfschalten zu
        # prüfen, ob dessen Ausnahmen Anfrageinhalte spiegeln.
        logger.exception("decision_layer_shadow failed for use_case=%s", _USE_CASE_ID)


__all__ = ["shadow_relevance_check"]
