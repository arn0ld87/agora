"""Kernaussagen tragen kein eigenes Confidence-Urteil (#1766).

``SectionMetadata.key_takeaways`` entsteht in einem eigenen LLM-Aufruf
(``chat_json``), *bevor* die Claims des Abschnitts extrahiert, gebunden und
validiert sind. Das Modell sieht also nur den Fliesstext und schaetzt
``confidence`` frei. Im Lauf ``report_a8fa9ff9fad0`` standen so 7 von 29
Kernaussagen auf ``high``, waehrend alle fuenf finalen Claims ``low`` waren —
und die Werte landeten im persistierten ``evidence_map.json`` und im Export.
Die ADR-0002-Validatoren (``cross_stakeholder_for_high``,
``reject_inferred_in_high_confidence``) greifen nur auf ``ReportClaimModel``
und decken diese Flaeche nicht ab.

Diese Funktionen deckeln das Urteil nachtraeglich auf das, was die final
validierten Claims desselben Abschnitts tragen:

* ``min(eigenes Label, hoechstes Claim-Label)`` — nie ein hoeheres Label als der
  staerkste Claim des Abschnitts.
* Kein validierter Claim oder nur ``speculative`` → ``None``: das Label entfaellt,
  statt eine Sicherheit zu behaupten, die kein Beleg traegt.
* Unbekannte Altwerte (freie Strings aus aelteren Laeufen) werden wie ein
  fehlendes Urteil behandelt, nicht abgelehnt.

Das ist eine Verschaerfung: ein Label kann hier nur sinken oder entfallen. Die
fuenf ADR-0002-Anker bleiben unberuehrt.

Rein funktional, ohne Zustand und ohne I/O — der Aufrufer
(``ReportAgent._save_evidence_section``) wendet sie nach der Claim-Finalisierung
und vor der Persistenz an.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional, Sequence

from .claim_provenance import derive_confidence_scope

logger = logging.getLogger(__name__)

#: Ordnung der Takeaway-Labels. ``None`` (kein Urteil) liegt unter ``low``.
_TAKEAWAY_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}
_RANK_TO_LABEL: dict[int, str] = {rank: label for label, rank in _TAKEAWAY_ORDER.items()}

#: Claim-Labels auf der Takeaway-Skala. ``verified`` liegt darueber und zaehlt
#: als ``high``; ``speculative`` liegt darunter und stuetzt kein Urteil.
_CLAIM_RANK: dict[str, int] = {
    "speculative": -1,
    "low": 0,
    "medium": 1,
    "high": 2,
    "verified": 2,
}

#: Deutsche und englische Umgangsformen, die ein Modell trotz Enum liefert.
_LABEL_ALIASES: dict[str, str] = {
    "niedrig": "low",
    "gering": "low",
    "mittel": "medium",
    "moderat": "medium",
    "hoch": "high",
}


def normalize_takeaway_confidence(value: Any) -> Optional[str]:
    """Bringt einen LLM- oder Altwert auf ``low``/``medium``/``high`` oder ``None``.

    Gross-/Kleinschreibung und Whitespace sind egal, ``hoch`` ist ``high``.
    Alles Unbekannte — auch ``verified`` und ``very high`` — wird ``None``: ein
    Wert ausserhalb der Skala ist kein Urteil, das man auf die naechstliegende
    Stufe raten duerfte.
    """
    if not isinstance(value, str):
        return None
    key = " ".join(value.split()).casefold()
    key = _LABEL_ALIASES.get(key, key)
    return key if key in _TAKEAWAY_ORDER else None


def highest_claim_rank(claims: Sequence[Any]) -> Optional[int]:
    """Hoechster Rang unter den Claim-Labels, ``None`` ohne tragfaehigen Claim."""
    ranks = [
        _CLAIM_RANK[label]
        for claim in claims or []
        if isinstance(claim, Mapping)
        for label in [_label_of(claim)]
        if label in _CLAIM_RANK
    ]
    best = max(ranks, default=None)
    # ``speculative`` allein traegt kein Urteil.
    return best if best is not None and best >= 0 else None


def _label_of(claim: Mapping[str, Any]) -> str:
    raw = claim.get("confidence_label")
    # ``model_dump(mode="json")`` liefert den Enum-Wert, Rohdicts u. U. das Enum.
    return str(getattr(raw, "value", raw) or "").strip().lower()


def cap_takeaway_confidence(
    takeaways: Any,
    final_claims: Sequence[Any],
    *,
    evidence_index: Optional[Mapping[str, Any]] = None,
) -> list[Any]:
    """Deckelt ``confidence`` und ``confidence_scope`` der Kernaussagen.

    ``final_claims`` sind die nach Validierung und Reparatur verbliebenen
    Claims des Abschnitts (Dicts mit ``confidence_label`` und ``evidence``).
    Gibt eine neue Liste zurueck; die Eingabe bleibt unveraendert. Eintraege,
    die keine Dicts sind, laufen unveraendert durch.

    ``confidence_scope``: ``evidence`` darf eine Kernaussage nur behaupten,
    wenn mindestens ein finaler Claim des Abschnitts quellengebunden ist
    (abgeleitet wie am Claim selbst). ``empirical`` wird nie bestaetigt: Agora
    erhebt keine empirischen Daten. In beiden Faellen faellt der Wert auf
    ``evidence`` (wenn gebunden) bzw. ``simulation_consensus`` zurueck.
    """
    if not isinstance(takeaways, list):
        return []
    ceiling = highest_claim_rank(final_claims)
    evidence_bound = any(
        isinstance(claim, Mapping)
        and derive_confidence_scope(claim.get("evidence"), evidence_index) == "evidence"
        for claim in final_claims or []
    )
    capped: list[Any] = []
    for takeaway in takeaways:
        if not isinstance(takeaway, dict):
            capped.append(takeaway)
            continue
        entry = dict(takeaway)
        own = normalize_takeaway_confidence(entry.get("confidence"))
        if own is None or ceiling is None:
            entry["confidence"] = None
        else:
            entry["confidence"] = _RANK_TO_LABEL[min(_TAKEAWAY_ORDER[own], ceiling)]
        if entry.get("confidence_scope") in {"evidence", "empirical"}:
            entry["confidence_scope"] = "evidence" if evidence_bound else "simulation_consensus"
        capped.append(entry)
    return capped


def cap_section_key_takeaways(evidence_map: Any, section_index: int) -> int:
    """Wendet den Deckel auf die persistierte Section ``section_index`` an.

    Arbeitet in-place auf der (bereits validierten) Evidence-Map direkt vor
    dem Schreiben und liest die Claims aus genau dieser Section — also den
    Stand nach Gate, Reparatur und Entfernung. Gibt die Anzahl der Kernaussagen
    zurueck, deren Label oder Geltungsbereich sich dabei geaendert hat.
    """
    if not isinstance(evidence_map, dict):
        return 0
    index = evidence_map.get("evidence_index")
    changed = 0
    for section in evidence_map.get("sections") or []:
        if not isinstance(section, dict) or section.get("section_index") != section_index:
            continue
        metadata = section.get("structured_metadata")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("key_takeaways"), list):
            continue
        before = metadata["key_takeaways"]
        after = cap_takeaway_confidence(
            before,
            section.get("claims") or [],
            evidence_index=index if isinstance(index, Mapping) else None,
        )
        # Ein fehlender Schluessel ist ``None``: das Ergaenzen von ``null`` ist
        # keine inhaltliche Aenderung des Urteils.
        changed += sum(
            1
            for old, new in zip(before, after)
            if isinstance(old, dict)
            and (
                old.get("confidence") != new.get("confidence")
                or old.get("confidence_scope") != new.get("confidence_scope")
            )
        )
        metadata["key_takeaways"] = after
    if changed:
        logger.info(
            "section %d: %d Kernaussage(n) auf die Claim-Labels des Abschnitts gedeckelt",
            section_index,
            changed,
        )
    return changed


__all__ = [
    "cap_section_key_takeaways",
    "cap_takeaway_confidence",
    "highest_claim_rank",
    "normalize_takeaway_confidence",
]
