"""Mengenaussagen über Stakeholder brauchen einen aggregierten Beleg (#1345).

„Nahezu alle befragten Akteure bevorzugen einen kontrollierten Pilotbetrieb"
ist keine Aussage, die ein einzelnes Zitat oder ein einzelner Dokumentsatz
tragen kann. Die Quelle „Vorgeschlagen wird: zunächst ausschließlich
Falkenbrück-Mitte" belegt die Empfehlung — nicht, dass nahezu alle sie teilen.
Bis zu diesem Modul prüfte die Adjudication nur Mehrheits- und
Minderheitsmarker und auch die nur gegen Prozentangaben in derselben Quelle.
Alle anderen Quantoren liefen in den qualitativen Pfad und konnten dort über
Deckung oder Judge ``SUPPORTED`` werden.

Zwei Stufen, beide deterministisch:

1. **Je Quelle** (:func:`evidence_backs_quantifier`): Eine Quelle trägt den
   Quantor nur, wenn sie selbst eine mindestens gleich starke Mengenaussage
   derselben Richtung macht („alle Stationen" trägt „nahezu alle Stationen").
   Sonst bleibt sie für den Claim höchstens ``RELATED_ONLY`` — auch wenn sie
   seinen Kern belegt.
2. **Über die Quellen eines Claims** (:func:`aggregate_quantifier_support`):
   Interview-Evidence (``agent_quote``), die den Kern belegt, wird je
   Stakeholder-Gruppe gezählt und gegen die Gegenstimmen im selben Pool
   gestellt. Nur wenn Anzahl und Anteil die Quantorstärke decken, werden
   diese Quellen ``SUPPORTED``.

Claims ohne Quantor berührt dieses Modul nicht. Die belegten Einzelfakten aus
#1317 bleiben dadurch unverändert gedeckt.

Grenze: Gezählt wird, was der Binder nach ``top_k`` noch sieht. Eine
Gegenstimme außerhalb dieses Fensters bleibt unsichtbar. Der Fehler geht damit
in Richtung „zu wenige Belege", nie in Richtung „Quantor ungeprüft".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


class QuantifierStrength(str, Enum):
    """Stärke einer Mengenaussage über eine Gruppe."""

    UNIVERSAL = "universal"
    NEAR_UNIVERSAL = "near_universal"
    MAJORITY = "majority"
    NONE = "none"
    NEAR_NONE = "near_none"


#: Richtung und Rang je Stärke. Eine Quelle trägt einen Claim-Quantor nur
#: in derselben Richtung und mit mindestens gleichem Rang.
_POLARITY_RANK: Dict[QuantifierStrength, Tuple[str, int]] = {
    QuantifierStrength.UNIVERSAL: ("positive", 3),
    QuantifierStrength.NEAR_UNIVERSAL: ("positive", 2),
    QuantifierStrength.MAJORITY: ("positive", 1),
    QuantifierStrength.NONE: ("negative", 3),
    QuantifierStrength.NEAR_NONE: ("negative", 2),
}

_NEAR = r"(?:nahezu|fast|beinahe|praktisch|quasi|annähernd|so gut wie)"

#: Reihenfolge ist Priorität: „nahezu alle" enthält „alle", „fast niemand"
#: enthält „niemand" — die abgeschwächte Form muss zuerst greifen.
_PATTERNS: Tuple[Tuple[QuantifierStrength, "re.Pattern[str]"], ...] = (
    (
        QuantifierStrength.NEAR_NONE,
        re.compile(
            rf"\b{_NEAR}\s+(?:niemand|keine[rnms]?)\b"
            r"|\bkaum\s+(?:jemand|eine[rnms]?)\b"
            r"|\b(?:almost|nearly)\s+(?:no\s+one|nobody|none)\b|\bhardly\s+any",
        ),
    ),
    (
        QuantifierStrength.NEAR_UNIVERSAL,
        re.compile(
            rf"\b{_NEAR}\s+(?:alle|allen|sämtliche[nr]?|jede[rnms]?)\b"
            r"|\b(?:almost|nearly|virtually)\s+(?:all|every)",
        ),
    ),
    (
        QuantifierStrength.NONE,
        re.compile(
            r"\bniemand\b|\bkein(?:e[rnms]?)?\s+einzige[rnms]?\b"
            r"|\bkeine[rs]?\s+(?:der|des|von\s+den)\b"
            r"|\bno\s+one\b|\bnobody\b|\bnone\s+of\b",
        ),
    ),
    (
        QuantifierStrength.UNIVERSAL,
        re.compile(
            r"\b(?:alle|allen|sämtliche[nr]?|allesamt|ausnahmslos|einhellig"
            r"|einstimmig|unisono)\b|\bjede[rs]?\s+(?:einzelne|befragte)"
            r"|\ball\s+of\b|\beveryone\b|\bunanimous",
        ),
    ),
    (
        QuantifierStrength.MAJORITY,
        re.compile(
            r"\bmehrheitlich\b|\bdie\s+mehrheit\b|\bmehrheit\s+der\b"
            r"|\büberwiegend\b|\bdie\s+meisten\b|\bgro(?:ß|ss)teil\b"
            r"|\bmajority\b|\bmost\s+of\b",
        ),
    ),
)

#: Feste Wendungen mit „alle", die nichts über eine Gruppe aussagen.
_IDIOMS = re.compile(
    r"\b(?:auf|für)\s+alle\s+fälle\b|\bein\s+für\s+alle\s*mal\b|\balle\s+paar\b"
)


def detect_quantifier(text: str) -> Optional[QuantifierStrength]:
    """Erkennt die stärkste Mengenaussage im Text, sonst ``None``."""
    lowered = _IDIOMS.sub(" ", (text or "").lower())
    for strength, pattern in _PATTERNS:
        if pattern.search(lowered):
            return strength
    return None


def evidence_backs_quantifier(claim_strength: QuantifierStrength, evidence_text: str) -> bool:
    """Trägt die Quelle selbst eine mindestens gleich starke Mengenaussage?"""
    evidence_strength = detect_quantifier(evidence_text)
    if evidence_strength is None:
        return False
    claim_dir, claim_rank = _POLARITY_RANK[claim_strength]
    ev_dir, ev_rank = _POLARITY_RANK[evidence_strength]
    return claim_dir == ev_dir and ev_rank >= claim_rank


#: Mindestbedingung je Stärke: (übereinstimmende Gruppen, Mindestanteil,
#: Anteil strikt größer). Drei Gruppen für „alle"/„nahezu alle" — mit zwei
#: Stimmen ist „alle" nicht von „beide" zu unterscheiden; der Binder liefert
#: höchstens ``top_k`` = 5 Quellen, drei ist damit erreichbar. Zwei Gruppen für
#: die Mehrheit spiegeln ``cross_stakeholder_for_high`` (ADR-0002 Anker 4):
#: eine einzelne Stimme ist keine Mehrheit.
_REQUIREMENTS: Dict[QuantifierStrength, Tuple[int, float, bool]] = {
    QuantifierStrength.UNIVERSAL: (3, 1.0, False),
    QuantifierStrength.NONE: (3, 1.0, False),
    QuantifierStrength.NEAR_UNIVERSAL: (3, 0.8, False),
    QuantifierStrength.NEAR_NONE: (3, 0.8, False),
    QuantifierStrength.MAJORITY: (2, 0.5, True),
}

_LABELS: Dict[QuantifierStrength, str] = {
    QuantifierStrength.UNIVERSAL: "alle",
    QuantifierStrength.NEAR_UNIVERSAL: "nahezu alle",
    QuantifierStrength.MAJORITY: "Mehrheit",
    QuantifierStrength.NONE: "niemand",
    QuantifierStrength.NEAR_NONE: "nahezu niemand",
}

#: Checks, die ``classify_evidence`` für den Aggregationsschritt hinterlässt.
CHECK_NEEDS_AGGREGATION = "quantifier_needs_aggregation"
CHECK_CORE_SUPPORTED = "quantifier_core_supported"

#: Auffangtypen bezeichnen keine Rollenfamilie. Spiegelt
#: ``report_contract._GENERIC_ENTITY_TYPES``.
_GENERIC_FAMILIES = frozenset({"person", "organization", "entity", "node", "unknown", "other"})


def quantifier_label(strength: QuantifierStrength) -> str:
    return _LABELS[strength]


def is_agent_quote(item: Dict[str, Any]) -> bool:
    return item.get("source_kind") == "agent_quote" or item.get("type") in {
        "agent_interview",
        "agent_quote",
    }


def stakeholder_group_key(item: Dict[str, Any]) -> Optional[str]:
    """Zählschlüssel einer Stimme — Rollenfamilie vor Berufstitel (#1248).

    Spiegelt ``report_contract._role_family_key`` für Dicts. ``None`` heißt:
    die Stimme ist keiner Gruppe zuordenbar und wird nicht gezählt.
    """
    family = " ".join(str(item.get("persona_role_family") or "").split()).casefold()
    if family and family not in _GENERIC_FAMILIES:
        return f"family:{family}"
    group = " ".join(str(item.get("persona_stakeholder_group") or "").split()).casefold()
    return f"title:{group}" if group else None


@dataclass(frozen=True)
class QuantifierTally:
    strength: QuantifierStrength
    supporting_groups: int
    dissenting_groups: int

    @property
    def share(self) -> float:
        known = self.supporting_groups + self.dissenting_groups
        return self.supporting_groups / known if known else 0.0

    @property
    def satisfied(self) -> bool:
        min_groups, min_share, strict = _REQUIREMENTS[self.strength]
        if self.supporting_groups < min_groups:
            return False
        return self.share > min_share if strict else self.share >= min_share

    def describe(self) -> str:
        min_groups, min_share, strict = _REQUIREMENTS[self.strength]
        relation = ">" if strict else "≥"
        return (
            f"Mengenaussage „{quantifier_label(self.strength)}“ verlangt mindestens "
            f"{min_groups} übereinstimmende Stakeholder-Gruppen (Anteil {relation} "
            f"{min_share:.0%}); belegt: {self.supporting_groups}, "
            f"Gegenstimmen: {self.dissenting_groups}"
        )


BindingEntry = Tuple[Dict[str, Any], Dict[str, Any], Sequence[str]]


def _tally(
    strength: QuantifierStrength, entries: Iterable[BindingEntry]
) -> Tuple[QuantifierTally, Dict[str, List[Dict[str, Any]]]]:
    supporting: Dict[str, List[Dict[str, Any]]] = {}
    dissenting: set[str] = set()
    for bound, item, checks in entries:
        if not is_agent_quote(item):
            continue
        key = stakeholder_group_key(item)
        if key is None:
            continue
        if bound.get("entailment") == "CONTRADICTED":
            dissenting.add(key)
        elif CHECK_CORE_SUPPORTED in checks:
            supporting.setdefault(key, []).append(bound)
    # Eine Gruppe, die zugleich zustimmt und widerspricht, ist gespalten —
    # sie zählt als Gegenstimme, nicht als Beleg.
    for key in dissenting:
        supporting.pop(key, None)
    tally = QuantifierTally(strength, len(supporting), len(dissenting))
    return tally, supporting


def aggregate_quantifier_support(
    claim_text: str, entries: Sequence[BindingEntry]
) -> Optional[QuantifierTally]:
    """Zweite Stufe: deckt die Interview-Evidence eines Claims den Quantor?

    ``entries`` sind ``(binding, evidence_item, checks)`` in Binder-Reihenfolge.
    Die Bindings werden an Ort und Stelle aktualisiert: bei gedecktem Quantor
    werden die Kern-Belege der zählenden Gruppen ``SUPPORTED``; sonst bleibt
    es bei ``RELATED_ONLY`` mit einer Begründung, die Soll und Ist nennt.
    """
    strength = detect_quantifier(claim_text)
    if strength is None:
        return None
    pending = [e for e in entries if CHECK_NEEDS_AGGREGATION in e[2]]
    if not pending:
        return None
    tally, supporting = _tally(strength, entries)
    counted = {id(bound) for bounds in supporting.values() for bound in bounds}
    for bound, _item, checks in pending:
        if tally.satisfied and id(bound) in counted:
            bound["entailment"] = "SUPPORTED"
            bound["supports_claim"] = True
            bound["entailment_reason"] = (
                f"Mengenaussage „{quantifier_label(strength)}“ durch "
                f"{tally.supporting_groups} übereinstimmende Stakeholder-Gruppen "
                f"gedeckt (Gegenstimmen: {tally.dissenting_groups})"
            )
        elif CHECK_CORE_SUPPORTED in checks:
            bound["entailment_reason"] = tally.describe()
    return tally


__all__ = [
    "CHECK_CORE_SUPPORTED",
    "CHECK_NEEDS_AGGREGATION",
    "QuantifierStrength",
    "QuantifierTally",
    "aggregate_quantifier_support",
    "detect_quantifier",
    "evidence_backs_quantifier",
    "is_agent_quote",
    "quantifier_label",
    "stakeholder_group_key",
]
