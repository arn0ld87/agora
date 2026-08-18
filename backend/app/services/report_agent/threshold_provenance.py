"""Schwellenwerte: einmal je Sachverhalt, mit belegbarer Herkunft.

Der Referenzlauf ``report_cc2ef45da5e9`` exportierte 27 Thresholds. Alle
trugen ``evidence_status="heuristic"``, alle hatten ``evidence_refs=[]`` — auch
die, die wörtlich im Seed-Dokument standen (80 % Schulungsquote, 15 Minuten
manueller Fallback, 38 Fälle). Mehrere Werte erschienen doppelt, weil sie in
zwei Abschnitten genannt wurden und die Deduplizierung nur über die vom Modell
vergebene ``id`` lief. Und derselbe Wert trug an einer Stelle
``simulation_proposal``, an anderer ``empirical_data``.

Für den Leser heißt das: eine dokumentierte Anforderung sieht aus wie ein
Modelleinfall, derselbe Wert zählt doppelt, und die Herkunftsangabe ist
beliebig. Drei getrennte Schäden, eine Stelle, an der sie sich beheben lassen —
dem Zusammenführen der Abschnitts-Metadaten.

Deduplizierung läuft über einen kanonischen Schlüssel aus dem, was die Zahl
inhaltlich ausmacht: Kennzahl, Bezug, Wert, Einheit, Rolle. Die vom Modell
vergebene ``id`` taugt dafür nicht — sie ist pro Abschnitt frei gewählt.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from ...contracts.report_v3 import Threshold
from ..evidence_entailment import coverage_ratio, extract_numeric_facts

#: Einheiten-Schreibweisen, die dieselbe Einheit meinen. Das Modell schreibt
#: mal "percent", mal "%", mal "Prozent" — ohne Normalisierung entgeht der
#: Deduplizierung genau der Fall, für den sie da ist.
_UNIT_ALIASES = {
    "%": "percent",
    "prozent": "percent",
    "pct": "percent",
    "minuten": "minutes",
    "min": "minutes",
    "minute": "minutes",
    "tage": "days",
    "tag": "days",
    "day": "days",
    "stück": "count",
    "stueck": "count",
    "anzahl": "count",
    "fälle": "count",
    "faelle": "count",
    "euro": "eur",
    "€": "eur",
}

#: Herkunftsangaben nach Behauptungsstärke. Eine Zahl als
#: ``document_requirement`` auszuweisen behauptet mehr als ``model_proposal``.
#: Bei einem Konflikt zwischen zwei unbelegten Angaben gewinnt deshalb die
#: schwächere — der Contract sagt es selbst: "Im Zweifel model_proposal".
_ORIGIN_STRENGTH = {
    "model_proposal": 0,
    "simulation_proposal": 1,
    "operator_policy": 2,
    "empirical_data": 3,
    "external_standard": 4,
    "document_requirement": 5,
}

#: Beleglage nach Stärke, für das Zusammenführen von Dubletten.
_STATUS_STRENGTH = {"heuristic": 0, "derived": 1, "verified": 2}

#: Ab welcher Deckung zwischen Threshold-Label und Quelltext die Zahl als
#: derselbe Sachverhalt gilt. Bewusst niedrig: das Label ist ein Stichwort
#: ("Schulungsquote"), der Quelltext ein ganzer Satz. Was den Treffer trägt,
#: ist die Zahl — das Label schließt nur Zufallstreffer aus.
LABEL_MATCH_THRESHOLD = 0.20

_TOKEN_RE = re.compile(r"[^\wäöüßÄÖÜ]+")


def normalize_unit(unit: str) -> str:
    lowered = (unit or "").strip().lower()
    return _UNIT_ALIASES.get(lowered, lowered)


#: Präfixlänge für den Label-Vergleich. Sechs Zeichen legten
#: "Fallbackdauer" und "Fallbackzeit" auf denselben Schlüssel — zwei fachlich
#: verschiedene Schwellenwerte wären zu einem verschmolzen, und der verworfene
#: erschiene nirgends mehr. Zehn behält die Robustheit gegen Beugungsformen
#: ("Schulungsquote"/"Schulungsquoten") und trennt die Komposita.
_LABEL_TOKEN_PREFIX = 10


def _label_tokens(label: str) -> frozenset[str]:
    return frozenset(
        token[:_LABEL_TOKEN_PREFIX]
        for token in _TOKEN_RE.split((label or "").lower())
        if len(token) > 3
    )


def canonical_threshold_key(threshold: Threshold) -> tuple[Any, ...]:
    """Der Sachverhalt, den eine Zahl beschreibt — ohne ihre Formulierung.

    Kennzahl und Bezug stecken beide im ``label``; der Contract trennt sie
    nicht. Gemeinsam normalisiert sind sie trotzdem trennscharf genug: "80 %
    Schulungsquote vor Produktivstart" und "Schulungsquote 80 % (Zielwert)"
    fallen zusammen, "80 % Schulungsquote" und "80 % Verfügbarkeit" nicht.
    """
    return (
        frozenset(_label_tokens(threshold.label)),
        round(float(threshold.value), 6),
        normalize_unit(threshold.unit),
        threshold.purpose,
    )


def _merge_pair(kept: Threshold, other: Threshold) -> Threshold:
    """Führt zwei Beschreibungen derselben Zahl zusammen.

    Belege addieren sich — zwei Abschnitte, die dieselbe Zahl je mit einer
    eigenen Quelle nennen, ergeben eine Zahl mit zwei Quellen. Die Herkunft
    dagegen addiert sich nicht: sie ist eine Behauptung, und zwei
    widersprüchliche Behauptungen werden nicht dadurch wahrer, dass man die
    lautere nimmt.
    """
    refs = list(dict.fromkeys([*kept.evidence_refs, *other.evidence_refs]))
    status = max(
        (kept.evidence_status, other.evidence_status),
        key=lambda value: _STATUS_STRENGTH.get(value, 0),
    )
    if refs:
        # Belegt: die stärkere Herkunftsangabe darf stehen bleiben, denn sie
        # ist überprüfbar.
        origin = max(
            (kept.origin, other.origin),
            key=lambda value: _ORIGIN_STRENGTH.get(value, 0),
        )
    else:
        origin = min(
            (kept.origin, other.origin),
            key=lambda value: _ORIGIN_STRENGTH.get(value, 0),
        )
    return kept.model_copy(
        update={"evidence_refs": refs, "evidence_status": status, "origin": origin}
    )


def dedup_thresholds(thresholds: Sequence[Threshold]) -> List[Threshold]:
    """Eine Zahl je Sachverhalt, in der Reihenfolge des ersten Auftretens."""
    merged: Dict[tuple[Any, ...], Threshold] = {}
    for threshold in thresholds:
        key = canonical_threshold_key(threshold)
        existing = merged.get(key)
        merged[key] = threshold if existing is None else _merge_pair(existing, threshold)
    return list(merged.values())


#: Quellengattungen, die einen Schwellenwert *belegen* können.
#:
#: ``inferred`` ist eine Modellableitung und ``web_source`` eine Fundstelle
#: ohne Projektbezug — beide dürfen keinen Wert auf ``verified`` heben. Sonst
#: entstünde die Kombination ``origin="model_proposal"`` mit
#: ``evidence_status="verified"``: eine Zahl, die sich selbst als belegt
#: ausweist, weil das Modell sie zweimal genannt hat.
VERIFYING_SOURCE_KINDS = frozenset({"seed_corpus", "agent_quote", "graph_relation"})


def _evidence_texts(evidence_pool: Sequence[Dict[str, Any]]) -> List[tuple[str, str]]:
    out: List[tuple[str, str]] = []
    for record in evidence_pool:
        if not isinstance(record, dict):
            continue
        if str(record.get("source_kind") or "") not in VERIFYING_SOURCE_KINDS:
            continue
        evidence_id = str(record.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        text = " ".join(
            str(record.get(key) or "")
            for key in ("snippet", "quote", "value", "content", "text")
        ).strip()
        if text:
            out.append((evidence_id, text))
    return out


def bind_threshold_provenance(
    thresholds: Sequence[Threshold],
    evidence_pool: Sequence[Dict[str, Any]],
) -> List[Threshold]:
    """Bindet Schwellenwerte an die Quellen, die ihre Zahl tatsächlich nennen.

    Ein Wert, der wörtlich im Seed steht, darf nicht als unbelegte Heuristik
    enden. Gesucht wird deterministisch: gleicher Zahlenwert, gleiche Einheit,
    thematisch passendes Label. Bleibt eine Zahl ohne Treffer, ändert sich
    nichts an ihr — eine unbelegte Zahl als belegt auszuweisen wäre der
    schlimmere Fehler.

    Bereits belegte Thresholds bleiben unangetastet; ihre Referenzen kommen
    aus dem Modell und sind nicht schlechter als diese hier.
    """
    texts = _evidence_texts(evidence_pool)
    if not texts:
        return list(thresholds)

    bound: List[Threshold] = []
    for threshold in thresholds:
        if threshold.evidence_refs:
            bound.append(threshold)
            continue

        unit = normalize_unit(threshold.unit)
        refs = [
            evidence_id
            for evidence_id, text in texts
            if _text_carries_threshold(text, threshold.value, unit)
            and coverage_ratio(threshold.label, text) >= LABEL_MATCH_THRESHOLD
        ]
        if not refs:
            bound.append(threshold)
            continue

        bound.append(
            threshold.model_copy(
                update={"evidence_refs": refs, "evidence_status": "verified"}
            )
        )
    return bound


#: Wortformen je Contract-Einheit. Die Faktenextraktion unterscheidet nur
#: ``percent`` von ``absolute`` — welche Absoluteinheit gemeint ist, steht im
#: Text daneben. Ohne diese Zuordnung belegte "15 Minuten" einen Schwellenwert
#: von "15 Tagen", solange das Label überlappte: eine operative Empfehlung mit
#: erfundener Herkunft.
_UNIT_WORD_FORMS = {
    "minutes": ("minute", "minuten", "min."),
    "hours": ("stunde", "stunden", "std."),
    "days": ("tag", "tage", "tagen"),
    "weeks": ("woche", "wochen"),
    "months": ("monat", "monate", "monaten"),
    "eur": ("euro", "eur", "€"),
    "count": ("fall", "fälle", "faelle", "stück", "stueck", "anzahl"),
}


def _text_carries_threshold(text: str, value: float, unit: str) -> bool:
    """Nennt der Quelltext genau diesen Wert in dieser Einheit?

    Für Prozentwerte entscheidet die Extraktion selbst. Für alles andere
    muss die Einheit im Text auftauchen — ihr Fehlen heißt nicht "passt
    schon", sondern "nicht nachweisbar". Eine Einheit, für die es keine
    Wortformen gibt, bleibt beim Wertvergleich; sie kann nicht schärfer
    geprüft werden, als der Contract sie beschreibt.
    """
    lowered = (text or "").lower()
    forms = _UNIT_WORD_FORMS.get(unit)
    for fact in extract_numeric_facts(text):
        if abs(fact.value - value) >= 0.001:
            continue
        if unit == "percent":
            if fact.unit != "percent":
                continue
            return True
        if fact.unit == "percent":
            continue
        if forms and not any(form in lowered for form in forms):
            continue
        return True
    return False


__all__ = [
    "LABEL_MATCH_THRESHOLD",
    "VERIFYING_SOURCE_KINDS",
    "bind_threshold_provenance",
    "canonical_threshold_key",
    "dedup_thresholds",
    "normalize_unit",
]
