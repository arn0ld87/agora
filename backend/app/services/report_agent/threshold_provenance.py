"""Herkunft einer operativen Zahl aus dem Beleg, in dem sie steht (#1359 A).

Der Bericht fordert in Abschnitt 1 einen vierwoechigen und in Abschnitt 7
einen mindestens achtwoechigen Pilotbetrieb. Beide Zahlen stehen im Artefakt
als ``model_proposal`` mit ``evidence_status="heuristic"`` und leerer
``evidence_refs``-Liste — als haette das Sprachmodell sie sich beide
ausgedacht. Die vier Wochen stammen aber aus dem Seed-Dokument.

Der Feldtext von ``Threshold.origin`` sagt „im Zweifel ``model_proposal``".
Im Zweifel war bisher immer, denn **Schwellen wurden nie an Evidence
gebunden**: das Modell liefert sie als Teil der Abschnittsmetadaten, und was
es an ``evidence_refs`` mitgibt, ist selbst wieder geraten. Ohne Bindung
kann keine Ableitung greifen — deshalb bindet dieses Modul zuerst und leitet
dann ab.

**Warum ein eigener Abgleich und nicht** :func:`extract_numeric_facts`:
Jene Funktion kennt zwei Einheiten (``percent`` und ``absolute``), verlangt
eine Bezugsgruppe und liest nur Ziffern. „vier Wochen" faende sie nicht. Eine
Schwelle ist ein viel engeres Problem: Wert und Einheit sind bekannt, gesucht
wird genau dieses Paar im Belegtext. Das laesst sich praeziser loesen, ohne
die Entailment-Engine anzufassen — Regel 2 dort haengt an ADR-0002 und ist
kein Ort fuer Beilaeufiges.

Gebunden wird nur, was **wortwoertlich im Beleg steht**. Ein Beleg, der
„sechs Wochen" sagt, belegt keine Vier-Wochen-Schwelle, auch wenn er vom
selben Pilotbetrieb handelt.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

#: Einheitenbezeichner des Vertrags → Woerter, die sie im Fliesstext tragen.
#: ``count`` steht bewusst mit leerem Tupel: eine blosse Anzahl hat kein
#: Einheitenwort, dort genuegt der Zahlentreffer allein.
_UNIT_WORDS: Mapping[str, Tuple[str, ...]] = {
    "percent": ("%", "prozent", "percent"),
    "weeks": ("woche", "wochen", "week", "weeks"),
    "days": ("tag", "tage", "tagen", "day", "days"),
    "months": ("monat", "monate", "monaten", "month", "months"),
    "hours": ("stunde", "stunden", "hour", "hours"),
    "minutes": ("minute", "minuten", "minute", "minutes"),
    "eur": ("eur", "euro", "€"),
    "count": (),
}

#: Ausgeschriebene Zahlwoerter bis zwoelf. Darueber schreibt deutscher
#: Fliesstext in aller Regel Ziffern, und die Liste bliebe eine Sammlung von
#: Sonderfaellen ohne Gewinn.
_NUMBER_WORDS: Mapping[str, float] = {
    "ein": 1.0, "eine": 1.0, "einen": 1.0, "einem": 1.0, "eins": 1.0,
    "zwei": 2.0, "drei": 3.0, "vier": 4.0, "fuenf": 5.0, "fünf": 5.0,
    "sechs": 6.0, "sieben": 7.0, "acht": 8.0, "neun": 9.0, "zehn": 10.0,
    "elf": 11.0, "zwoelf": 12.0, "zwölf": 12.0,
}

_DIGIT_RE = re.compile(r"\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?")
_WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+")

#: Abstand zwischen Zahl und Einheitenwort. „4 Wochen" und „4 volle Wochen"
#: sollen treffen, „4 Standorte mit je 8 Wochen Vorlauf" nicht.
_UNIT_WINDOW = 24

#: Quellengattungen, die eine Zahl zur Dokumentanforderung machen.
_DOCUMENT_SOURCE_KINDS = frozenset({"seed_corpus"})

#: Quellengattungen, die eine Zahl zum Vorschlag aus der Simulation machen.
_SIMULATION_SOURCE_KINDS = frozenset({"agent_quote", "agent_action"})

#: Herkuenfte, die eine Zahl als verbindlich ausweisen. Ohne Beleg darf keine
#: davon stehenbleiben — das ist genau die Behauptung, die #1160 E adressiert.
_AUTHORITATIVE_ORIGINS = frozenset(
    {"document_requirement", "empirical_data", "external_standard", "operator_policy"}
)


def _parse_number(raw: str) -> Optional[float]:
    cleaned = raw.strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", cleaned):  # 1.234.567
        cleaned = cleaned.replace(".", "")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _numbers_in(text: str) -> Iterable[Tuple[float, int]]:
    """Alle Zahlen des Textes als (Wert, Endposition) — Ziffern und Zahlwoerter."""
    for match in _DIGIT_RE.finditer(text):
        value = _parse_number(match.group(0))
        if value is not None:
            yield value, match.end()
    for match in _WORD_RE.finditer(text):
        value = _NUMBER_WORDS.get(match.group(0).lower())
        if value is not None:
            yield value, match.end()


def snippet_carries_value(text: str, value: float, unit: str) -> bool:
    """Steht *value* mit der Einheit *unit* woertlich in *text*?

    Fuer Einheiten ohne Einheitenwort (``count``) genuegt der Zahlentreffer.
    Sonst muss das Einheitenwort dicht hinter der Zahl stehen — sonst belegte
    „4 Standorte mit je 8 Wochen Vorlauf" eine Vier-Wochen-Schwelle.
    """
    if not text:
        return False
    unit_words = _UNIT_WORDS.get(unit.strip().lower())
    if unit_words is None:
        # Unbekannte Einheit: der Zahlentreffer allein waere Raterei.
        return False
    lowered = text.lower()
    for found, end in _numbers_in(text):
        if abs(found - value) >= 0.001:
            continue
        if not unit_words:
            return True
        window = lowered[end:end + _UNIT_WINDOW]
        if any(word in window for word in unit_words):
            return True
    return False


def _evidence_text(record: Mapping[str, Any]) -> str:
    parts = [
        str(record.get("snippet") or ""),
        str(record.get("quote") or ""),
    ]
    return " ".join(part for part in parts if part)


def bind_threshold(
    value: float,
    unit: str,
    evidence_index: Mapping[str, Any],
) -> List[Tuple[str, str]]:
    """Sucht Belege, die *value* mit *unit* woertlich nennen.

    Liefert ``(evidence_id, source_kind)``-Paare in der Reihenfolge des Index.
    """
    hits: List[Tuple[str, str]] = []
    for evidence_id, record in evidence_index.items():
        if not isinstance(record, Mapping):
            continue
        if snippet_carries_value(_evidence_text(record), value, unit):
            hits.append((str(evidence_id), str(record.get("source_kind") or "")))
    return hits


def resolve_threshold_provenance(
    threshold: Any,
    evidence_index: Mapping[str, Any],
) -> Dict[str, Any]:
    """Berechnet die Feldaenderungen fuer eine Schwelle.

    Rueckgabe ist das ``update``-Dict fuer ``model_copy`` — leer, wenn nichts
    zu aendern ist.

    Drei Faelle, alle aus der Quellengattung der belegenden Items:

    * Steht die Zahl in einem ``seed_corpus``-Beleg, ist sie eine
      Dokumentanforderung. Genau das war der Fall der vier Wochen.
    * Steht sie nur in Aeusserungen oder Handlungen simulierter Agenten, ist
      sie ein Vorschlag aus der Simulation — ``simulation_proposal`` existiert
      im Vertrag fuer diesen Fall.
    * Steht sie nirgends, darf keine verbindliche Herkunft stehenbleiben. Eine
      Zahl, die als Dokumentanforderung auftritt, ohne dass ein Dokument sie
      nennt, ist die Behauptung, gegen die #1160 E antritt — sie faellt auf
      ``model_proposal`` zurueck.

    Web-Treffer und Graph-Relationen belegen die Zahl (``verified``), aendern
    die Herkunft aber nicht: ob ein Web-Fund eine Norm, eine Messung oder eine
    fremde Empfehlung ist, entscheidet die Gattung nicht.
    """
    hits = bind_threshold(float(threshold.value), str(threshold.unit), evidence_index)
    update: Dict[str, Any] = {}

    if not hits:
        if str(threshold.origin) in _AUTHORITATIVE_ORIGINS and not threshold.evidence_refs:
            update["origin"] = "model_proposal"
            update["evidence_status"] = "heuristic"
        return update

    kinds = {kind for _, kind in hits}
    update["evidence_refs"] = list(
        dict.fromkeys([*threshold.evidence_refs, *(eid for eid, _ in hits)])
    )
    update["evidence_status"] = "verified"

    if kinds & _DOCUMENT_SOURCE_KINDS:
        update["origin"] = "document_requirement"
    elif kinds and kinds <= _SIMULATION_SOURCE_KINDS:
        update["origin"] = "simulation_proposal"
    return update


def apply_threshold_provenance(
    thresholds: Iterable[Any],
    evidence_index: Mapping[str, Any],
) -> List[Any]:
    """Wendet :func:`resolve_threshold_provenance` auf jede Schwelle an."""
    resolved: List[Any] = []
    for threshold in thresholds:
        update = resolve_threshold_provenance(threshold, evidence_index)
        resolved.append(threshold.model_copy(update=update) if update else threshold)
    return resolved


__all__ = [
    "apply_threshold_provenance",
    "bind_threshold",
    "resolve_threshold_provenance",
    "snippet_carries_value",
]
