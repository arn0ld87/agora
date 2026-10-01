"""Decision-Layer-Use-Case `local-search-relevance` (f005, Slice
`decision-pilot`/`jev-core`, Tasks `shadow-usecase`/`resolve-fn`): lokale
Keyword-Relevanzbewertung.

Use Case: Nach der lokalen Keyword-Suche (``app.services.graph.graph_reader
::local_search``) trifft dieses Modul GENAU EINE zusätzliche Entscheidung —
wirkt das bestbewertete Ergebnis für die Anfrage relevant? Bewusst genau EIN
Aufruf pro Suche, nicht einer je Treffer: ``local_search`` iteriert über
potenziell alle Kanten/Knoten eines Graphen; ein Decision-Aufruf pro Treffer
wäre ein neuer, unbegrenzter Kostenfaktor auf einem heißen Retrieval-Pfad —
das widerspräche "kleiner, risikoarmer Use Case" (f005-Auftrag, Abschnitt 3,
"Retrieval-Entscheidungen"). Ausgewählt aus der Decision Map
(docs/research/f005/decision-map.md, Abschnitt "Pilotvorschlag").

``resolve_relevance`` deckt alle drei ``AGORA_DECISION_LAYER_MODE``-Werte ab:

- ``disabled`` (Default) oder leerer ``top_fact`` → ``None``, kein
  Provider-Aufruf. Bestehendes Verhalten von ``local_search`` bleibt
  unverändert.
- ``shadow`` → wie zuvor: ``RuleProvider`` mit der deterministischen
  Schwellenwertregel läuft parallel, das Ergebnis wird nur telemetriert
  (``shadow=True``), nie verwendet. Kein LLM- oder Jev-Aufruf, State
  enthält nur ``top_score`` — kein Klartext.
- ``authoritative`` → Jev (TypeSafe) ist Primärprovider, ``RuleProvider``
  ist Rückfall bei jeder Jev-Ausnahme oder wenn kein Jev-Provider verfügbar
  ist (kein API-Key gebunden oder nach einem Auth-Fehler temporär
  gesperrt). Scheitert auch der Rückfall, ist das Ergebnis ``None``.

Wirft nie: ein Fehler in diesem Modul darf ``local_search`` nie zum Absturz
bringen. Die bestehende Keyword-Sortierung und der Rückgabewert von
``local_search`` bleiben unverändert — der Aufrufer verwirft das Ergebnis
dieses Moduls aktuell (Wirkung auf die Suche folgt in einer eigenen Slice,
siehe ``graph_reader.py::local_search``).

Datenschutz (authoritative-Modus): Maintainer-Freigabe 30.09.2026
(Alexander Schneider): Query und Top-Fakt von ``local-search-relevance``
dürfen im Klartext an TypeSafe (Jev) gesendet werden; gilt für den
authoritative-Modus mit Rule-Rückfall. Der shadow-Modus sendet weiterhin
nur ``top_score`` (kein Klartext), siehe :func:`_resolve_shadow`.

Provider-Austauschbarkeit bleibt erhalten: jeder ``DecisionProvider``
(Rule/LLM/Fake/Jev) erfüllt denselben Aufruf über die injizierbaren
``jev``-/``rule``-Parameter von :func:`resolve_relevance`.
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Optional

from typesafe_sdk import RetryPolicy, TypeSafeAuthenticationError

from app.contracts.decision_contract import (
    DecisionQuestion,
    DecisionResult,
    DecisionState,
    NoulQuestion,
)
from app.repositories.decision_provider import DecisionProvider, decision_layer_mode
from app.services.decisions.jev_provider import (
    JevDecisionProvider,
    build_jev_client,
    resolve_jev_api_key,
)
from app.services.decisions.rule_provider import RuleOutcome, RuleProvider
from app.utils.logger import get_logger

logger = get_logger("agora.decisions.local_search_relevance")

_USE_CASE_ID = "local-search-relevance"

#: ``local_search`` vergibt 100 für einen exakten Query-Treffer, 10 je
#: getroffenes Keyword (``graph_reader.py::match_score``) — 10 heißt:
#: mindestens ein Keyword hat getroffen.
_RELEVANCE_THRESHOLD = 10

#: Geteilt mit den Jev-Skripten (``scripts/jev_benchmark_local_search.py``,
#: ``scripts/jev_rollout_probe.py``), damit Benchmark, Probe und der
#: produktive authoritative-Pfad Jev exakt dieselbe Aussage zur Bewertung
#: vorlegen.
RELEVANCE_ASSERTION = "Der Fakt ist für die Suchanfrage relevant."

#: Der authoritative-Pfad darf das Timeout-Budget eines Aufrufs nicht
#: vervielfachen (siehe ``_jev_provider`` unten) — höchstens ein
#: zusätzlicher Versuch neben dem ersten.
_JEV_MAX_RETRIES = 1

#: Nach einem Auth-Fehler bleibt der Jev-Provider gesperrt, statt bei jedem
#: Aufruf erneut gegen eine erkennbar falsche/abgelaufene Anmeldung zu
#: laufen (unnötige Latenz und Fehlerlog-Rauschen auf dem heißen Pfad).
_AUTH_BLOCK_SECONDS = 300.0

_jev_lock = threading.Lock()
_jev_cache: Optional[JevDecisionProvider] = None
_jev_blocked_until: Optional[float] = None
_jev_warned_no_key = False


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
    den Klartext (ADR-0016, Abschnitt Security).

    ``surrogatepass``: eine Query aus JSON kann einen einzelnen Surrogat
    (``"\\ud800"``) enthalten, den striktes UTF-8 ablehnt. Für jede gültige
    Eingabe ist der Hash byte-gleich zu ``.encode()``."""
    return hashlib.sha256(f"{query}\n{fact}".encode("utf-8", "surrogatepass")).hexdigest()[:16]


def _reset_jev_cache_for_tests() -> None:
    """Setzt Cache, Sperre und Warn-Flag zurück. Nur für Tests — der
    Produktionscode ruft das nie auf."""
    global _jev_cache, _jev_blocked_until, _jev_warned_no_key
    with _jev_lock:
        _jev_cache = None
        _jev_blocked_until = None
        _jev_warned_no_key = False


def _lock_jev_after_auth_failure() -> None:
    """Leert den Cache und sperrt neue Jev-Aufrufe für ``_AUTH_BLOCK_SECONDS``."""
    global _jev_cache, _jev_blocked_until
    with _jev_lock:
        _jev_cache = None
        _jev_blocked_until = time.monotonic() + _AUTH_BLOCK_SECONDS


def _jev_provider() -> tuple[Optional[JevDecisionProvider], Optional[str]]:
    """Liefert den (gecachten) Jev-Provider, oder ``(None, Grund)`` wenn
    keiner verfügbar ist — ``"no_key"`` (kein API-Key im Secret-Store) oder
    ``"auth_blocked"`` (Sperre nach einem vorherigen Auth-Fehler noch aktiv).

    Thread-sicher: mehrere gleichzeitige ``local_search``-Aufrufe teilen
    sich denselben Client statt je einen eigenen aufzubauen.
    """
    global _jev_cache, _jev_blocked_until, _jev_warned_no_key
    from app.config import Config

    with _jev_lock:
        now = time.monotonic()
        if _jev_blocked_until is not None:
            if now < _jev_blocked_until:
                return None, "auth_blocked"
            _jev_blocked_until = None
        if _jev_cache is not None:
            return _jev_cache, None
        if not resolve_jev_api_key():
            if not _jev_warned_no_key:
                logger.warning(
                    "decision_layer_authoritative: kein Jev-API-Key gebunden, "
                    "use_case=%s faellt auf RuleProvider zurueck.",
                    _USE_CASE_ID,
                )
                _jev_warned_no_key = True
            return None, "no_key"
        # Höchstens ein zusätzlicher Versuch (siehe ``_JEV_MAX_RETRIES``):
        # der SDK-Default (``RetryPolicy(max_retries=2, ...)``) würde das
        # Timeout-Budget dieses heißen Pfads bis zu verdreifachen. Das
        # innere Retry-``timeout`` wird auf dasselbe Budget wie der
        # Client-Timeout gesetzt, statt auf dem SDK-Default (30s) zu
        # bleiben, der sonst ein größeres Gesamtbudget vorgäbe, als der
        # Aufrufer tatsächlich zu warten bereit ist.
        retry = RetryPolicy(max_retries=_JEV_MAX_RETRIES, timeout=Config.JEV_TIMEOUT_S)
        client = build_jev_client(timeout=Config.JEV_TIMEOUT_S, retry=retry)
        _jev_cache = JevDecisionProvider(client)
        return _jev_cache, None


def _log_authoritative(
    *,
    provider: str,
    probability_yes: Optional[float],
    latency_ms: int,
    cost_micros: Optional[int],
    fallback_chain: list[str],
    fallback_reason: Optional[str],
    context_hash: str,
) -> None:
    logger.info(
        "decision_layer_authoritative use_case=%s mode=authoritative provider=%s "
        "probability_yes=%s latency_ms=%d cost_micros=%s fallback_chain=%s "
        "fallback_reason=%s context_hash=%s",
        _USE_CASE_ID,
        provider,
        probability_yes,
        latency_ms,
        cost_micros,
        fallback_chain,
        fallback_reason,
        context_hash,
    )


def _resolve_shadow(
    query: str,
    top_fact: str,
    top_score: int,
    *,
    rule: Optional[DecisionProvider],
) -> Optional[DecisionResult]:
    """Heutiges Shadow-Verhalten: nur ``RuleProvider``, Ergebnis wird
    telemetriert (``shadow=True``), nie verwendet. Wirft nie."""
    try:
        state = DecisionState(
            use_case_id=_USE_CASE_ID,
            state={"top_score": top_score},
            context_hash=_context_hash(query, top_fact),
        )
        active_provider = rule or RuleProvider(use_case_id=_USE_CASE_ID, rule_fn=_relevance_rule)
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
        return shadow_result
    except Exception:  # noqa: BLE001 - Shadow-Fehler duerfen die Suche nie stoeren
        # ``logger.exception`` hängt den Traceback an, und der enthält die
        # Message der Ausnahme. Die Adapter dieses Projekts halten ihre
        # Fehlermeldungen deshalb payload-frei (``_shape``/``_bounded`` in
        # ``jev_provider``/``llm_provider``). Im shadow-Pfad läuft nur
        # ``RuleProvider`` (reiner Python-Code, kein externes SDK) — für den
        # authoritative-Pfad mit Jev gilt das NICHT automatisch, siehe
        # ``_resolve_authoritative`` unten.
        logger.exception("decision_layer_shadow failed for use_case=%s", _USE_CASE_ID)
        return None


def _resolve_authoritative(
    query: str,
    top_fact: str,
    top_score: int,
    *,
    jev: Optional[DecisionProvider],
    rule: Optional[DecisionProvider],
) -> Optional[DecisionResult]:
    """Jev ist Primärprovider, ``RuleProvider`` ist Rückfall bei jeder
    Jev-Ausnahme oder fehlender Verfügbarkeit (kein Key / gesperrt)."""
    context_hash = _context_hash(query, top_fact)
    fallback_reason: Optional[str] = None

    active_jev = jev
    if active_jev is None:
        try:
            active_jev, fallback_reason = _jev_provider()
        except Exception as exc:  # noqa: BLE001 - Key-Store/Client-Bau-Fehler -> Rule
            # Kein Cache-Eintrag entsteht; der nächste Aufruf versucht es neu.
            active_jev, fallback_reason = None, f"provider_unavailable({type(exc).__name__})"

    if active_jev is not None:
        jev_state = DecisionState(
            use_case_id=_USE_CASE_ID,
            state={"assertion": RELEVANCE_ASSERTION, "query": query, "fact": top_fact},
            context_hash=context_hash,
        )
        try:
            result = active_jev.decide(jev_state, NoulQuestion())
        except Exception as exc:  # noqa: BLE001 - kontrollierter Rueckfall auf Rule
            # NIEMALS str(exc)/repr(exc)/logger.exception/exc_info hier: eine
            # SDK-Ausnahme kann die gesendete Anfrage (Query/Fakt) spiegeln.
            # Nur der Exception-Klassenname (+ Request-ID, falls vorhanden)
            # ist sicher zu loggen.
            if isinstance(exc, TypeSafeAuthenticationError):
                _lock_jev_after_auth_failure()
            reason = type(exc).__name__
            request_id = getattr(exc, "request_id", None)
            if request_id is not None:
                reason = f"{reason}(request_id={request_id})"
            fallback_reason = reason
            active_jev = None
        else:
            final = result.model_copy(update={"shadow": False, "fallback_chain": ["jev"]})
            _log_authoritative(
                provider=final.provider,
                probability_yes=final.probability_yes,
                latency_ms=final.latency_ms,
                cost_micros=final.cost_micros,
                fallback_chain=final.fallback_chain,
                fallback_reason=None,
                context_hash=context_hash,
            )
            return final

    # Rückfall auf Rule — entweder weil kein Jev-Provider verfügbar war
    # (no_key/auth_blocked) oder weil der Jev-Aufruf oben geworfen hat.
    rule_state = DecisionState(
        use_case_id=_USE_CASE_ID,
        state={"top_score": top_score},
        context_hash=context_hash,
    )
    active_rule = rule or RuleProvider(use_case_id=_USE_CASE_ID, rule_fn=_relevance_rule)
    try:
        rule_result = active_rule.decide(rule_state, NoulQuestion())
    except Exception as exc:  # noqa: BLE001 - auch der Rueckfall darf local_search nie stoeren
        logger.error(
            "decision_layer_authoritative use_case=%s rule_fallback_failed=%s "
            "jev_fallback_reason=%s",
            _USE_CASE_ID,
            type(exc).__name__,
            fallback_reason,
        )
        return None

    final = rule_result.model_copy(update={"shadow": False, "fallback_chain": ["jev", "rule"]})
    _log_authoritative(
        provider=final.provider,
        probability_yes=final.probability_yes,
        latency_ms=final.latency_ms,
        cost_micros=final.cost_micros,
        fallback_chain=final.fallback_chain,
        fallback_reason=fallback_reason,
        context_hash=context_hash,
    )
    return final


def resolve_relevance(
    query: str,
    top_fact: Optional[str],
    top_score: int,
    *,
    jev: Optional[DecisionProvider] = None,
    rule: Optional[DecisionProvider] = None,
) -> Optional[DecisionResult]:
    """Trifft GENAU EINE Relevanz-Entscheidung über das bestbewertete
    ``local_search``-Ergebnis, abhängig von ``AGORA_DECISION_LAYER_MODE``
    (siehe Moduldocstring für die drei Modi). Default ``disabled`` — dann
    tut diese Funktion nichts.

    Wirft nie: ein Fehler in der Decision Layer darf die eigentliche Suche
    nicht beeinflussen. ``jev``/``rule`` sind injizierbar für Tests; ohne
    Injektion baut der authoritative-Pfad seinen Jev-Provider selbst (siehe
    :func:`_jev_provider`), der shadow-Pfad seinen ``RuleProvider``.
    """
    mode = decision_layer_mode(_USE_CASE_ID)
    if mode == "disabled" or not top_fact:
        return None
    if mode == "shadow":
        return _resolve_shadow(query, top_fact, top_score, rule=rule)
    if mode == "authoritative":
        # Äußerer Schutz für alles, was ``_resolve_authoritative`` außerhalb
        # seiner eigenen try-Blöcke tut: Key-Store-Zugriff und Client-Bau in
        # ``_jev_provider`` (``get_bound_store_api_key`` fängt nur
        # ``RuntimeError``), ``_context_hash``, ``DecisionState``-Validierung.
        # Ohne ihn bräche ein Key-Store-Fehler ``local_search`` ab. Nur der
        # Klassenname wird geloggt — keine Message, kein Traceback, weil
        # beides Query/Fakt spiegeln kann.
        try:
            return _resolve_authoritative(query, top_fact, top_score, jev=jev, rule=rule)
        except Exception as exc:  # noqa: BLE001 - darf local_search nie stoeren
            logger.error(
                "decision_layer_authoritative use_case=%s unexpected_error=%s",
                _USE_CASE_ID,
                type(exc).__name__,
            )
            return None
    return None


__all__ = ["resolve_relevance", "RELEVANCE_ASSERTION"]
