"""Abweichende Schwellenwerte: verbunden und begründet — oder sichtbar (#1359).

Im Referenzlauf nannte Abschnitt 1 vier Wochen Pilotbetrieb, Abschnitt 7
mindestens acht. Beide Werte standen unverbunden im Bericht; der Leser konnte
nicht erkennen, ob sich der Bericht widerspricht oder ob der zweite Wert eine
begründete Verschärfung ist.

Drei Bausteine schließen das:

- **Identität.** Die vom Modell vergebene ``id`` ist pro Abschnitt frei
  gewählt; zwei Abschnitte vergeben beide ``thr_01``, und der Merge verwarf
  den zweiten stillschweigend — genau den Wert, der dem ersten widersprach.
  Jeder Schwellenwert bekommt deshalb eine berichtsweite Kennung nach dem
  Muster der Claims: ``T7_01`` ist der erste Schwellenwert aus Abschnitt 7.
- **Verweis.** Die Metadaten-Extraktion eines Abschnitts sieht die bereits
  erfassten Zahlen früherer Abschnitte mit ihrer Kennung und kann eine
  gewollte Abweichung über ``deviates_from`` verbinden.
- **Erkennung.** Dieselbe Größe mit verschiedenen Werten ohne Verbindung ist
  ein Widerspruch. Das lässt sich abzählen und gehört nicht in einen Prompt:
  es wird deterministisch gemeldet, im Markdown wie in den Red-Team-Befunden.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Set

from ...contracts.report_v3 import Threshold
from .threshold_provenance import threshold_measure_key

#: Wie viele bereits erfasste Zahlen der Metadaten-Extraktion höchstens
#: gezeigt werden. Kostenbremse gegen entartete Läufe; reale Berichte liegen
#: deutlich darunter (Referenzlauf: 27 über alle Abschnitte).
PRIOR_THRESHOLDS_PROMPT_LIMIT = 40

#: Wie viele Widersprüche einzeln in die Red-Team-Befunde gehen. Der Slot ist
#: auf ``RED_TEAM_FINDINGS_LIMIT`` begrenzt; abzählbare Befunde stehen vorn und
#: dürfen die Einschätzungen des Modells nicht vollständig verdrängen.
CONFLICT_FINDINGS_LIMIT = 3


def threshold_export_id(section_index: int, position: int) -> str:
    """Berichtsweite Kennung: ``T7_01`` = erster Schwellenwert aus Abschnitt 7."""
    return f"T{section_index}_{position:02d}"


def section_number(section: Dict[str, Any], fallback: int) -> int:
    """Abschnittsnummer für die Kennung; Altbestand ohne Index zählt die Position."""
    value = section.get("section_index")
    return value if isinstance(value, int) and value > 0 else fallback


def namespace_section_thresholds(
    raw_items: Any, section_index: int
) -> List[Any]:
    """Vergibt berichtsweite Kennungen für die Rohdaten eines Abschnitts.

    Die Position zählt über die Rohliste, auch über Einträge, die die
    Validierung später verwirft — nur so stimmt die Kennung mit der überein,
    die :func:`prior_threshold_lines` der Extraktion späterer Abschnitte
    gezeigt hat.

    Ein Verweis auf eine abschnittsinterne ``id`` wird mit umbenannt. Ein
    Verweis ohne Begründung wird entfernt statt den ganzen Schwellenwert an der
    Validierung scheitern zu lassen: der Wert bleibt, und die
    Widerspruchserkennung meldet ihn, falls er einem anderen widerspricht.
    """
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        return []
    renamed: Dict[str, str] = {}
    for position, raw in enumerate(raw_items, start=1):
        if isinstance(raw, dict):
            raw_id = str(raw.get("id") or "")
            if raw_id and raw_id not in renamed:
                renamed[raw_id] = threshold_export_id(section_index, position)

    result: List[Any] = []
    for position, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            result.append(raw)
            continue
        item = dict(raw)
        item["id"] = threshold_export_id(section_index, position)
        target = item.get("deviates_from")
        if target is not None:
            target = renamed.get(str(target), str(target))
            if target == item["id"] or not str(item.get("deviation_rationale") or "").strip():
                item["deviates_from"] = None
                item["deviation_rationale"] = None
            else:
                item["deviates_from"] = target
        result.append(item)
    return result


def prior_threshold_lines(sections: Any, section_index: int) -> List[str]:
    """Die Zahlen früherer Abschnitte mit der Kennung, die der Merge vergibt."""
    if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)):
        return []
    lines: List[str] = []
    for fallback, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            continue
        number = section_number(section, fallback)
        metadata = section.get("structured_metadata")
        if number >= section_index or not isinstance(metadata, dict):
            continue
        raw_items = metadata.get("thresholds")
        if not isinstance(raw_items, list):
            continue
        for position, raw in enumerate(raw_items, start=1):
            if not isinstance(raw, dict) or not raw.get("label"):
                continue
            unit = f" {raw['unit']}" if raw.get("unit") else ""
            lines.append(
                f"- [{threshold_export_id(number, position)}] {raw['label']}: "
                f"{raw.get('value')}{unit} ({raw.get('purpose')})"
            )
    return lines[:PRIOR_THRESHOLDS_PROMPT_LIMIT]


def drop_unresolvable_deviations(thresholds: Sequence[Threshold]) -> List[Threshold]:
    """Entfernt Verweise auf Schwellenwerte, die es im Bericht nicht gibt.

    Das Ziel kann an der Validierung gescheitert oder eine Modellerfindung
    sein. Der Verweis fällt weg, der Wert bleibt — und steht er im
    Widerspruch zu einem anderen, meldet ihn die Erkennung.
    """
    known = {threshold.id for threshold in thresholds}
    return [
        threshold
        if threshold.deviates_from is None or threshold.deviates_from in known
        else threshold.model_copy(
            update={"deviates_from": None, "deviation_rationale": None}
        )
        for threshold in thresholds
    ]


def _find(parent: Dict[str, str], node: str) -> str:
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return parent[node]


def _is_linked(group: Sequence[Threshold]) -> bool:
    """Hängen alle Werte der Gruppe über Verweise zusammen?

    Gleiche Werte gelten als verbunden — sie widersprechen einander nicht.
    """
    parent = {threshold.id: threshold.id for threshold in group}
    by_value: Dict[Any, str] = {}
    for threshold in group:
        if threshold.deviates_from in parent:
            parent[_find(parent, threshold.id)] = _find(parent, threshold.deviates_from)
        twin = by_value.setdefault(threshold.value, threshold.id)
        parent[_find(parent, threshold.id)] = _find(parent, twin)
    roots: Set[str] = {_find(parent, threshold.id) for threshold in group}
    return len(roots) == 1


def find_threshold_conflicts(thresholds: Sequence[Threshold]) -> List[List[Threshold]]:
    """Gruppen derselben Größe mit verschiedenen Werten ohne Verbindung."""
    groups: Dict[tuple[Any, ...], List[Threshold]] = {}
    for threshold in thresholds:
        key = threshold_measure_key(threshold)
        if key is not None:
            groups.setdefault(key, []).append(threshold)
    return [
        group
        for group in groups.values()
        if len({threshold.value for threshold in group}) > 1 and not _is_linked(group)
    ]


def describe_conflict_values(group: Sequence[Threshold]) -> str:
    """„4 weeks [T1_01] und 8 weeks [T7_01]“ — Wert und Fundstelle."""
    parts = [f"{threshold.display_value} [{threshold.id}]" for threshold in group]
    return ", ".join(parts[:-1]) + " und " + parts[-1]


def threshold_conflict_findings(thresholds: Sequence[Threshold]) -> List[str]:
    """Red-Team-Befunde für unverbundene Widersprüche, ohne LLM."""
    conflicts = find_threshold_conflicts(thresholds)
    findings = [
        f"Widersprüchliche operative Zahl ohne begründete Abweichung: "
        f"„{group[0].label}“ steht mit {describe_conflict_values(group)} im "
        "Bericht, keine Nennung verweist auf die andere."
        for group in conflicts[:CONFLICT_FINDINGS_LIMIT]
    ]
    remaining = len(conflicts) - CONFLICT_FINDINGS_LIMIT
    if remaining > 0:
        findings.append(
            f"{remaining} weitere operative Zahl(en) mit widersprüchlichen Werten "
            "ohne begründete Abweichung — siehe Abschnitt „Operative Zahlen“."
        )
    return findings


__all__ = [
    "CONFLICT_FINDINGS_LIMIT",
    "PRIOR_THRESHOLDS_PROMPT_LIMIT",
    "describe_conflict_values",
    "drop_unresolvable_deviations",
    "find_threshold_conflicts",
    "namespace_section_thresholds",
    "prior_threshold_lines",
    "section_number",
    "threshold_conflict_findings",
    "threshold_export_id",
]
