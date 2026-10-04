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
ConfidenceScope = Literal[
    "simulation_consensus", "simulation_single_voice", "evidence", "empirical"
]

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


def _normalised(value: Any) -> str:
    """Vergleichsform eines Namens: Whitespace-Kollaps und casefold."""
    return " ".join(str(value or "").split()).casefold()


def _voice_key(item: Mapping[str, Any], record: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Identitaet der Stimme hinter einem stuetzenden Item, oder ``None``.

    Eine Stimme ist eine Persona, nicht ein Evidence-Item: Zwei Fragen an
    dieselbe Persona erzeugen zwei ``evidence_id`` und bleiben eine Stimme.
    Stabil ist der ``agent_name`` — er steht im ``raw``-Teil des Index-Records
    (``AgentInterview.to_dict()``), bei Items direkt am Item. Aeltere Records
    ohne Namen fallen auf ``persona_stakeholder_group`` zurueck; das ist die
    Rolle der Persona und damit nie feiner als die Persona selbst.

    ``None`` heisst: nicht ermittelbar. Der Aufrufer zaehlt das konservativ.
    """
    sources = [s for s in (item, record) if isinstance(s, Mapping)]
    for source in sources:
        name = _normalised(source.get("agent_name"))
        if not name:
            raw = source.get("raw")
            name = _normalised(raw.get("agent_name")) if isinstance(raw, Mapping) else ""
        if name:
            return f"agent:{name}"
    for source in sources:
        group = _normalised(source.get("persona_stakeholder_group"))
        if group:
            return f"group:{group}"
    return None


def count_supporting_voices(
    evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> int:
    """Anzahl verschiedener Stimmen unter den stuetzenden Items (#1766).

    Nicht ermittelbare Identitaeten bilden zusammen hoechstens *eine* Stimme
    und erhoehen die Zahl nie, sobald eine Stimme bekannt ist: Ein Item ohne
    erkennbare Persona kann dieselbe Person sein wie ein anderes. Im Zweifel
    die kleinere Zahl — nie ungeprueft Uebereinstimmung behaupten.
    """
    if not isinstance(evidence, list):
        return 0
    index = evidence_index or {}
    resolved: set[str] = set()
    unresolved = False
    for item in evidence:
        if not isinstance(item, dict) or item.get("supports_claim") is not True:
            continue
        record = index.get(str(item.get("evidence_id") or ""))
        key = _voice_key(item, record if isinstance(record, Mapping) else None)
        if key is None:
            unresolved = True
        else:
            resolved.add(key)
    if resolved:
        return len(resolved)
    return 1 if unresolved else 0


def derive_confidence_scope(
    evidence: Any,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> ConfidenceScope:
    """Leitet den Geltungsbereich aus den stuetzenden Evidence-Items ab.

    ``empirical`` wird hier nie vergeben: der Wert bezeichnet reale empirische
    Daten, die Agora nicht erhebt.

    Ohne quellengebundene Evidence entscheidet die Zahl der Stimmen
    (#1766): ``simulation_consensus`` verlangt mindestens zwei verschiedene
    Personas. Stuetzt genau eine, ist das eine Einzelstimme und kein Konsens.
    Stuetzt keine (leere oder nur nicht-stuetzende Evidence), bleibt es beim
    bisherigen Rueckfallwert ``simulation_consensus`` — der Claim ist dann ein
    ``datenluecke``-Fall, dessen Scope der Vertrag ohnehin nicht als
    quellengebunden zulaesst.
    """
    kinds = supporting_source_kinds(evidence, evidence_index)
    if any(kind in EVIDENCE_BOUND_SOURCE_KINDS for kind in kinds):
        return "evidence"
    if kinds and count_supporting_voices(evidence, evidence_index) < 2:
        return "simulation_single_voice"
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
    "count_supporting_voices",
    "derive_aggregation_basis",
    "derive_confidence_scope",
    "supporting_source_kinds",
]
