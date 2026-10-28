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
from typing import Any, Literal, Mapping, Optional, Sequence

from ...contracts.report_contract import counts_for_confidence

AggregationBasis = Literal["seed", "persona", "aggregat", "datenluecke"]
ConfidenceScope = Literal[
    "simulation_consensus", "simulation_single_voice", "evidence", "empirical"
]

#: Quellengattungen, die den Claim an etwas ausserhalb der Simulation binden.
#: ``agent_quote`` und ``agent_action`` fehlen hier bewusst: beides sind
#: Aeusserungen bzw. Handlungen simulierter Agenten. Ein Claim, den nur sie
#: stuetzen, ist Simulationskonsens — unabhaengig von seinem Label.
EVIDENCE_BOUND_SOURCE_KINDS = frozenset({
    "seed_corpus",
    "graph_edge",
    "graph_relation",
    "web_source",
})

#: Nur diese beiden Gattungen tragen eine eigene Herkunftsangabe. Alles
#: andere — Graph-Relation, Web-Treffer, Agentenhandlung, Inferenz — ist im
#: Sinne des Vertrags Mischtraegerschaft.
_BASIS_FOR_DOMINANT_KIND: Mapping[str, AggregationBasis] = {
    "seed_corpus": "seed",
    "agent_quote": "persona",
}


def _is_qualifying_support(
    item: Any,
    record: Optional[Mapping[str, Any]],
) -> bool:
    """Ein Beleg stuetzt nur mit ``supports_claim=True`` und ohne manuelle Graph-Herkunft (ADR-0022 §4)."""
    if not isinstance(item, dict) or item.get("supports_claim") is not True:
        return False
    if not counts_for_confidence(item):
        return False
    if isinstance(record, Mapping) and not counts_for_confidence(record):
        return False
    return True


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
        if not isinstance(item, dict):
            continue
        record = index.get(str(item.get("evidence_id") or ""))
        record_map = record if isinstance(record, Mapping) else None
        if not _is_qualifying_support(item, record_map):
            continue
        kind = str(item.get("source_kind") or "").strip()
        if not kind and record_map is not None:
            kind = str(record_map.get("source_kind") or "").strip()
        kinds.append(kind)
    return kinds


def _normalised(value: Any) -> str:
    """Vergleichsform eines Namens: Whitespace-Kollaps und casefold."""
    return " ".join(str(value or "").split()).casefold()


def _looks_like_technical_id(token: str) -> bool:
    """Prueft, ob ein normalisierter Suffix eine technische Agenten-ID ist."""
    if not token:
        return False
    if token.isdigit():
        return True
    for prefix in ("agent_", "id_", "persona_"):
        if token.startswith(prefix) and token[len(prefix) :].isdigit():
            return True
    return False


def _first_source_field(
    sources: Sequence[Mapping[str, Any]],
    field: str,
    *,
    allow_raw: bool = False,
) -> str:
    """Liest den ersten nicht-leeren normalisierten Feldwert aus ``sources``."""
    for source in sources:
        val = _normalised(source.get(field))
        if not val and allow_raw:
            raw = source.get("raw")
            val = _normalised(raw.get(field)) if isinstance(raw, Mapping) else ""
        if val:
            return val
    return ""


def _parse_voice_key_token(
    vk: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Klassifiziert einen normalisierten ``voice_key`` als ``(id_key, name_key, other_vk)``."""
    if ":" not in vk:
        if _looks_like_technical_id(vk):
            return f"agent:{vk}", None, None
        return None, None, f"voice:{vk}"
    prefix, rest = vk.split(":", 1)
    rest = rest.strip()
    if not rest:
        return None, None, None
    if prefix in ("agent_id", "id") or (
        prefix == "agent" and _looks_like_technical_id(rest)
    ):
        return f"agent:{rest}", None, None
    if prefix in ("name", "agent_name", "agent"):
        return None, f"agent:{rest}", None
    return None, None, f"{prefix}:{rest}"


def _extract_voice_identity_parts(
    item: Mapping[str, Any],
    record: Optional[Mapping[str, Any]],
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Zerlegt die Persona-Hinweise aus ``record`` und ``item`` in kanonische Tokens.

    Rueckgabe: ``(id_key, name_key, other_voice_key, group_key)``.
    Technische Agenten-IDs (``agent_id``, ``raw.agent_id`` sowie ``voice_key``
    der Form ``agent:<id>`` / ``agent_id:<id>`` / ``id:<id>``) werden auf das
    kanonische Format ``agent:<id>`` normiert, damit identische Personas ueber
    unterschiedliche Felder denselben Schluessel erhalten.
    """
    sources = [s for s in (record, item) if isinstance(s, Mapping)]
    aid = _first_source_field(sources, "agent_id", allow_raw=True)
    id_key: Optional[str] = f"agent:{aid}" if aid else None
    name_key: Optional[str] = None
    other_vk: Optional[str] = None

    for source in sources:
        vk = _normalised(source.get("voice_key"))
        if not vk:
            continue
        vk_id, vk_name, vk_other = _parse_voice_key_token(vk)
        id_key = id_key or vk_id
        name_key = name_key or vk_name
        other_vk = other_vk or vk_other

    name = _first_source_field(sources, "agent_name", allow_raw=True)
    if name and name_key is None:
        name_key = f"agent:{name}"

    group = _first_source_field(sources, "persona_stakeholder_group")
    group_key: Optional[str] = f"group:{group}" if group else None

    return id_key, name_key, other_vk, group_key


def _voice_key(item: Mapping[str, Any], record: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Identitaet der Stimme hinter einem stuetzenden Item, oder ``None``.

    Eine Stimme ist eine Persona, nicht ein Evidence-Item: Zwei Fragen an
    dieselbe Persona erzeugen zwei ``evidence_id`` und bleiben eine Stimme.
    Reihenfolge (ADR-0002 / Issue #1778):
    1. Technische Agenten-ID (``agent_id``, ``raw.agent_id`` oder numerischer
       ``voice_key``) -> ``agent:<id>``
    2. Expliziter sonstiger ``voice_key`` -> normalisiert
    3. ``agent_name`` / ``raw.agent_name`` (oder Namens-``voice_key``) -> ``agent:<name>``
    4. ``persona_stakeholder_group`` -> ``group:<gruppe>``

    ``None`` heisst: nicht ermittelbar. Der Aufrufer zaehlt das konservativ.
    """
    id_key, name_key, other_vk, group_key = _extract_voice_identity_parts(item, record)
    return id_key or other_vk or name_key or group_key


resolve_voice_key = _voice_key


def resolve_canonical_voice_keys(
    pairs: Sequence[tuple[Mapping[str, Any], Optional[Mapping[str, Any]]]],
) -> list[Optional[str]]:
    """Loest Stimmen-Schluessel ueber eine Folge von ``(item, record)``-Paaren auf.

    Verbindet Mischformate derselben Persona innerhalb eines Claims: Traegt ein
    Beleg sowohl ``agent_id`` (bzw. ``voice_key="agent:<id>"``) als auch
    ``agent_name``, und ein weiterer Beleg derselben Persona nur ``agent_name``
    (ohne eigene ``agent_id``), wird der Namens-Schluessel eindeutig auf den
    kanonischen ``agent:<id>``-Schluessel abgebildet.
    """
    parts_list = [_extract_voice_identity_parts(item, record) for item, record in pairs]
    name_to_ids: dict[str, set[str]] = {}
    for id_key, name_key, _, _ in parts_list:
        if id_key and name_key:
            name_to_ids.setdefault(name_key, set()).add(id_key)

    resolved_keys: list[Optional[str]] = []
    for id_key, name_key, other_vk, group_key in parts_list:
        primary = id_key or other_vk or name_key or group_key
        if (
            primary is not None
            and id_key is None
            and other_vk is None
            and primary == name_key
        ):
            linked_ids = name_to_ids.get(name_key)
            if linked_ids and len(linked_ids) == 1:
                primary = next(iter(linked_ids))
        resolved_keys.append(primary)
    return resolved_keys


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
    qualifying_pairs: list[tuple[Mapping[str, Any], Optional[Mapping[str, Any]]]] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        record = index.get(str(item.get("evidence_id") or ""))
        record_map = record if isinstance(record, Mapping) else None
        if not _is_qualifying_support(item, record_map):
            continue
        qualifying_pairs.append((item, record_map))

    resolved: set[str] = set()
    unresolved = False
    for key in resolve_canonical_voice_keys(qualifying_pairs):
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
    "resolve_canonical_voice_keys",
    "resolve_voice_key",
    "supporting_source_kinds",
]
