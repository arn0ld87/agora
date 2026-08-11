"""Zweite Stufe des Evidence-Bindings: Beweist die Evidence den Claim?

Der `evidence_binder` beantwortet mit Cosine-Similarity nur die Frage
"handeln beide Texte vom selben Thema?". Das ist eine Retrieval-Frage,
keine Beweisfrage. Dieses Modul beantwortet die zweite Frage und trennt
damit ``retrieval_score`` sauber von ``supports_claim``.

Vier Urteile:

``SUPPORTED``
    Die Evidence trägt den Claim. Nur hier darf ``supports_claim=True``
    gesetzt werden und nur hier darf die Confidence steigen.
``CONTRADICTED``
    Die Evidence widerspricht dem Claim (falsche Zahl, gegenläufige
    Richtung). Wird als Contradiction-Evidence behandelt.
``RELATED_ONLY``
    Gleiches Thema, aber kein Beleg. Erhöht die Confidence nie.
``INSUFFICIENT``
    Zu wenig Überschneidung für ein Urteil.

Deterministische Checks haben Vorrang: sobald ein Claim eine Zahl, eine
Bezugsgruppe oder eine Mengenaussage trägt, entscheidet die Regel — nicht
das Embedding und nicht der optionale LLM-Judge. Ein LLM-Judge darf ein
regelbasiertes SUPPORTED nur abschwächen, nie erzeugen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence


class EntailmentVerdict(str, Enum):
    """Urteil der zweiten Binding-Stufe."""

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    RELATED_ONLY = "RELATED_ONLY"
    INSUFFICIENT = "INSUFFICIENT"


class FactModality(str, Enum):
    """Ist die Zahl ein berichteter Ist-Wert oder eine Zielvorgabe?

    "70 % der Lehrkräfte *sollen* geschult sein" ist eine Anforderung, kein
    gemessener Zustimmungswert. Diese Unterscheidung verhindert genau die
    Verfälschung aus dem Referenzlauf.
    """

    FACTUAL = "factual"
    NORMATIVE = "normative"


@dataclass(frozen=True)
class NumericFact:
    """Eine Zahl zusammen mit ihrer Bezugsgruppe und ihrer Aussage."""

    value: float
    unit: str
    subject: str
    predicate: str
    modality: FactModality = FactModality.FACTUAL
    raw: str = ""


@dataclass
class EntailmentResult:
    verdict: EntailmentVerdict
    reason: str
    matched_fact: Optional[NumericFact] = None
    claim_fact: Optional[NumericFact] = None
    checks: List[str] = field(default_factory=list)

    @property
    def supports(self) -> bool:
        return self.verdict is EntailmentVerdict.SUPPORTED


# ---------------------------------------------------------------------------
# Numerische Faktenextraktion
# ---------------------------------------------------------------------------

_PERCENT_RE = re.compile(
    r"(?P<value>\d{1,3}(?:[.,]\d+)?)\s*(?:%|Prozent|percent)\s*"
    r"(?:der|des|von\s+den|von|aller|of)?\s*",
    re.IGNORECASE,
)

_ABSOLUTE_RE = re.compile(
    r"(?P<value>\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)\s+"
    r"(?P<noun>[A-ZÄÖÜ][\wÄÖÜäöüß-]+)",
)

# Kleingeschriebene Wörter, die eine Nominalphrase nicht beenden.
_SUBJECT_CONNECTORS = {"und", "bzw", "sowie", "oder", "der", "die", "das", "den"}

_NORMATIVE_MARKERS = (
    "soll",
    "sollen",
    "sollte",
    "sollten",
    "muss",
    "müssen",
    "geplant",
    "vorgesehen",
    "angestrebt",
    "ziel ist",
    "verpflichtend",
    "should",
    "must",
    "planned",
    "required",
)

_MAJORITY_MARKERS = (
    "mehrheitlich",
    "die mehrheit",
    "mehrheit der",
    "überwiegend",
    "die meisten",
    "großteil",
    "grossteil",
    "majority",
    "most of",
)

_MINORITY_MARKERS = (
    "eine minderheit",
    "wenige",
    "ein kleiner teil",
    "minority",
)

_STOPWORDS = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "eines",
    "einem", "einen", "und", "oder", "aber", "bei", "von", "vom", "zu", "zum",
    "zur", "mit", "für", "auf", "in", "im", "an", "am", "als", "auch", "ist",
    "sind", "war", "waren", "wird", "werden", "hat", "haben", "sich", "nicht",
    "mindestens", "etwa", "rund", "ca", "prozent", "the", "of", "and", "a", "to",
}


def _tokens(text: str) -> List[str]:
    return [t for t in re.split(r"\W+", (text or "").lower()) if t and t not in _STOPWORDS]


def _content_tokens(text: str) -> set[str]:
    return {t for t in _tokens(text) if len(t) > 3}


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


#: Englische Verben, die den Übergang von Bezugsgruppe zu Prädikat markieren.
#: Ohne NLP-Tagger reicht eine kleine Liste häufiger Report-Verben — ein
#: fehlendes Verb führt höchstens zu einem längeren Subjekt, nie zu einem
#: Fehlurteil (die Zahl-Bezugsgruppe-Prüfung greift trotzdem).
_EN_SUBJECT_VERBS = frozenset({
    "rated", "reported", "stated", "said", "believed", "indicated",
    "found", "noted", "mentioned", "claimed", "expressed", "gave",
    "showed", "saw", "experienced", "felt", "think", "thought",
    "consider", "considered", "view", "viewed", "judge", "judged",
})


def _split_subject_predicate(tail: str) -> tuple[str, str]:
    """Trennt die Bezugsgruppe vom Prädikat.

    Deutsche Nomen sind großgeschrieben: die Nominalphrase läuft bis zum
    ersten kleingeschriebenen Wort, das kein Bindewort ist. Für englische
    Seeds (keine Großschreibung-Pflicht) fällt diese Heuristik leer aus —
    dann übernimmt ein Fallback, der die Bezugsgruppe bis zum ersten
    bekannten Report-Verb nimmt. Without that, ``extract_numeric_facts``
    liefert für englische Sätze keine Fakten und die Fließtext-Prüfung
    überspringt sie still (Handover P2.7).
    """
    words = tail.split()
    subject_parts: List[str] = []
    idx = 0
    for idx, word in enumerate(words):
        bare = word.strip(",.;:()").lower()
        if word[:1].isupper() or bare in _SUBJECT_CONNECTORS:
            # Ein Bindewort zählt nur mit, wenn danach wieder ein Nomen folgt.
            if bare in _SUBJECT_CONNECTORS and not subject_parts:
                continue
            subject_parts.append(word)
            continue
        break
    else:
        idx = len(words)

    # Trailing-Bindewörter gehören nicht zum Subjekt ("Eltern und" → "Eltern").
    while subject_parts and subject_parts[-1].strip(",.;:()").lower() in _SUBJECT_CONNECTORS:
        subject_parts.pop()
        idx -= 1

    subject = " ".join(subject_parts).strip(",.;:() ")
    predicate = " ".join(words[idx:]).strip(",.;:() ")

    # Englischer Fallback: keine Großschreibung → deutscher Pfad leer.
    if not subject and words:
        subject_parts = []
        end_idx = len(words)
        for en_idx, word in enumerate(words):
            bare = word.strip(",.;:()").lower()
            if bare in _EN_SUBJECT_VERBS:
                end_idx = en_idx
                break
            subject_parts.append(word)
        if subject_parts:
            subject = " ".join(subject_parts).strip(",.;:() ")
            predicate = " ".join(words[end_idx:]).strip(",.;:() ")

    return subject, predicate


def _modality_of(predicate: str) -> FactModality:
    lowered = f" {predicate.lower()} "
    if any(f" {marker} " in lowered or lowered.startswith(f" {marker} ") for marker in _NORMATIVE_MARKERS):
        return FactModality.NORMATIVE
    return FactModality.FACTUAL


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p for p in parts if p.strip()]


#: Ab wie vielen Inhaltswörtern der Teil rechts der Zahl als eigenständige
#: Aussage gilt. Darunter ist er ein Fragment ("", "geführt") und das Vorfeld
#: trägt die Aussage.
_TAIL_PREDICATE_MIN_TOKENS = 2


def _full_predicate(prefix: str, tail_predicate: str) -> str:
    """Wählt die Satzhälfte, die die Aussage trägt.

    Deutsch besetzt das Vorfeld frei: "Auf der Personalliste des Trägers
    stehen 31 Honorarkräfte." trägt seine gesamte Aussage *links* der Zahl.
    Wer nur ``sentence[match.end():]`` liest, behält dort ein leeres Prädikat
    und misst anschließend eine Deckung von 0.00 gegen eine Evidence, die
    denselben Satz in anderer Wortstellung enthält — der Satz wird als
    Widerspruch aus dem Fließtext entfernt (#1209/#1217).

    Das Vorfeld wird deshalb **nur ergänzend** herangezogen, nicht generell:
    trägt der Teil rechts der Zahl bereits eine Aussage, bleibt er allein
    maßgeblich. Sonst wanderte Rahmensprache ("Die Datenlage zeigt, dass …")
    ins Prädikat, blähte die Claim-Seite von :func:`coverage_ratio` auf und
    machte belegte Aussagen fälschlich zu ``predicate_overreach``.

    Die Bezugsgruppe bleibt außen vor: sie wird aus dem Tail bestimmt und
    separat über :func:`subjects_match` geprüft.
    """
    if len(_content_tokens(tail_predicate)) >= _TAIL_PREDICATE_MIN_TOKENS:
        return tail_predicate
    return " ".join(part for part in (prefix.strip(",.;:() "), tail_predicate) if part).strip()


def extract_numeric_facts(text: str) -> List[NumericFact]:
    """Extrahiert Zahlen samt Bezugsgruppe, Aussage und Modalität.

    Nur was sich einer Bezugsgruppe zuordnen lässt, wird zum ``NumericFact`` —
    eine nackte Zahl ohne Subjekt ist für den Faktencheck wertlos.
    """
    facts: List[NumericFact] = []
    for sentence in _sentences(text):
        for match in _PERCENT_RE.finditer(sentence):
            value = _parse_number(match.group("value"))
            if value is None:
                continue
            subject, tail = _split_subject_predicate(sentence[match.end():])
            if not subject:
                continue
            predicate = _full_predicate(sentence[: match.start()], tail)
            facts.append(
                NumericFact(
                    value=value,
                    unit="percent",
                    subject=subject,
                    predicate=predicate,
                    modality=_modality_of(predicate),
                    raw=sentence.strip(),
                )
            )
        if not any(f.raw == sentence.strip() for f in facts):
            for match in _ABSOLUTE_RE.finditer(sentence):
                value = _parse_number(match.group("value"))
                if value is None:
                    continue
                subject, tail = _split_subject_predicate(sentence[match.start("noun"):])
                if not subject:
                    continue
                predicate = _full_predicate(sentence[: match.start()], tail)
                facts.append(
                    NumericFact(
                        value=value,
                        unit="absolute",
                        subject=subject,
                        predicate=predicate,
                        modality=_modality_of(predicate),
                        raw=sentence.strip(),
                    )
                )
    return facts


# ---------------------------------------------------------------------------
# Vergleichs-Primitive
# ---------------------------------------------------------------------------


def _overlap_ratio(left: str, right: str) -> float:
    """Containment-Overlap: Anteil der kleineren Tokenmenge in der größeren."""
    a, b = _content_tokens(left), _content_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def coverage_ratio(claim_text: str, evidence_text: str) -> float:
    """Anteil der Claim-Aussage, der von der Evidence gedeckt ist.

    Bewusst asymmetrisch — und das ist der Punkt. ``_overlap_ratio`` misst
    Containment und liefert 1.0, sobald die Evidence *Teilmenge* des Claims
    ist. Genau so rutschte im E2E-Lauf durch:

        Seed:  "61 % der Lehrkräfte berichteten von Zeitersparnis …"
        Claim: "61 % der Lehrkräfte bewerteten die Lernhilfe positiv
                und berichteten von Zeitersparnis …"

    Der Seed steckt vollständig im Claim, also Containment 1.0 — obwohl der
    Claim eine zusätzliche, unbelegte Behauptung trägt. Die Deckungsrichtung
    muss umgekehrt sein: Was der Claim behauptet, muss in der Evidence stehen.
    Für obigen Fall ergibt das 0.56 statt 1.0.
    """
    claim_tokens = _content_tokens(claim_text)
    evidence_tokens = _content_tokens(evidence_text)
    if not claim_tokens:
        return 0.0
    if not evidence_tokens:
        return 0.0
    return len(claim_tokens & evidence_tokens) / len(claim_tokens)


def subjects_match(left: str, right: str) -> bool:
    """Bezugsgruppen-Vergleich mit leichter Stamm-Normalisierung.

    "Lehrkräfte" und "Lehrkraft" sind dieselbe Gruppe, "Lehrkräfte" und
    "Eltern" nicht.
    """
    def stems(value: str) -> set[str]:
        return {t[:6] for t in _tokens(value) if len(t) > 3}

    a, b = stems(left), stems(right)
    if not a or not b:
        return False
    return bool(a & b)


def _quantifier_direction(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    if any(marker in lowered for marker in _MAJORITY_MARKERS):
        return "majority"
    if any(marker in lowered for marker in _MINORITY_MARKERS):
        return "minority"
    return None


# ---------------------------------------------------------------------------
# Hauptklassifikation
# ---------------------------------------------------------------------------

#: Ab diesem Containment-Overlap gilt eine Aussage als dieselbe Aussage.
PREDICATE_MATCH_THRESHOLD = 0.5
#: Darunter besteht nicht einmal thematische Nähe.
TOPIC_MATCH_THRESHOLD = 0.2
#: Mindestanteil der Claim-Aussage, der von der Evidence gedeckt sein muss,
#: damit ein numerischer Fakt als übernommen gilt. Höchstens ein Viertel der
#: inhaltlichen Aussage darf über die Evidence hinausgehen.
#:
#: Am realen Fall kalibriert (E2E gegen sim_7058c126da03):
#:   0.56 — "61 % … bewerteten die Lernhilfe positiv UND berichteten von
#:           Zeitersparnis" gegen den Seed, der nur die Zeitersparnis belegt
#:   1.00 — "72 % der Schülerinnen und Schüler bewerteten die Lernhilfe
#:           positiv", wörtlich aus dem Seed
#: Der Schwellwert trennt diese beiden Fälle mit Abstand nach beiden Seiten.
PREDICATE_COVERAGE_THRESHOLD = 0.75

EntailmentJudge = Callable[[str, str], str]
"""Optionaler strukturierter Judge: (claim, evidence_text) -> Verdict-Name."""


def _evidence_text(item: Dict[str, Any]) -> str:
    parts = [str(item.get("snippet") or ""), str(item.get("quote") or ""), str(item.get("value") or "")]
    raw = item.get("raw")
    if isinstance(raw, dict):
        for key in ("content", "text", "snippet", "summary"):
            val = raw.get(key)
            if isinstance(val, str) and val:
                parts.append(val)
    elif isinstance(raw, str):
        parts.append(raw)
    return " ".join(p for p in parts if p).strip()


def classify_evidence(
    claim_text: str,
    evidence_item: Dict[str, Any],
    *,
    judge: Optional[EntailmentJudge] = None,
) -> EntailmentResult:
    """Entscheidet, ob ``evidence_item`` den Claim tatsächlich stützt.

    Reihenfolge ist bewusst: numerische und Mengen-Checks laufen zuerst und
    sind bindend. Der ``judge`` wird nur befragt, wenn die Regeln kein Urteil
    fällen konnten, und darf ein SUPPORTED nur verhindern, nie erzeugen.
    """
    claim = (claim_text or "").strip()
    evidence_text = _evidence_text(evidence_item)
    if not claim or not evidence_text:
        return EntailmentResult(EntailmentVerdict.INSUFFICIENT, "leerer Claim oder Evidence-Text")

    checks: List[str] = []
    claim_facts = extract_numeric_facts(claim)
    evidence_facts = extract_numeric_facts(evidence_text)
    topic_overlap = _overlap_ratio(claim, evidence_text)

    # --- Regel 1: Claim trägt eine Zahl ------------------------------------
    if claim_facts:
        checks.append("numeric_claim")
        for claim_fact in claim_facts:
            for ev_fact in evidence_facts:
                same_value = abs(claim_fact.value - ev_fact.value) < 0.001
                same_subject = subjects_match(claim_fact.subject, ev_fact.subject)
                predicate_overlap = _overlap_ratio(claim_fact.predicate, ev_fact.predicate)

                if same_value and same_subject:
                    if ev_fact.modality is FactModality.NORMATIVE and (
                        claim_fact.modality is FactModality.FACTUAL
                    ):
                        return EntailmentResult(
                            EntailmentVerdict.CONTRADICTED,
                            "Zielvorgabe wird als Ist-Wert wiedergegeben",
                            matched_fact=ev_fact,
                            claim_fact=claim_fact,
                            checks=checks + ["modality_mismatch"],
                        )
                    # Die Evidence muss die Aussage des Claims decken. Ein
                    # Claim, der die Zahl korrekt zitiert und ihr zusätzlich
                    # eine unbelegte Aussage anhängt, ist nicht gestützt.
                    coverage = coverage_ratio(claim_fact.predicate, ev_fact.predicate)
                    if (
                        predicate_overlap >= PREDICATE_MATCH_THRESHOLD
                        and coverage >= PREDICATE_COVERAGE_THRESHOLD
                    ):
                        return EntailmentResult(
                            EntailmentVerdict.SUPPORTED,
                            "Zahl, Bezugsgruppe und Aussage stimmen überein",
                            matched_fact=ev_fact,
                            claim_fact=claim_fact,
                            checks=checks + ["value_subject_predicate_match"],
                        )
                    if coverage < PREDICATE_COVERAGE_THRESHOLD:
                        return EntailmentResult(
                            EntailmentVerdict.CONTRADICTED,
                            "Zahl und Bezugsgruppe passen, der Claim behauptet "
                            f"aber mehr als die Quelle deckt (Deckung {coverage:.2f})",
                            matched_fact=ev_fact,
                            claim_fact=claim_fact,
                            checks=checks + ["predicate_overreach"],
                        )
                    return EntailmentResult(
                        EntailmentVerdict.CONTRADICTED,
                        "Zahl und Bezugsgruppe passen, die Aussage dazu nicht",
                        matched_fact=ev_fact,
                        claim_fact=claim_fact,
                        checks=checks + ["predicate_mismatch"],
                    )

                if same_value and not same_subject:
                    return EntailmentResult(
                        EntailmentVerdict.CONTRADICTED,
                        "Zahl wird einer anderen Bezugsgruppe zugeschrieben",
                        matched_fact=ev_fact,
                        claim_fact=claim_fact,
                        checks=checks + ["subject_mismatch"],
                    )

                if (
                    same_subject
                    and not same_value
                    and predicate_overlap >= PREDICATE_MATCH_THRESHOLD
                ):
                    return EntailmentResult(
                        EntailmentVerdict.CONTRADICTED,
                        "gleiche Aussage über dieselbe Gruppe, abweichender Zahlenwert",
                        matched_fact=ev_fact,
                        claim_fact=claim_fact,
                        checks=checks + ["value_mismatch"],
                    )

        return EntailmentResult(
            EntailmentVerdict.INSUFFICIENT,
            "numerischer Claim ohne passenden Zahlenbeleg",
            claim_fact=claim_facts[0],
            checks=checks + ["no_matching_number"],
        )

    # --- Regel 2: Claim behauptet eine Mehrheit/Minderheit ------------------
    direction = _quantifier_direction(claim)
    if direction and evidence_facts:
        checks.append("quantifier_claim")
        for ev_fact in evidence_facts:
            if ev_fact.unit != "percent" or not subjects_match(claim, ev_fact.subject):
                continue
            is_majority = ev_fact.value > 50.0
            if direction == "majority" and not is_majority:
                return EntailmentResult(
                    EntailmentVerdict.CONTRADICTED,
                    f"Mehrheitsaussage steht gegen einen Anteil von {ev_fact.value:g} %",
                    matched_fact=ev_fact,
                    checks=checks + ["majority_vs_minority"],
                )
            if direction == "minority" and is_majority:
                return EntailmentResult(
                    EntailmentVerdict.CONTRADICTED,
                    f"Minderheitsaussage steht gegen einen Anteil von {ev_fact.value:g} %",
                    matched_fact=ev_fact,
                    checks=checks + ["minority_vs_majority"],
                )
        return EntailmentResult(
            EntailmentVerdict.RELATED_ONLY,
            "Mengenaussage ohne quantitativen Beleg",
            checks=checks + ["quantifier_unbacked"],
        )

    # --- Regel 3: rein qualitativer Claim ----------------------------------
    if topic_overlap < TOPIC_MATCH_THRESHOLD:
        return EntailmentResult(
            EntailmentVerdict.INSUFFICIENT,
            "zu geringe inhaltliche Überschneidung",
            checks=checks + ["low_overlap"],
        )

    if judge is not None:
        try:
            raw_verdict = str(judge(claim, evidence_text)).strip().upper()
            if raw_verdict in EntailmentVerdict.__members__:
                judge_verdict = EntailmentVerdict[raw_verdict]
                # ADR-0002: Der LLM-Judge darf ein regelbasiertes SUPPORTED
                # nur abschwächen, nie erzeugen. Im qualitativen Pfad (Regel 3)
                # gibt es kein regelbasiertes SUPPORTED — also wäre ein
                # Judge-SUPPORTED ein ungedeckter Claim, der durch das Tor
                # geschlüpft wäre. Downgraden auf RELATED_ONLY.
                if judge_verdict is EntailmentVerdict.SUPPORTED:
                    return EntailmentResult(
                        EntailmentVerdict.RELATED_ONLY,
                        "Judge-Bestätigung darf SUPPORTED nicht erzeugen (ADR-0002)",
                        checks=checks + ["judge_downgraded"],
                    )
                return EntailmentResult(
                    judge_verdict, "strukturierter Judge", checks=checks + ["judge"]
                )
        except Exception:  # noqa: BLE001 — Judge ist optional; Regelpfad bleibt gültig
            checks.append("judge_failed")

    if topic_overlap >= PREDICATE_MATCH_THRESHOLD:
        return EntailmentResult(
            EntailmentVerdict.SUPPORTED,
            "qualitative Aussage deckt sich weitgehend mit der Evidence",
            checks=checks + ["high_lexical_overlap"],
        )

    return EntailmentResult(
        EntailmentVerdict.RELATED_ONLY,
        "thematisch verwandt, aber kein Beleg",
        checks=checks + ["topic_only"],
    )


def classify_many(
    claim_text: str,
    evidence_items: Sequence[Dict[str, Any]],
    *,
    judge: Optional[EntailmentJudge] = None,
) -> List[EntailmentResult]:
    return [classify_evidence(claim_text, item, judge=judge) for item in evidence_items]


__all__ = [
    "EntailmentJudge",
    "EntailmentResult",
    "EntailmentVerdict",
    "FactModality",
    "NumericFact",
    "PREDICATE_MATCH_THRESHOLD",
    "TOPIC_MATCH_THRESHOLD",
    "classify_evidence",
    "classify_many",
    "extract_numeric_facts",
    "subjects_match",
]
