"""S6 — formelbasierte Confidence-Berechnung für Report-Claims.

Vorher: ``confidence_score = min(0.95, 0.25 + support_count * 0.12)`` —
quasi linear in der Anzahl der Evidence-Items, ohne Qualitätsbewertung.
Folge: jeder Claim mit 6+ Items wurde 0.95 (Label "high"), egal wie
relevant die Evidence inhaltlich war. Reviewer hatte das als
unkalibriert markiert.

Neue Formel (Reviewer-Empfehlung, leicht abgeschwächt):

    score = 0.40 * relevance
          + 0.25 * source_quality
          + 0.20 * specificity
          + 0.15 * consistency
          - contradiction_penalty

Komponenten kapitulieren bei 1.0; Penalty ist heute fix 0 (kein
Contradiction-Detector live), bleibt aber als Hook erhalten.

Labels:

* 0.00 – 0.44 → ``speculative``
* 0.45 – 0.64 → ``low``
* 0.65 – 0.84 → ``medium``
* 0.85 – 0.89 → ``high``
* 0.90 – 1.00 → ``verified`` (nur wenn mindestens ein Evidence-Item
  einen ``match_score >= 0.85`` trägt UND mindestens 2 unabhängige
  Quellen vorliegen — sonst gedeckelt auf 0.89 → ``high``)
* Zusätzlich: wenn alle match_scores < 0.55 → Deckel auf 0.64 (low/medium-Grenze)

MAI-14: Contradiction-Penalty.

Wenn Evidence-Items derselben Claim auseinandergehende Sentiments tragen,
ist die Behauptung weniger belastbar. Konkret:
- Wenn std(sentiment_scores) > 0.6 → Penalty -0.2.
- Wenn min < -0.3 und max > +0.3 → Penalty -0.2 (gemischter Tenor).

Die Heuristik greift in compute_confidence automatisch, sobald mindestens
2 Evidence-Items ein sentiment_score-Feld tragen. Die Penalty wird
zusätzlich zum extern übergebenen contradiction_penalty aufaddiert.
compute_claim_confidence() ist die erweiterte Variante für Aufrufer,
die applied_penalties auswerten wollen.
"""

from __future__ import annotations

import statistics
from typing import Dict, List, Tuple

# MAI-14: Schwellwerte für Sentiment-Contradiction-Heuristik.
_CONTRADICTION_PENALTY_AMOUNT: float = 0.2
_CONTRADICTION_STD_THRESHOLD: float = 0.6
_CONTRADICTION_RANGE_LOW: float = -0.3
_CONTRADICTION_RANGE_HIGH: float = 0.3

#: Auffangtypen zaehlen nicht als Rollenfamilie (Issue #1248). Spiegelt
#: ``report_contract._GENERIC_ENTITY_TYPES`` — der Konsenswert muss dieselbe
#: Vorstellung von "Gruppe" haben wie der Validator, der darueber entscheidet.
_GENERIC_ENTITY_TYPES: frozenset[str] = frozenset(
    {"person", "organization", "entity", "node", "unknown", "other"}
)


def _has_contradiction(sentiment_scores: List[float]) -> bool:
    """Erkennt widersprüchliche Sentiment-Vektoren in einem Evidence-Set.

    Zwei Kriterien (OR-verknüpft):
    1. Populationsstandardabweichung > 0.6 — hohe Streuung.
    2. Minimum < -0.3 UND Maximum > +0.3 — gemischter Tenor.

    Mindestens 2 Scores nötig; 1 Score kann nicht widersprüchlich sein.
    """
    if len(sentiment_scores) < 2:
        return False
    stddev = statistics.pstdev(sentiment_scores)
    if stddev > _CONTRADICTION_STD_THRESHOLD:
        return True
    low = min(sentiment_scores)
    high = max(sentiment_scores)
    if low < _CONTRADICTION_RANGE_LOW and high > _CONTRADICTION_RANGE_HIGH:
        return True
    return False


def _extract_sentiment_scores(evidence: List[Dict]) -> List[float]:
    """Extrahiert valide sentiment_score-Werte aus einer Evidence-Liste."""
    result: List[float] = []
    for e in evidence:
        val = e.get("sentiment_score")
        # Issue #1277-7(4): ``bool`` erbt von ``int`` — ``isinstance(True,
        # (int, float))`` ist True, wodurch boolesche Sentinel-Werte als
        # numerische Sentiment-Scores durchrutschten und eine Schein-Penalty
        # auslösen konnten. Boolesche Werte sind keine Sentiments.
        if val is not None and isinstance(val, (int, float)) and not isinstance(val, bool):
            result.append(float(val))
    return result


# S6: Source-Quality-Gewichtung. Bewusst grob — der Audit-Trail wird
# in S5 ohnehin getrennt und fließt hier nicht ein.
_SOURCE_WEIGHTS: Dict[str, float] = {
    "graph_fact": 1.0,
    "graph_metric": 0.85,
    "graph_metric_status": 0.5,
    "relationship_chain": 0.95,
    "entity_summary": 0.85,
    "agent_action": 0.7,
    "agent_behavior": 0.75,
    "section_synthesis": 0.0,
    "model_generated_inference": 0.0,
}


def _component_relevance(evidence: List[Dict]) -> float:
    """Mittelwert der `match_score`-Felder; ohne Scores Konservativ-Default."""
    scores = [float(e.get("match_score") or 0.0) for e in evidence if "match_score" in e]
    if scores:
        return min(1.0, sum(scores) / len(scores))
    if not evidence:
        return 0.0
    return 0.5


def _component_source_quality(evidence: List[Dict]) -> float:
    if not evidence:
        return 0.0
    weights = [_SOURCE_WEIGHTS.get(str(e.get("type") or ""), 0.6) for e in evidence]
    return min(1.0, sum(weights) / len(weights))


def _component_specificity(evidence: List[Dict]) -> float:
    """Top-Match-Score → Spezifität. Ohne Scores: 0.5 (mid)."""
    scores = [float(e.get("match_score") or 0.0) for e in evidence if "match_score" in e]
    if not scores:
        return 0.5 if evidence else 0.0
    top = max(scores)
    if top >= 0.85:
        return 1.0
    if top >= 0.7:
        return 0.8
    if top >= 0.55:
        return 0.6
    return 0.4


def _component_consistency(evidence: List[Dict]) -> float:
    """Wieviele unabhängige Quellen? Mehr = robuster gegen Einzelfehler."""
    sources = {(e.get("type"), e.get("source")) for e in evidence}
    if len(sources) >= 3:
        return 1.0
    if len(sources) == 2:
        return 0.8
    if len(sources) == 1:
        return 0.6
    return 0.0


def _apply_single_source_cap(
    score: float, *, unique_sources: int, has_strong_match: bool
) -> float:
    """Deckelt Ein-Quellen-Claims auf höchstens ``low`` — außer bei starkem Match.

    ``has_strong_match`` verwendet dieselbe 0.85-Schwelle wie die Verified-
    Schranke in ``_compute_confidence_with_penalties``. Contradiction-
    Penaltys können den Score danach noch weiter auf ``speculative`` senken;
    der Claim selbst bleibt in jedem Fall sichtbar.

    #1301: der vorher bedingungslose Deckel war ein Attraktor, kein
    Grenzfall-Schutz — er zog auch sehr gut belegte Ein-Quellen-Fakten
    (match_score > 0.9) unter die medium-Schwelle (0.65) und ließ praktisch
    alle Ein-Quellen-Claims exakt bei 0.59 konvergieren, egal wie viel besser
    die Evidence war. Ab ``has_strong_match`` greift der Deckel nicht mehr;
    die Verified-Schranke (:277-279) bleibt trotzdem der harte Riegel — ein
    Ein-Quellen-Claim erreicht dadurch höchstens 0.89 ("high"), nie
    "verified" (das verlangt weiterhin >= 2 unabhängige Quellen).
    """
    if unique_sources < 2 and not has_strong_match:
        return min(score, 0.59)
    return score


def partition_by_entailment(evidence: List[Dict]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Teilt Evidence in (stützend, widersprechend, nur verwandt).

    Items ohne ``entailment``-Feld stammen aus der Zeit vor der zweiten
    Binding-Stufe und gelten weiterhin als stützend — sonst würden alte
    Reports beim Neuberechnen ihre gesamte Confidence verlieren.
    """
    supporting: List[Dict] = []
    contradicting: List[Dict] = []
    related: List[Dict] = []
    for item in evidence:
        verdict = str(item.get("entailment") or "").upper()
        if verdict == "CONTRADICTED" or item.get("contradicts_claim") is True:
            contradicting.append(item)
        elif verdict in {"RELATED_ONLY", "INSUFFICIENT"}:
            related.append(item)
        elif verdict == "SUPPORTED" or item.get("supports_claim") is not False:
            supporting.append(item)
        else:
            related.append(item)
    return supporting, contradicting, related


def _compute_confidence_with_penalties(
    evidence: List[Dict],
    *,
    contradiction_penalty: float = 0.0,
) -> Tuple[float, str, List[str]]:
    """Authoritative Stelle für Score, Label und Audit-Trail.

    Issue #1277-7: ``compute_confidence`` und ``compute_claim_confidence``
    müssen denselben Penalty-Satz beschreiben. Bisher extrahierte
    ``compute_claim_confidence`` Sentiment-Scores über die *gesamte* Evidence
    (inkl. widersprechender und nur verwandter Items), während der Score in
    ``compute_confidence`` nur über die stützende Teilmenge lief — der
    Audit-Trail konnte Penalties aufführen, die der Score gar nicht abbildete,
    und umgekehrt fehlte die Entailment-Penalty im Audit. Beide Wrapper leiten
    jetzt hieraus ab, sodass Score und Audit-Trail dieselbe Penalty-Menge
    tragen.
    """
    applied_penalties: List[str] = []

    if not evidence:
        return 0.15, "speculative", applied_penalties

    supporting, contradicting, _related = partition_by_entailment(evidence)
    if not supporting:
        # Kein einziger Beleg — thematische Nähe allein trägt keinen Claim.
        return 0.15, "speculative", applied_penalties
    extra_entailment_penalty = 0.0
    if contradicting:
        extra_entailment_penalty = _CONTRADICTION_PENALTY_AMOUNT * min(len(contradicting), 2)
        applied_penalties.append("entailment_contradiction_penalty")
    effective_contradiction_penalty = contradiction_penalty + extra_entailment_penalty
    evidence = supporting

    relevance = _component_relevance(evidence)
    source_quality = _component_source_quality(evidence)
    specificity = _component_specificity(evidence)
    consistency = _component_consistency(evidence)

    # MAI-14: Sentiment-Contradiction-Penalty auto-berechnen
    sentiments = _extract_sentiment_scores(evidence)
    sentiment_penalty = _CONTRADICTION_PENALTY_AMOUNT if _has_contradiction(sentiments) else 0.0
    if sentiment_penalty:
        applied_penalties.append("contradiction_penalty")

    total_penalty = max(0.0, effective_contradiction_penalty) + sentiment_penalty

    raw = (
        0.40 * relevance
        + 0.25 * source_quality
        + 0.20 * specificity
        + 0.15 * consistency
        - total_penalty
    )
    score = max(0.0, min(1.0, raw))

    has_strong_match = any(
        float(e.get("match_score") or 0.0) >= 0.85
        for e in evidence
        if "match_score" in e
    )
    unique_sources = len({(e.get("type"), e.get("source")) for e in evidence})

    score = _apply_single_source_cap(
        score, unique_sources=unique_sources, has_strong_match=has_strong_match
    )

    # Task 08: Medium-Cap — kein Claim darf "high" sein, wenn alle
    # match_scores unter 0.55 liegen.
    match_scores = [
        float(e.get("match_score") or 0.0)
        for e in evidence
        if "match_score" in e
    ]
    all_weak_matches = match_scores and max(match_scores) < 0.55
    if all_weak_matches:
        score = min(score, 0.64)

    # Task 08: verified nur bei starkem Match UND mind. 2 unabhängigen Quellen.
    if score >= 0.90 and (not has_strong_match or unique_sources < 2):
        score = 0.89

    if score < 0.45:
        label = "speculative"
    elif score < 0.65:
        label = "low"
    elif score < 0.85:
        label = "medium"
    elif score < 0.90:
        label = "high"
    else:
        label = "verified"

    return round(score, 3), label, applied_penalties


def compute_confidence(
    evidence: List[Dict],
    *,
    contradiction_penalty: float = 0.0,
) -> Tuple[float, str]:
    """Liefert (score, label) für eine Evidence-Liste.

    Nur tatsächlich stützende Evidence geht in den Score ein. Thematisch
    verwandte Treffer (``RELATED_ONLY``/``INSUFFICIENT``) erhöhen die
    Confidence nicht — vorher floss ihr Retrieval-``match_score`` mit 40 %
    Gewicht in die Relevanz und machte Ähnlichkeit zu Sicherheit.
    Widersprechende Evidence senkt den Score zusätzlich.

    MAI-14: Wenn sentiment_score-Felder in den Evidence-Items vorhanden sind
    und _has_contradiction() anschlägt, wird automatisch ein Sentiment-
    Contradiction-Penalty von 0.2 aufaddiert (zusätzlich zum extern
    übergebenen contradiction_penalty).
    """
    score, label, _applied = _compute_confidence_with_penalties(
        evidence, contradiction_penalty=contradiction_penalty
    )
    return score, label


def compute_claim_confidence(
    evidence: List[Dict],
    *,
    contradiction_penalty: float = 0.0,
) -> Tuple[float, str, List[str]]:
    """Erweiterte Variante von compute_confidence mit Penalty-Audit-Trail.

    Returns:
        (score, label, applied_penalties)
        score: 0.0–1.0
        label: "speculative" | "low" | "medium" | "high" | "verified"
        applied_penalties: Namen aller angewandten Penalties für Audit.

    Issue #1277-7: Audit-Trail und Score stammen aus derselben Berechnung
    (``_compute_confidence_with_penalties``). Zuvor extrahierte diese Funktion
    Sentiment-Scores über die gesamte Evidence-Menge, während der Score nur
    die stützende Teilmenge sah — der Audit-Trail konnte Penalties nennen, die
    der Score nicht abbildete, und die Entailment-Penalty fehlte im Audit.
    Der tote ``base_score``-Parameter ist entfallen; er wurde nie ausgewertet.
    """
    score, label, applied_penalties = _compute_confidence_with_penalties(
        evidence, contradiction_penalty=contradiction_penalty
    )
    return score, label, applied_penalties


def compute_confidence_breakdown(evidence: List[Dict]) -> Dict[str, float]:
    """Trennt Quellentreue von Simulationskonsens.

    Ein korrekt wiedergegebener Seed-Fakt ist etwas anderes als eine über
    mehrere Stakeholder-Gruppen hinweg konsistente Simulationsreaktion. Beides
    in eine Zahl zu pressen war die Ursache dafür, dass praktisch jeder Claim
    "medium" wurde.

    ``source_fidelity``
        Wie zuverlässig gibt der Claim wieder, was in den Quellen steht.
        Hoch heißt: der Claim ist quellentreu — nicht, dass die Aussage für
        die reale Bevölkerung gilt.
    ``simulation_consensus``
        Wie breit tragen unabhängige simulierte Stakeholder-Gruppen die
        Aussage. Eine einzelne Persona bleibt hier niedrig.
    """
    supporting, contradicting, related = partition_by_entailment(evidence)
    if not supporting:
        return {
            "source_fidelity": 0.0,
            "simulation_consensus": 0.0,
            "supporting_count": 0.0,
            "contradicting_count": float(len(contradicting)),
            "related_only_count": float(len(related)),
        }

    seed_items = [e for e in supporting if str(e.get("source_kind")) == "seed_corpus"]
    quote_items = [e for e in supporting if str(e.get("source_kind")) == "agent_quote"]

    # Quellentreue: getragen von Seed- und Graph-Belegen, gedämpft durch
    # Widersprüche.
    fidelity_base = len(seed_items) / max(1, len(supporting))
    fidelity = min(1.0, 0.5 + 0.5 * fidelity_base)
    if contradicting:
        fidelity = max(0.0, fidelity - 0.25 * min(len(contradicting), 2))

    # Simulationskonsens: Anzahl unterschiedlicher Stakeholder-Gruppen unter
    # den stützenden Agentenzitaten.
    # Issue #1248: dieselbe Zaehlgroesse wie im Cross-Stakeholder-Anker — das
    # Rollenfamilien-Label, ersatzweise der Berufstitel. Sonst haette der
    # Konsenswert eine andere Vorstellung von "Gruppe" als der Validator, der
    # ueber dasselbe Label entscheidet.
    groups: set[str] = set()
    for e in quote_items:
        family = " ".join(str(e.get("persona_role_family") or "").split()).casefold()
        if family and family not in _GENERIC_ENTITY_TYPES:
            groups.add(f"family:{family}")
            continue
        title = " ".join(str(e.get("persona_stakeholder_group") or "").split()).casefold()
        if title:
            groups.add(f"title:{title}")
    if len(groups) >= 3:
        consensus = 1.0
    elif len(groups) == 2:
        consensus = 0.75
    elif len(groups) == 1:
        consensus = 0.4
    else:
        consensus = 0.0

    return {
        "source_fidelity": round(fidelity, 3),
        "simulation_consensus": round(consensus, 3),
        "supporting_count": float(len(supporting)),
        "contradicting_count": float(len(contradicting)),
        "related_only_count": float(len(related)),
        "stakeholder_group_count": float(len(groups)),
    }


_ECHO_CAP_THRESHOLD: float = 0.75
_ECHO_CAP_MAX_SCORE: float = 0.84


def apply_echo_cap(
    score: float,
    label: str,
    echo_index: float,
    is_cross_stakeholder: bool,
) -> tuple[float, str]:
    """Deckelt Cross-Stakeholder-Claim-Scores bei hohem Echo-Chamber-Index.

    Wenn ``echo_index > 0.75`` UND ``is_cross_stakeholder=True``:
    - score wird auf max 0.84 gedeckelt.
    - label ``high`` und ``verified`` werden auf ``medium`` heruntergestuft.

    Ohne Echo-Chamber-Überschreitung oder bei nicht-Cross-Stakeholder-Claims
    wird score/label unverändert zurückgegeben.
    """
    if not is_cross_stakeholder or echo_index <= _ECHO_CAP_THRESHOLD:
        return score, label
    capped_score = min(score, _ECHO_CAP_MAX_SCORE)
    capped_label = label
    if label in ("high", "verified"):
        capped_label = "medium"
    # Issue #1277-3: Der folgende elif-Zweig war tot. Er lief nur, wenn label
    # NICHT in ("high", "verified") ist — dann ist sein zweites Prädikat
    # ``label in ("high", "verified")`` aber immer False. Abgestuft wurde also
    # nie; das ``if`` oben deckt den einzigen realen Fall ab.
    return round(capped_score, 3), capped_label


__all__ = [
    "apply_echo_cap",
    "compute_confidence",
    "compute_confidence_breakdown",
    "compute_claim_confidence",
    "partition_by_entailment",
    "_has_contradiction",
]
