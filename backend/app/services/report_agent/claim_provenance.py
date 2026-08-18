"""Herkunft eines Claims aus seinen stuetzenden Evidence-Items (#1358).

Im Referenzlauf trugen **alle sechzehn** Claims ``aggregation_basis="persona"``
und ``confidence_scope="simulation_consensus"`` — waehrend ihre
``evidence_refs`` auf 22 ``seed_corpus``- und 2 ``agent_action``-Items
aufloesten. Fuenfzehn davon waren quellengebunden und wurden als
Simulationskonsens ausgewiesen. Das ist keine Ungenauigkeit, sondern eine
falsche Herkunftsangabe: Der Leser erfaehrt, ein Befund beruhe auf der
Meinung simulierter Personas, obwohl er aus dem Seed-Dokument stammt.

Zwei Ursachen, beide hier behoben:

1. Die Evidence-Dicts *am Claim* tragen nur die Bindungsdaten
   (``evidence_id``, ``match_score``, ``entailment`` …), keine
   ``source_kind``. Die alte Ableitung las das Feld direkt am Item, fand nie
   etwas und fiel still auf den Default zurueck. Sie schlaegt jetzt ueber
   ``evidence_index[evidence_id]`` nach — dort steht der volle Datensatz.
2. ``aggregation_basis`` war der Literalwert ``"persona"``.

**Gezaehlt wird nur ``supports_claim is True``** — dieselbe Menge, aus der
``evidence_refs`` entsteht. Widersprechende oder nur thematisch verwandte
Items begruenden keine Herkunft.

Zur Abbildung der Quellengattung auf ``aggregation_basis``: Eine einfache
Mehrheit genuegt nicht, eine *strikte* wird verlangt (mehr als die Haelfte).
Bei zwei Seed- und zwei Zitat-Items traegt keine der beiden Gattungen den
Claim allein — das ist ein ``aggregat``, und genau das soll dastehen.

``graph_relation`` und ``web_source`` fuehren bewusst **nicht** auf ``seed``,
obwohl eine Graph-Relation aus dem Seed-Korpus stammt: Der Knoten verdichtet
viele Erwaehnungen zu einer Kante, ist also selbst schon eine Aggregation.
Ihn als Dokumentfakt auszuweisen wuerde einen Verarbeitungsschritt
unterschlagen.

Items ohne aufloesbare Quellengattung zaehlen in die Grundgesamtheit, aber in
keine Gattung. Sie koennen eine Mehrheit also nur verhindern, nie begruenden.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal, Mapping, Optional

AggregationBasis = Literal["seed", "persona", "aggregat", "datenluecke"]
ConfidenceScope = Literal["simulation_consensus", "evidence", "empirical"]

#: Quellengattungen, die den Claim an etwas ausserhalb der Simulation binden.
#: ``agent_quote`` und ``agent_action`` fehlen hier bewusst: beides sind
#: Aeusserungen bzw. Handlungen simulierter Agenten. Ein Claim, den nur sie
#: stuetzen, ist Simulationskonsens — unabhaengig von seinem Label.
EVIDENCE_BOUND_SOURCE_KINDS = frozenset({"seed_corpus", "graph_relation", "web_source"})

#: Nur diese beiden Gattungen tragen eine eigene Herkunftsangabe. Alles
#: andere — Graph-Relation, Web-Treffer, Agentenhandlung, Inferenz — ist im
#: Sinne des Vertrags Mischtraegerschaft.
_BASIS_FOR_DOMINANT_KIND: Mapping[str, AggregationBasis] = {
    "seed_corpus": "seed",
    "agent_quote": "persona",
}


def supporting_source_kinds(
    evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> list[str]:
    """Quellengattungen der stuetzenden Items, in Reihenfolge des Auftretens.

    Nicht aufloesbare Gattungen erscheinen als ``""`` — sie zaehlen in die
    Grundgesamtheit, begruenden aber keine Mehrheit.
    """
    if not isinstance(evidence, list):
        return []
    index = evidence_index or {}
    kinds: list[str] = []
    for item in evidence:
        if not isinstance(item, dict) or item.get("supports_claim") is not True:
            continue
        kind = str(item.get("source_kind") or "").strip()
        if not kind:
            record = index.get(str(item.get("evidence_id") or ""))
            if isinstance(record, Mapping):
                kind = str(record.get("source_kind") or "").strip()
        kinds.append(kind)
    return kinds


def derive_confidence_scope(
    evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> ConfidenceScope:
    """Leitet den Geltungsbereich aus den stuetzenden Evidence-Items ab.

    ``empirical`` wird hier nie vergeben: der Wert bezeichnet reale empirische
    Daten, die Agora nicht erhebt. Die Ableitung kennt daher nur die beiden
    Faelle, die im Lauf tatsaechlich vorkommen.
    """
    kinds = supporting_source_kinds(evidence, evidence_index)
    if any(kind in EVIDENCE_BOUND_SOURCE_KINDS for kind in kinds):
        return "evidence"
    return "simulation_consensus"


def derive_aggregation_basis(
    evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> AggregationBasis:
    """Leitet die Traegerschaft aus der dominanten Quellengattung ab.

    ``datenluecke`` heisst: kein einziges stuetzendes Item. Das ist keine
    schwache Herkunft, sondern gar keine — und der Vertrag verlangt dann eine
    leere ``evidence_refs``-Liste.
    """
    kinds = supporting_source_kinds(evidence, evidence_index)
    if not kinds:
        return "datenluecke"
    dominant, count = Counter(kinds).most_common(1)[0]
    if count * 2 <= len(kinds):
        return "aggregat"
    return _BASIS_FOR_DOMINANT_KIND.get(dominant, "aggregat")


__all__ = [
    "EVIDENCE_BOUND_SOURCE_KINDS",
    "AggregationBasis",
    "ConfidenceScope",
    "derive_aggregation_basis",
    "derive_confidence_scope",
    "supporting_source_kinds",
]
