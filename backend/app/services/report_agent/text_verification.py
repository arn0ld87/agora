"""Faktenprüfung des sichtbaren Fließtexts.

Bis hierher war die Pipeline asymmetrisch: Claims wurden gegen Evidence
geprüft, der sichtbare Prosatext nicht. Der E2E-Lauf gegen
``sim_7058c126da03`` machte die Folge sichtbar — die Aussage

    "61 Prozent der Lehrkräfte bewerteten die zusätzliche Lernhilfe positiv
     und berichteten von einer Zeitersparnis …"

wurde vom Entailment korrekt verworfen, erzeugte null Claims und landete bei
den Hypothesen. Im gelesenen Report stand sie trotzdem, weil der Abschnitt
die rohe LLM-Prosa ist und die Claim-Extraktion nur ein nachgelagertes
Nebenprodukt.

Diese Stufe schließt die Lücke an derselben Engine, die auch die Claims
prüft: Jeder numerische Fakt im Fließtext wird gegen die Evidence gehalten.

Bewusst eng: Nur Sätze mit numerischen Fakten werden geprüft. Analytische
Prosa ohne Zahlenbehauptung bleibt unangetastet — sie ist Einordnung, nicht
Faktenbehauptung, und wird über das Confidence-Gating der Claims geführt.

Issue #1356 — was diese Stufe **nicht** mehr tut
-------------------------------------------------

Ein vollständiger Referenzlauf (7 Sektionen) zeigte, dass die Prüfung mehr
zerstörte als sie sicherte: 28 Aussagen wurden entfernt, die weit
überwiegende Mehrheit davon belegt. Drei Verhaltensänderungen folgen daraus.

**Nur ein Widerspruch löscht.** ``INSUFFICIENT`` heißt "kein passendes
Evidence-Item gefunden", nicht "falsch". Wer Text löscht, weil er ihn nicht
prüfen konnte, verliert genau die konkreten Zahlen, für die der Bericht
gelesen wird. Nicht belegbare Aussagen bleiben deshalb stehen und tragen
sichtbar :data:`UNVERIFIED_MARKER`; in die Hypothesen wandern sie trotzdem.

**Struktur ist unantastbar.** ``(?<=[.!?])\\s+`` hielt Ordinalzahlen für
Satzenden. Aus "(3. bis 14. Juni mit 14 Ärzten …) wichen 38 Empfehlungen ab"
wurden zwei Fragmente; das zweite trug die Zahlen und fiel, übrig blieb ein
Satz, der mitten in der Datumsklammer abbrach. Dieselbe Zeile erzeugte die
leeren Listenmarker: "1. Erfolgreicher Wiederholungstest …" zerfiel in "1."
und den Rest, der Rest fiel, der Marker blieb. Deshalb werden Aufzählungs-
präfixe vor der Zerlegung abgetrennt und Ordinalzahlen wie Abkürzungen als
Satzgrenze ausgeschlossen.

**Das beste Urteil zählt, nicht das erste.** Geprüft wird pro numerischem
Fakt gegen den gesamten Pool. Ein beliebiges Item, das denselben Zahlenwert
zufällig einer anderen Bezugsgruppe zuschreibt, kippt damit keinen Satz
mehr, dessen übrige Zahlen sauber belegt sind.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..evidence_entailment import (
    ENUMERATION_WORDS,
    EntailmentJudge,
    EntailmentResult,
    EntailmentVerdict,
    NumericFact,
    classify_evidence,
    extract_numeric_facts,
)

#: Sichtbare Kennzeichnung einer Aussage, für die sich kein Beleg finden ließ.
#: Bewusst als Klartext und nicht als HTML-Tag: der Abschnitt wird auch als
#: rohe ``section_XX.md`` gelesen, und dort muss die Einschränkung ohne
#: Renderer erkennbar sein.
UNVERIFIED_MARKER = "[Beleg fehlt]"


@dataclass
class FlaggedStatement:
    """Eine Faktenbehauptung, die die Prüfung nicht bestanden hat."""

    text: str
    verdict: EntailmentVerdict
    reason: str
    block_index: int = 0

    def as_hypothesis(self, index: int) -> Dict[str, Any]:
        # ReportSectionHypothesisModel.hypothesis_id erzwingt
        # ^hypothesis_\d{2,}$ — ein sprechendes Präfix ("hypothesis_text_01")
        # lässt die gesamte EvidenceMap-Validierung scheitern.
        return {
            "hypothesis_id": f"hypothesis_{index:02d}",
            "hypothesis_text": self.text[:1000],
            "rationale": (
                f"{self._rationale_prefix}: {self.reason} "
                f"(Urteil: {self.verdict.value})."
            ),
            "suggested_evidence": [
                "Quelle mit übereinstimmender Zahl, Bezugsgruppe und Aussage nachreichen."
            ],
        }

    @property
    def _rationale_prefix(self) -> str:
        return "Aus dem Fließtext entfernt"


@dataclass
class RejectedStatement(FlaggedStatement):
    """Aus dem Fließtext entfernt — eine Quelle widerspricht ihr."""


@dataclass
class UnverifiedStatement(FlaggedStatement):
    """Im Fließtext belassen und markiert — es fand sich kein Beleg."""

    @property
    def _rationale_prefix(self) -> str:
        return "Im Fließtext als unbelegt markiert"


@dataclass
class VerifiedProse:
    content: str
    rejected: List[RejectedStatement] = field(default_factory=list)
    unverified: List[UnverifiedStatement] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.rejected or self.unverified)

    @property
    def flagged(self) -> List[FlaggedStatement]:
        """Alles, was in die Hypothesen gehört — entfernt wie markiert."""
        return [*self.rejected, *self.unverified]


#: Zeilen, die keine Fließtextaussage sind und deshalb nicht geprüft werden:
#: Zitatblöcke tragen fremde Rede, Aufzählungsmarker und Fettschrift-Label
#: sind Struktur.
_QUOTE_PREFIXES = (">", "|")

#: Aufzählungs- und Nummerierungspräfix einer Listenzeile. Es wird vor der
#: Satzzerlegung abgetrennt und danach unverändert wieder vorangestellt —
#: sonst wird "1." zum eigenen Satz und überlebt seinen eigenen Inhalt.
_LIST_PREFIX = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+)(.*)$")

#: Nummerierte Listenzeile, für den Renummerierungs-Nachlauf.
_ORDERED_ITEM = re.compile(r"^(?P<indent>\s*)(?P<number>\d+)(?P<sep>[.)])(?P<space>\s+)(?P<rest>.*)$")

#: Kanonische Schreibweise der ausgeschriebenen Aufzählung, in Zählreihenfolge.
#: Aus dieser Sequenz wird nach einer Entfernung neu gesetzt.
_ENUMERATION_SEQUENCE = (
    "Erstens",
    "Zweitens",
    "Drittens",
    "Viertens",
    "Fünftens",
    "Sechstens",
    "Siebtens",
    "Achtens",
    "Neuntens",
    "Zehntens",
)

#: Wort → Position, inklusive der Schreibvarianten aus ``ENUMERATION_WORDS``.
#: Die Sequenz oben ist die Ausgabeform, diese Tabelle die Lesart.
_ENUMERATION_ORDINALS = {
    "erstens": 0,
    "zweitens": 1,
    "drittens": 2,
    "viertens": 3,
    "fünftens": 4,
    "fuenftens": 4,
    "sechstens": 5,
    "siebtens": 6,
    "siebentens": 6,
    "achtens": 7,
    "neuntens": 8,
    "zehntens": 9,
}

#: Ein Aufzählungswort am Satzanfang — am Zeilenanfang oder hinter einem
#: Satzzeichen. Gruppe 1 ist der Vorlauf und bleibt unverändert stehen.
_ENUMERATION_AT_SENTENCE_START = re.compile(
    r"(^|[.!?]['\"\)\]]?\s+)(" + "|".join(sorted(ENUMERATION_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

#: Code-Fence. Innerhalb eines Blocks wird nichts geprüft und nichts entfernt.
_FENCE = re.compile(r"^\s*(```|~~~)")

#: Abkürzungen, deren Punkt kein Satzende ist. Einzelne Buchstaben ("z. B.",
#: "u. a.") deckt die Längenprüfung in :func:`_is_false_boundary` ab.
_ABBREVIATIONS = frozenset({
    "bzw", "ca", "vgl", "ggf", "evtl", "inkl", "exkl", "max", "min",
    "nr", "abs", "art", "bspw", "etc", "usw", "sog", "insb", "zzgl",
    "jan", "feb", "mrz", "apr", "jun", "jul", "aug", "sep", "okt", "nov", "dez",
})

#: Monatsnamen. Ein großgeschriebenes Wort hinter einer Zahl beendet den Satz
#: normalerweise ("umfasste 14. Danach …"); ein Monat tut das nicht ("14. Juni").
_MONTHS = frozenset({
    "januar", "februar", "märz", "maerz", "april", "mai", "juni", "juli",
    "august", "september", "oktober", "november", "dezember",
    "jan", "feb", "mrz", "apr", "jun", "jul", "aug", "sep", "sept", "okt", "nov", "dez",
})


def is_markup_or_quote_line(stripped: str) -> bool:
    """Leere Zeile, Zitatblock-Präfix oder vollständig getaggte Zeile.

    Gemeinsame Teilprüfung für ``_is_structural`` (Fließtext-Validator, hier)
    und ``is_claim_candidate`` (Claim-Extraktion in ``sections.py``,
    Issue #1316) — beide verwerfen dieselben drei Zeilenformen, bevor sie
    ihre je eigene Zusatzlogik anwenden. ``stripped`` erwartet bereits
    getrimmten Text.
    """
    if not stripped:
        return True
    if stripped.startswith(_QUOTE_PREFIXES):
        return True
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    return False


def _is_structural(line: str) -> bool:
    stripped = line.strip()
    if is_markup_or_quote_line(stripped):
        return True
    return bool(re.fullmatch(r"\*\*[^*]+\*\*:?", stripped))


def _is_ordinal_boundary(text: str, dot_index: int, token_start: int) -> bool:
    """Ist die Ziffernfolge vor dem Punkt eine Ordinalzahl statt eines Satzendes?

    Eine Zahl allein entscheidet das nicht — ``Die Stichprobe umfasste 14.``
    endet einen Satz, ``am 14. Juni`` nicht. Würde jede Ziffer die Satzgrenze
    unterdrücken, verschmölzen zwei Sätze zu einer Prüfeinheit, und ein
    widerlegter Fakt im zweiten risse den ersten mit heraus (Codex-Review
    PR #1360, P2). Entschieden wird deshalb am Kontext:

    * Ziffer am Zeilenanfang — ein Aufzählungsmarker ("1. Erfolgreicher …").
    * Folgewort kleingeschrieben — Ordinalzahl ("3. bis 14. Juni").
    * Folgewort ist ein Monatsname — Datum ("14. Juni").

    Sonst ist der Punkt ein Satzende, auch nach einer Zahl.
    """
    if not text[:token_start].strip():
        return True
    following = re.match(r"\s*(\S+)", text[dot_index + 1:])
    if not following:
        return False
    word = following.group(1).strip(",.;:()\"'„»")
    if not word:
        return False
    if word[:1].islower():
        return True
    return word.lower().rstrip(".") in _MONTHS


def _is_false_boundary(text: str, dot_index: int) -> bool:
    """Steht der Punkt an ``dot_index`` für eine Abkürzung statt ein Satzende?

    Drei Fälle, alle im Referenzlauf belegt: eine Ordinalzahl ("14. Juni",
    "3. bis"), eine Listennummer ("1. Erfolgreicher …") und eine Abkürzung
    ("z. B.", "Nr. 3"). Jeder von ihnen zerlegte einen intakten Satz in zwei
    Fragmente, von denen eines die Zahlen trug und deshalb verschwand.
    """
    match = re.search(r"(\S+)$", text[:dot_index])
    if not match:
        return False
    # Öffnende Klammern und Anführungszeichen gehören nicht zum Token:
    # in "(3. bis 14. Juni" ist die Ordinalzahl sonst "(3" und damit keine
    # Ziffer mehr — genau daran zerbrach der Satz im Referenzlauf.
    token = match.group(1).lstrip("([{\"'„»‚‹")
    if not token:
        return False
    if token.isdigit():
        # ``token_start`` zeigt hinter die abgestreiften Klammern — nur so
        # erkennt die Zeilenanfangs-Prüfung einen echten Aufzählungsmarker.
        token_start = match.end() - len(token)
        return _is_ordinal_boundary(text, dot_index, token_start)
    # Nur *einzelne* Buchstaben sind Abkürzungspunkte ("z. B.", "u. a.").
    # Zwei Buchstaben deckt die Liste ab — "ab", "an", "zu" sind gewöhnliche
    # Wörter und dürfen ein Satzende nicht verhindern.
    if len(token) == 1 and token.isalpha():
        return True
    return token.lower() in _ABBREVIATIONS


def split_sentences(line: str) -> List[str]:
    """Zerlegt eine Zeile in Sätze, ohne Ordinalzahlen zu zerreißen.

    Gibt die Sätze getrimmt zurück; leere Fragmente entfallen. Ein falsch
    zusammengelassener Satz kostet höchstens Prüfschärfe, ein falsch
    getrennter dagegen zerstört den gelesenen Text — die Heuristik ist
    deshalb bewusst konservativ.
    """
    sentences: List[str] = []
    start = 0
    for match in re.finditer(r"[.!?]+\s+", line):
        if _is_false_boundary(line, match.start()):
            continue
        chunk = line[start:match.end()].strip()
        if chunk:
            sentences.append(chunk)
        start = match.end()
    tail = line[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


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


#: Der Marker als eigenständiges Vorkommen, inklusive führendem Leerraum.
_MARKER_RE = re.compile(rf"\s*{re.escape(UNVERIFIED_MARKER)}")


def _strip_marker(text: str) -> str:
    """Entfernt bereits gesetzte Marker.

    Die Prüfung muss idempotent sein: ein zweiter Durchlauf über denselben
    Text darf keinen zweiten Marker anhängen. Da die Segmentierung nach dem
    Satzpunkt trennt, landet ein angehängter Marker sonst in einem eigenen
    Fragment, der Satz selbst gilt wieder als unmarkiert und bekommt einen
    weiteren.
    """
    return _MARKER_RE.sub("", text)


def _mark_unverified(sentence: str) -> str:
    """Hängt den Marker an, ohne ihn zu verdoppeln."""
    return f"{_strip_marker(sentence).rstrip()} {UNVERIFIED_MARKER}"


def _renumber_block(lines: List[str], anchor: int, indent: str) -> None:
    """Nummeriert den Listenblock um ``anchor`` herum neu ab 1.

    Läuft nur über Blöcke, aus denen tatsächlich eine Zeile entfernt wurde.
    Eine intakte Liste, die bewusst bei einer anderen Zahl beginnt, bleibt
    damit unangetastet.
    """
    def belongs(index: int) -> bool:
        if not 0 <= index < len(lines):
            return False
        match = _ORDERED_ITEM.match(lines[index])
        return bool(match) and match.group("indent") == indent

    start = anchor
    while belongs(start - 1):
        start -= 1
    end = anchor
    while belongs(end):
        end += 1

    counter = 1
    for index in range(start, end):
        match = _ORDERED_ITEM.match(lines[index])
        if not match:
            continue
        lines[index] = (
            f"{match.group('indent')}{counter}{match.group('sep')}"
            f"{match.group('space')}{match.group('rest')}"
        )
        counter += 1


def _leading_ordinal(sentence: str) -> Optional[int]:
    """Zählposition, falls der Satz mit einem Aufzählungswort beginnt."""
    match = re.match(r"\s*([A-Za-zÄÖÜäöüß]+)", sentence)
    if not match:
        return None
    return _ENUMERATION_ORDINALS.get(match.group(1).lower())


def _paragraph_bounds(lines: List[str], anchor: int) -> tuple[int, int]:
    """Grenzen des Absatzes um ``anchor``; Leerzeilen trennen.

    Eine Aufzählung endet am Absatzende. Zwei durch eine Leerzeile getrennte
    Blöcke sind zwei Aufzählungen — der zweite darf nicht umgezählt werden,
    nur weil im ersten etwas fehlte.
    """
    start = min(anchor, len(lines))
    while start > 0 and lines[start - 1].strip():
        start -= 1
    end = min(anchor, len(lines) - 1) if lines else 0
    while end + 1 < len(lines) and lines[end + 1].strip():
        end += 1
    return start, min(end + 1, len(lines))


def _renumber_enumeration(lines: List[str], anchor: int, removed_ordinal: int) -> None:
    """Zählt die ausgeschriebene Aufzählung des Absatzes lückenlos neu.

    Der Referenzlauf ``report_cc2ef45da5e9`` hinterließ "Erstens … Zweitens …
    Viertens": der dritte Punkt war als widerlegt entfernt worden, die Zählung
    blieb stehen. Für den Leser ist das ein Fehler im Bericht — er kann nicht
    wissen, dass dort etwas geprüft und verworfen wurde. Nummerierte Listen
    schützt :func:`_renumber_block` seit #1356 genauso.

    Der Startwert ist bewusst nicht fest 1: ein Absatz, der bei "Zweitens"
    einsetzt, weil der erste Punkt darüber steht, soll dort bleiben. Gezählt
    wird ab dem kleinsten Wert, der im Absatz vorkam — das entfernte Element
    eingeschlossen, sonst rutschte die Aufzählung nach oben, wenn ausgerechnet
    ihr erster Punkt wegfiel.
    """
    start, end = _paragraph_bounds(lines, anchor)
    positions: List[tuple[int, re.Match[str]]] = [
        (index, match)
        for index in range(start, end)
        for match in _ENUMERATION_AT_SENTENCE_START.finditer(lines[index])
    ]
    if not positions:
        return

    found = [
        _ENUMERATION_ORDINALS[match.group(2).lower()] for _, match in positions
    ]
    counter = min(min(found), removed_ordinal)
    if counter + len(positions) > len(_ENUMERATION_SEQUENCE):
        # Mehr Punkte, als die Sequenz Wörter kennt. Lieber die vorhandene
        # Zählung stehen lassen als sie mit einem IndexError abzubrechen.
        return

    for index in range(start, end):
        def _replace(match: re.Match[str]) -> str:
            nonlocal counter
            word = _ENUMERATION_SEQUENCE[counter]
            counter += 1
            return f"{match.group(1)}{word}"

        lines[index] = _ENUMERATION_AT_SENTENCE_START.sub(_replace, lines[index])


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
            facts = extract_numeric_facts(sentence)
            if not facts:
                kept.append(sentence)
                continue

            worst: Optional[EntailmentResult] = None
            for fact in facts:
                result = _best_verdict(_fact_probe(fact), evidence_pool, judge=judge)
                if result.verdict is EntailmentVerdict.SUPPORTED:
                    continue
                if worst is None or _SEVERITY[result.verdict] > _SEVERITY[worst.verdict]:
                    worst = result

            if worst is None:
                kept.append(sentence)
                continue

            if worst.verdict is EntailmentVerdict.CONTRADICTED:
                rejected.append(
                    RejectedStatement(
                        text=sentence.strip(),
                        verdict=worst.verdict,
                        reason=worst.reason,
                        block_index=len(out_lines),
                    )
                )
                ordinal = _leading_ordinal(sentence)
                if ordinal is not None:
                    enumeration_anchors.append((len(out_lines), ordinal))
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


__all__ = [
    "UNVERIFIED_MARKER",
    "FlaggedStatement",
    "RejectedStatement",
    "UnverifiedStatement",
    "VerifiedProse",
    "is_markup_or_quote_line",
    "prose_gate_decisions",
    "split_sentences",
    "verify_prose",
]
