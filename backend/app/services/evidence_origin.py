"""Sprungkennungen an Belegen, abgeleitet beim Ausliefern (Issue #1804, Etappe 5).

Ein Beleg soll die Oberfläche zu seinem Ursprung führen: ``agent_action`` zum
Beitrag im Feed, ``entity_summary`` zum Knoten im Wissensgraphen. Die Kennung
steht nicht als eigenes Feld im gespeicherten Beleg, ist aber teilweise in
dessen Inhalt (``raw``, ``producer_key``) enthalten. Dieses Modul leitet sie
daraus ab — ausschließlich im Lesepfad (``GET /api/report/<id>/evidence``). Die
gespeicherten Artefakte und der Schreibpfad des Report-Agenten bleiben
unberührt; deshalb gilt die Ableitung auch für Altberichte.

Regeln:

* Nur eindeutige Kennungen. Keine Näherung über Zeitfenster, Autor oder
  Textvergleich. Ohne belegte Kennung bleibt das Feld ``None``.
* ``agent_action``: nur Aktionen, die einen *eigenen* Beitrag erzeugen, und
  nur mit der Kennung, die das Aktionsprotokoll dafür trägt
  (``CREATE_POST.post_id``, ``QUOTE_POST.new_post_id``, ``REPOST.new_post_id``,
  ``CREATE_COMMENT.comment_id``). ``LIKE_*``, ``FOLLOW``, ``SEARCH_*`` tragen
  zwar die Kennung des *Ziels*, aber der Beleg beschreibt dann eine Reaktion
  und keinen Beitrag — dafür gibt es keinen Ursprungs-Sprung.
* Format wie im Feed (``GET /api/simulation/<id>/feed-snapshot``):
  ``<platform>:<id>`` für Beiträge, ``<platform>:comment:<id>`` für Kommentare.
* ``entity_summary``: die Knoten-UUID aus ``raw.uuid``. Trägt der Beleg
  zusätzlich einen ``producer_key`` der Form ``graph-node:<uuid>``, müssen
  beide übereinstimmen, sonst bleibt das Feld leer.
* ``graph_fact`` und ``relationship_chain`` tragen als ``raw`` nur den
  Faktentext, keine Kanten-UUID; für sie gibt es nichts abzuleiten.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from ..contracts.report_contract import EvidenceMapModel, EvidenceRecordModel

#: Plattformen mit Feed (``<platform>_simulation.db``); gleiche Präfixe wie
#: ``simulation_history._build_feed_snapshot``.
_FEED_PLATFORMS = frozenset({"twitter", "reddit"})

#: Aktionsart → Argument, das die Kennung des *selbst erzeugten* Beitrags trägt.
_OWN_POST_ARG = {
    "CREATE_POST": "post_id",
    "QUOTE_POST": "new_post_id",
    "REPOST": "new_post_id",
}
_OWN_COMMENT_ARG = {"CREATE_COMMENT": "comment_id"}

_ACTION_KEY_PREFIX = "simulation-action:"
_NODE_KEY_PREFIX = "graph-node:"
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _positive_int(value: Any) -> Optional[int]:
    """Ganzzahlige Datenbank-Kennung; ``bool`` und Nicht-Zahlen sind keine."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def _action_origin_post_id(record: EvidenceRecordModel) -> Optional[str]:
    raw = record.raw
    if not isinstance(raw, Mapping):
        return None
    platform = raw.get("platform")
    action_type = raw.get("action_type")
    if (
        not isinstance(platform, str)
        or platform not in _FEED_PLATFORMS
        or not isinstance(action_type, str)
    ):
        return None
    args = raw.get("action_args")
    if not isinstance(args, Mapping):
        return None
    # Der producer_key kodiert Plattform und Aktionsart ein zweites Mal
    # (``build_action_evidence_item``). Widerspricht er dem Rohwert, ist der
    # Beleg nicht eindeutig zuzuordnen.
    if record.producer_key.startswith(_ACTION_KEY_PREFIX):
        parts = record.producer_key.split(":", 5)
        if len(parts) != 6 or parts[1] != platform or parts[4] != action_type:
            return None
    if action_type in _OWN_POST_ARG:
        post_id = _positive_int(args.get(_OWN_POST_ARG[action_type]))
        return f"{platform}:{post_id}" if post_id is not None else None
    if action_type in _OWN_COMMENT_ARG:
        comment_id = _positive_int(args.get(_OWN_COMMENT_ARG[action_type]))
        return f"{platform}:comment:{comment_id}" if comment_id is not None else None
    return None


def _entity_origin_node_uuids(record: EvidenceRecordModel) -> Optional[list[str]]:
    raw = record.raw
    if not isinstance(raw, Mapping):
        return None
    node_uuid = raw.get("uuid")
    if not isinstance(node_uuid, str) or not _UUID_RE.match(node_uuid):
        return None
    if record.producer_key.startswith(_NODE_KEY_PREFIX):
        if record.producer_key[len(_NODE_KEY_PREFIX):] != node_uuid:
            return None
    return [node_uuid]


def derive_evidence_origin(record: EvidenceRecordModel) -> dict[str, Any]:
    """Abgeleitete ``origin_*``-Felder eines Belegs; leer, wenn nichts eindeutig ist."""
    kind = record.type.value
    if kind == "agent_action":
        post_id = _action_origin_post_id(record)
        return {"origin_post_id": post_id} if post_id is not None else {}
    if kind == "entity_summary":
        node_uuids = _entity_origin_node_uuids(record)
        return {"origin_node_uuids": node_uuids} if node_uuids is not None else {}
    return {}


def with_evidence_origins(evidence_map: EvidenceMapModel) -> EvidenceMapModel:
    """Kopie der Map, deren Belege die abgeleiteten Sprungkennungen tragen.

    Die übergebene Map bleibt unverändert; ohne ableitbare Kennung kommt sie
    selbst zurück.
    """
    updated: dict[str, EvidenceRecordModel] = {}
    for evidence_id, record in evidence_map.evidence_index.items():
        derived = derive_evidence_origin(record)
        updated[evidence_id] = record.model_copy(update=derived) if derived else record
    if all(updated[key] is evidence_map.evidence_index[key] for key in updated):
        return evidence_map
    return evidence_map.model_copy(update={"evidence_index": updated})


__all__ = ["derive_evidence_origin", "with_evidence_origins"]
