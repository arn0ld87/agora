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

from .claim_qualification import (
    EVIDENCE_BOUND_SOURCE_KINDS,
    AggregationBasis,
    ConfidenceScope,
    _BASIS_FOR_DOMINANT_KIND,
    _extract_doc_from_anchor,
    _extract_voice_identity_parts,
    _looks_like_technical_id,
    _normalised,
    _parse_voice_key_token,
    _seed_doc_key_from_mapping as _seed_doc_key,
    count_supporting_voices,
    derive_aggregation_basis,
    derive_confidence_scope,
    is_qualifying_support as _is_qualifying_support,
    resolve_canonical_voice_keys,
    resolve_document_anchor,
    resolve_independent_source_keys,
    resolve_voice_key,
    supporting_source_kinds,
)

_voice_key = resolve_voice_key


__all__ = [
    "EVIDENCE_BOUND_SOURCE_KINDS",
    "AggregationBasis",
    "ConfidenceScope",
    "_BASIS_FOR_DOMINANT_KIND",
    "_extract_doc_from_anchor",
    "_extract_voice_identity_parts",
    "_is_qualifying_support",
    "_looks_like_technical_id",
    "_normalised",
    "_parse_voice_key_token",
    "_seed_doc_key",
    "_voice_key",
    "count_supporting_voices",
    "derive_aggregation_basis",
    "derive_confidence_scope",
    "resolve_canonical_voice_keys",
    "resolve_document_anchor",
    "resolve_independent_source_keys",
    "resolve_voice_key",
    "supporting_source_kinds",
]
