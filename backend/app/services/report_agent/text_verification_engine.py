from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..evidence_entailment import (
    EntailmentJudge,
    EntailmentResult,
    EntailmentVerdict,
    NumericFact,
    classify_evidence,
    extract_numeric_facts,
)
from ..sentence_splitter import split_sentences
from .text_verification_renumbering import (
    _FENCE,
    _LIST_PREFIX,
    _ORDERED_ITEM,
    _is_structural,
    _leading_ordinal,
    _mark_unverified,
    _renumber_block,
    _renumber_enumeration,
    _strip_marker,
)
from .text_verification_types import (
    FactOutcome,
    RejectedStatement,
    UnverifiedStatement,
    VerifiedProse,
)


def _fact_probe(fact: NumericFact) -> str:
    """Baut aus einem extrahierten Fakt einen eigenständigen Prüftext.

    Die Prüfung läuft pro Fakt, nicht pro Satz: ein Satz, der drei
    Schulungsquoten nennt, darf nicht daran scheitern, dass ein einzelnes
    Evidence-Item einen dieser Werte einer fremden Bezugsgruppe zuordnet.
    Der rekonstruierte Text enthält genau das, was
    :func:`extract_numeric_facts` wieder als denselben Fakt erkennt.
    """
    if fact.unit == "percent":
        head = f"{fact.value:g} Prozent"
    else:
        head = f"{fact.value:g}"
    # Der Scope gehört vor die Zahl: dort steht er im Original, und nur dort
    # findet ihn die Extraktion wieder. Ohne ihn verliert die Claim-Seite ihre
    # Teilpopulation, während die Evidence-Seite ihre behält — der
    # Vergleichbarkeitstest liefe dann systematisch schief und der Schutz vor
    # falschen Widersprüchen wäre ausgerechnet im Fließtext-Pfad wirkungslos.
    scope = " ".join(sorted(fact.scope))
    return " ".join(
        part for part in (scope, head, fact.subject, fact.predicate) if part
    ).strip()


#: Aussagekraft — welches Pool-Urteil entscheidet über einen Fakt?
#:
#: Ein Beleg schlägt alles. Danach kommt der Widerspruch: er trägt eine
#: Information ("die Quelle sagt etwas anderes"), die ein ``INSUFFICIENT``
#: nicht hat ("diese Quelle sagt dazu nichts"). Weil der Pool seit #1356 der
#: vollständige ``evidence_index`` ist, liefert praktisch immer *irgendein*
#: Item ein ``INSUFFICIENT`` — würde das gewinnen, wäre der Löschpfad tot
#: und aktiv widerlegte Aussagen blieben stehen (Codex-Review PR #1360, P1).
#:
#: Dass dabei kein Zufallstreffer mehr durchschlägt, sichert nicht diese
#: Rangfolge, sondern die Verdikte selbst: ``subject_mismatch`` — dieselbe
#: Zahl bei fremder Bezugsgruppe — ist seit #1356 kein Widerspruch mehr.
_DECISIVENESS = {
    EntailmentVerdict.SUPPORTED: 0,
    EntailmentVerdict.CONTRADICTED: 1,
    EntailmentVerdict.RELATED_ONLY: 2,
    EntailmentVerdict.INSUFFICIENT: 3,
}

#: Schweregrad — welcher Fakt entscheidet über den Satz?
#:
#: Bewusst eine andere Ordnung als :data:`_DECISIVENESS`. Für den einzelnen
#: Fakt ist ein Widerspruch das *aussagekräftigere* Urteil, für den Satz das
#: *schwerwiegendere*: ein einziger widerlegter Fakt entfernt ihn, ein
#: unbelegbarer kennzeichnet ihn nur.
_SEVERITY = {
    EntailmentVerdict.SUPPORTED: 0,
    EntailmentVerdict.RELATED_ONLY: 1,
    EntailmentVerdict.INSUFFICIENT: 1,
    EntailmentVerdict.CONTRADICTED: 2,
}


def _best_verdict(
    probe: str,
    evidence_pool: Sequence[Dict[str, Any]],
    *,
    judge: Optional[EntailmentJudge] = None,
) -> EntailmentResult:
    """Das aussagekräftigste Urteil, das irgendein Item des Pools hergibt."""
    best: Optional[EntailmentResult] = None
    for item in evidence_pool:
        result = classify_evidence(probe, item, judge=judge)
        if result.verdict is EntailmentVerdict.SUPPORTED:
            return result
        if best is None or _DECISIVENESS[result.verdict] < _DECISIVENESS[best.verdict]:
            best = result
    return best or EntailmentResult(
        EntailmentVerdict.INSUFFICIENT, "keine Evidence geprüft"
    )


def _worst_fact_verdict(
    sentence: str,
    evidence_pool: Sequence[Dict[str, Any]],
    *,
    judge: Optional[EntailmentJudge] = None,
) -> Optional[FactOutcome]:
    """Das schwerwiegendste Urteil über die Zahlenfakten eines Satzes.

    ``None`` heißt: der Satz trägt keine prüfbare Zahl, oder jede seiner
    Zahlen ist belegt. Geprüft wird pro Fakt, nicht pro Satz — ein Satz mit
    drei Quoten darf nicht daran scheitern, dass eine Quelle eine davon einer
    fremden Bezugsgruppe zuordnet.

    Zurück kommt nicht nur das Urteil, sondern auch der Fakt, der es ausgelöst
    hat, und wie viele Zahlen des Satzes belegt sind (Issue #1492) — sonst
    nennt die Beanstandung den Satz, aber nicht den Grund.
    """
    worst: Optional[FactOutcome] = None
    supported = 0
    checked = 0
    pending: List[tuple[EntailmentResult, NumericFact]] = []
    for fact in extract_numeric_facts(sentence):
        checked += 1
        result = _best_verdict(_fact_probe(fact), evidence_pool, judge=judge)
        if result.verdict is EntailmentVerdict.SUPPORTED:
            supported += 1
            continue
        pending.append((result, fact))

    for result, fact in pending:
        if worst is None or _SEVERITY[result.verdict] > _SEVERITY[worst.verdict]:
            worst = FactOutcome(
                result=result, fact=fact, supported=supported, checked=checked
            )
    return worst


def _reject_sentence(
    sentence: str,
    result: "FactOutcome",
    *,
    block_index: int,
    rejected: List["RejectedStatement"],
    enumeration_anchors: List[tuple[int, int]],
) -> None:
    """Protokolliert einen entfernten Satz und merkt seine Zählposition.

    Beginnt der Satz eine ausgeschriebene Aufzählung, muss der Rest des
    Absatzes danach lückenlos weiterzählen — sonst bleibt ein sichtbarer
    Sprung stehen ("Erstens … Zweitens … Viertens").
    """
    rejected.append(
        RejectedStatement(
            text=sentence.strip(),
            verdict=result.verdict,
            reason=result.reason,
            block_index=block_index,
        )
    )
    ordinal = _leading_ordinal(sentence)
    if ordinal is not None:
        enumeration_anchors.append((block_index, ordinal))


def prose_gate_decisions(
    prose_entries: Sequence[Any],
    truncate: Callable[[str, int], str],
) -> List[Dict[str, Any]]:
    """Protokolliert die Ausgänge der Fließtext-Prüfung auditierbar.

    Slice 7 (Audit Trail): Gate-Routing und Fließtext-Beanstandungen sind
    Degradation-Entscheidungen — der leere ``degradation_log`` bei 17
    entfernten Aussagen (``report_06f654800817``) war eine Erfassungslücke,
    keine Absicht.

    Issue #1356: entfernt wird nur noch bei aktivem Widerspruch, der Regelfall
    ist die im Text belassene, markierte Aussage. Beide landen in den
    Hypothesen; ein Audit muss sie trotzdem unterscheiden können. Das leistet
    die ``violation`` — ``action`` bleibt für beide gleich, damit bestehende
    Konsumenten des Logs nicht auf einen unbekannten Wert stoßen.

    ``prose_entries`` sind die Paare aus ``_pending_prose_hypotheses``:
    Hypothesen-Dict und das Statement, aus dem es entstanden ist.
    """
    decisions: List[Dict[str, Any]] = []
    for hypothesis, statement in prose_entries:
        if not isinstance(hypothesis, dict):
            continue
        removed = isinstance(statement, RejectedStatement)
        decisions.append({
            "claim_id": str(hypothesis.get("hypothesis_id") or "<no-id>"),
            "violation": (
                "prose_fact_contradicted" if removed else "prose_fact_unverified"
            ),
            "action": "moved_to_hypotheses",
            "detail": truncate(
                str(hypothesis.get("hypothesis_text") or ""), 500
            ) or (
                "Fließtext-Aussage steht im Widerspruch zur Quelle und wurde entfernt."
                if removed
                else "Fließtext-Aussage ohne deckende Evidence im Text markiert."
            ),
        })
    return decisions


def verify_prose(
    content: str,
    evidence_pool: Sequence[Dict[str, Any]],
    *,
    judge: Optional[EntailmentJudge] = None,
) -> VerifiedProse:
    """Prüft quantitative Aussagen des Fließtexts gegen die Evidence.

    Ein Satz bleibt unverändert, wenn jeder seiner numerischen Fakten von
    mindestens einem Evidence-Item mit ``SUPPORTED`` getragen wird. Findet
    sich für einen Fakt kein Beleg, bleibt der Satz stehen und wird mit
    :data:`UNVERIFIED_MARKER` gekennzeichnet. Nur wenn eine Quelle aktiv
    widerspricht, wird der Satz entfernt. Beide Fälle wandern zusätzlich in
    die Hypothesen — der Aufrufer routet sie über :attr:`VerifiedProse.flagged`.

    Ohne Evidence-Pool bleibt der Text unverändert: eine Prüfung ohne
    Vergleichsbasis darf nicht als bestandene Prüfung gelten und erst recht
    nicht den halben Bericht löschen.
    """
    if not content or not evidence_pool:
        return VerifiedProse(content=content or "")

    rejected: List[RejectedStatement] = []
    unverified: List[UnverifiedStatement] = []
    out_lines: List[str] = []
    renumber_anchors: List[tuple[int, str]] = []
    #: Zeilenindex und Zählposition jedes entfernten Aufzählungspunkts.
    enumeration_anchors: List[tuple[int, int]] = []
    in_fence = False

    for line in content.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence or _is_structural(line):
            out_lines.append(line)
            continue

        prefix_match = _LIST_PREFIX.match(line)
        prefix = prefix_match.group(1) if prefix_match else ""
        body = prefix_match.group(2) if prefix_match else line
        # Marker eines früheren Durchlaufs abziehen, bevor segmentiert wird —
        # sonst wird "[Beleg fehlt]" hinter dem Satzpunkt zu einem eigenen
        # Fragment und der Satz bekommt beim zweiten Lauf einen zweiten Marker.
        body = _strip_marker(body)

        sentences = split_sentences(body)
        if not sentences:
            out_lines.append(line)
            continue

        kept: List[str] = []
        for sentence in sentences:
            worst = _worst_fact_verdict(sentence, evidence_pool, judge=judge)
            if worst is None:
                kept.append(sentence)
                continue

            if worst.verdict is EntailmentVerdict.CONTRADICTED:
                _reject_sentence(
                    sentence,
                    worst,
                    block_index=len(out_lines),
                    rejected=rejected,
                    enumeration_anchors=enumeration_anchors,
                )
                continue

            unverified.append(
                UnverifiedStatement(
                    text=sentence.strip(),
                    verdict=worst.verdict,
                    reason=worst.reason,
                    block_index=len(out_lines),
                )
            )
            kept.append(_mark_unverified(sentence))

        rebuilt = " ".join(part for part in kept if part.strip())
        if rebuilt.strip():
            out_lines.append(f"{prefix}{rebuilt}")
            continue

        # Die Zeile hat ihren gesamten Inhalt verloren. Sie verschwindet
        # vollständig — ein zurückbleibender Aufzählungsmarker wäre schlimmer
        # als eine fehlende Zeile (#1356). Nummerierte Listen ziehen danach
        # ihre Zählung nach.
        ordered = _ORDERED_ITEM.match(line)
        if ordered:
            renumber_anchors.append((len(out_lines), ordered.group("indent")))

    for anchor, indent in renumber_anchors:
        _renumber_block(out_lines, anchor, indent)

    for anchor, removed_ordinal in enumeration_anchors:
        _renumber_enumeration(out_lines, anchor, removed_ordinal)

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines)).strip()
    return VerifiedProse(content=cleaned, rejected=rejected, unverified=unverified)

