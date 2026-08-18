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

from .claim_atomizer import split_compound_claim


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


class BoundKind(str, Enum):
    """Beschreibt die Zahl einen Punktwert oder eine Schranke?

    "31 Prozent geschult" und "mindestens 80 Prozent geschult" sind nicht
    derselbe Aussagetyp. Der erste Satz misst, der zweite fordert. Ohne diese
    Unterscheidung las der Trust-Layer die Differenz 31 ≠ 80 als Widerspruch
    und löschte den Satz aus dem Fließtext — obwohl beide Angaben gleichzeitig
    zutreffen und der Satz genau diese Lücke benennt.
    """

    EXACT = "exact"
    AT_LEAST = "at_least"
    AT_MOST = "at_most"


@dataclass(frozen=True)
class NumericFact:
    """Eine Zahl zusammen mit ihrer Bezugsgruppe und ihrer Aussage."""

    value: float
    unit: str
    subject: str
    predicate: str
    modality: FactModality = FactModality.FACTUAL
    raw: str = ""
    bound: BoundKind = BoundKind.EXACT
    #: Einschränkende Zusätze aus dem Vorfeld ("Pflege-Nachtschicht",
    #: "erstes Quartal") in Originalschreibweise. Zwei Zahlen über dieselbe
    #: Bezugsgruppe, aber verschiedene Teilpopulationen oder Zeiträume, sind
    #: keine widersprüchlichen Angaben über denselben Sachverhalt.
    #:
    #: Bewusst ungestemmt: ``text_verification._fact_probe`` baut aus einem
    #: Fakt wieder einen Prüftext, und der Scope muss dabei so wiederauftauchen,
    #: dass ihn dieselbe Extraktion erneut findet. Aus Stämmen ließe sich das
    #: nicht rekonstruieren, und der Scope-Schutz wäre im Fließtext-Pfad —
    #: also genau dort, wo der Referenzlauf Sätze verlor — wirkungslos.
    scope: frozenset[str] = frozenset()


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

#: Absolutzahl mit ihrem Bezugsnomen. Zwischen beiden dürfen bis zu zwei
#: kleingeschriebene Wörter stehen: "38 abweichende Dringlichkeitsfälle",
#: "412 geprüfte Fälle", "38 der Empfehlungen". Ohne diese Lücke entstand für
#: solche Sätze gar kein Fakt, und die Zahl war für den Trust-Layer nicht
#: vorhanden — im Referenzlauf traf das die 38 abweichenden Dringlichkeitsfälle
#: und die 412 geprüften Fälle.
_ABSOLUTE_RE = re.compile(
    r"(?P<value>\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)\s+"
    r"(?:[a-zäöüß]+\s+){0,2}"
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
    "fordert",
    "fordern",
    "verlangt",
    "verlangen",
    "schreibt vor",
    "sieht vor",
    "vorsieht",
    "should",
    "must",
    "planned",
    "required",
    "requires",
    "demands",
)

#: Substantivische Zielmarker. Deutsch drückt eine Vorgabe häufig ohne Modalverb
#: aus — "Schulungsziel von 80 Prozent in allen Schichten" ist eine Anforderung,
#: trägt aber kein "soll". Ohne diese Liste las ``_modality_of`` den Satz als
#: Ist-Wert, die normativ formulierte Quelle als Zielvorgabe, und das Ergebnis
#: war ein ``modality_mismatch`` auf einer belegten Aussage (Issue #1356).
#:
#: Sie werden als Teilwort gesucht, nicht als eigenes Token: "Schulungsziel",
#: "Zielmarke" und "Mindestquote" sind Komposita, in denen der Marker
#: aufgeht. Der Preis dafür sind gelegentliche Falschtreffer ("Zielgruppe") —
#: die kosten nach Issue #1356 aber nur noch einen Hinweis am Satz, keine
#: Löschung mehr.
_NORMATIVE_NOUN_MARKERS = (
    "ziel",
    "zielwert",
    "zielmarke",
    "zielquote",
    "vorgabe",
    "sollwert",
    "sollquote",
    "anforderung",
    "schwellenwert",
    "target",
    "threshold",
)

#: Bewusst *nicht* mehr in der Liste oben: "mindestens", "maximal",
#: "höchstens", "at least", "at most". Diese Wörter beschreiben eine Schranke,
#: keine Absicht — "der Fallback dauerte höchstens 15 Minuten" ist eine
#: Messung, "das Ziel sind 80 Prozent" eine Vorgabe. Solange sie beides
#: bedeuteten, galt jede Schranke automatisch als Zielvorgabe, jeder Vergleich
#: mit einem gemessenen Wert als Modalitätskonflikt, und eine tatsächlich
#: gerissene Grenze verschwand als "nicht vergleichbar". Die Schranke selbst
#: erfasst jetzt :class:`BoundKind`, die Absicht die Marker oben.

#: Marker für eine untere bzw. obere Schranke. Sie stehen im Deutschen
#: unmittelbar links der Zahl ("mindestens 80 Prozent"), weshalb
#: :func:`_bound_of` nur ein kurzes Fenster davor liest — ein "mindestens" aus
#: einem anderen Satzteil darf einen gemessenen Wert nicht zur Forderung machen.
_AT_LEAST_MARKERS = (
    "mindestens",
    "wenigstens",
    "nicht weniger als",
    "minimum",
    "mindest",
    "at least",
    "no less than",
)

_AT_MOST_MARKERS = (
    "maximal",
    "höchstens",
    "hoechstens",
    "nicht mehr als",
    "nicht länger als",
    "nicht laenger als",
    "bis zu",
    "max.",
    "at most",
    "no more than",
    "up to",
)

#: Wie weit links der Zahl nach einem Schrankenmarker gesucht wird.
_BOUND_WINDOW = 40

#: Ausgeschriebene Aufzählungswörter. Sie stehen am Satzanfang und sind
#: deshalb großgeschrieben — ohne diese Liste hielt :func:`_subject_from_prefix`
#: das "Drittens" in "Drittens erreichte die Verwaltung 42 Prozent" für die
#: Bezugsgruppe der Zahl. Die echte Gruppe rutschte in den Scope, der Fakt
#: fand weder Beleg noch Widerspruch, und der Satz blieb ungeprüft stehen.
#:
#: ``text_verification`` verwendet dieselbe Liste, um eine aufgerissene
#: Aufzählung wieder lückenlos zu zählen.
ENUMERATION_WORDS: tuple[str, ...] = (
    "erstens",
    "zweitens",
    "drittens",
    "viertens",
    "fünftens",
    "fuenftens",
    "sechstens",
    "siebtens",
    "siebentens",
    "achtens",
    "neuntens",
    "zehntens",
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


#: Verneinungsmarker. Sie muessen vor ``_tokens`` geprueft werden — ``nicht``
#: steht selbst in ``_STOPWORDS`` und faellt dort weg (#1317).
_NEGATION_MARKERS = frozenset({
    "nicht", "kein", "keine", "keiner", "keines", "keinem", "keinen",
    "nie", "niemals", "ohne", "weder", "not", "no", "never", "without",
})


def _is_negated(text: str) -> bool:
    """Traegt der Text einen Verneinungsmarker?

    Bewusst grob: es geht nur darum, zwei sonst nicht messbare Praedikate
    auseinanderzuhalten, nicht um eine Skopusanalyse der Negation.
    """
    return any(
        token in _NEGATION_MARKERS
        for token in re.split(r"\W+", (text or "").lower())
        if token
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
        # Issue #1356: Eine Bezugsgruppe enthält keine zweite Zahlenangabe.
        # In "83 Prozent, in der Verwaltung 91 Prozent und in der Pflege 54
        # Prozent" lief das Subjekt des ersten Fakts über die beiden anderen
        # Zahlen hinweg — jeder Fakt bekam dieselbe unbrauchbare Bezugsgruppe
        # und kollidierte anschließend mit fremden Quellen.
        if any(char.isdigit() for char in word):
            break
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
            # Issue #1356: dieselbe Grenze wie im deutschen Pfad. Ohne sie
            # verschluckt der Fallback in einer Aufzählung ("83 Prozent, in
            # der Verwaltung 91 Prozent …") den gesamten Rest des Satzes als
            # Bezugsgruppe, sobald rechts der Zahl kein Nomen steht.
            if any(char.isdigit() for char in word):
                end_idx = en_idx
                break
            if bare in _EN_SUBJECT_VERBS:
                end_idx = en_idx
                break
            subject_parts.append(word)
        if subject_parts:
            subject = " ".join(subject_parts).strip(",.;:() ")
            predicate = " ".join(words[end_idx:]).strip(",.;:() ")

    return subject, predicate


def _modality_of(predicate: str, context: str = "") -> FactModality:
    """Ist-Wert oder Zielvorgabe?

    ``context`` ist der ganze Satz. Modalität ist eine Satzeigenschaft, keine
    Prädikatseigenschaft: in "Das Schulungsziel von 80 Prozent wurde in allen
    Schichten verfehlt" steht der Marker im Vorfeld, während ``_full_predicate``
    nur "in allen Schichten verfehlt" liefert. Wer bloß das Prädikat liest,
    hält die Vorgabe für einen gemessenen Wert (Issue #1356).
    """
    # Der ganze Satz, nicht nur das Prädikat: "Der Projektplan *fordert*
    # mindestens 80 Prozent" trägt seinen Zielcharakter im Vorfeld, während
    # ``_full_predicate`` nur den Teil rechts der Zahl liefert. Wer bloß dort
    # sucht, liest die Vorgabe als gemessenen Wert — und vergleicht sie
    # anschließend mit einem Ist-Wert, als wären beide dasselbe.
    #
    # Die Wortgrenzen bleiben: "muss" darf nicht in "Kompromissbereitschaft"
    # anschlagen.
    lowered = f" {predicate.lower()} {context.lower()} "
    if any(f" {marker} " in lowered for marker in _NORMATIVE_MARKERS):
        return FactModality.NORMATIVE
    if any(marker in lowered for marker in _NORMATIVE_NOUN_MARKERS):
        return FactModality.NORMATIVE
    return FactModality.FACTUAL


def _bound_of(prefix: str) -> BoundKind:
    """Punktwert oder Schranke? Entschieden wird am Fenster links der Zahl.

    "mindestens 80 Prozent" ist eine Untergrenze, "31 Prozent" ein gemessener
    Wert. Ohne diese Unterscheidung verglich der Trust-Layer 31 mit 80 und
    erklärte den Satz für widerlegt (Referenzlauf ``report_cc2ef45da5e9``).

    Das Fenster ist bewusst kurz: in "… liegt bei 31 Prozent, während der
    Projektplan mindestens 80 Prozent fordert" gehört das "mindestens" zur
    zweiten Zahl, nicht zur ersten.
    """
    window = (prefix or "")[-_BOUND_WINDOW:].lower()
    at_least = max(
        (window.rfind(marker) for marker in _AT_LEAST_MARKERS), default=-1
    )
    at_most = max((window.rfind(marker) for marker in _AT_MOST_MARKERS), default=-1)
    if at_least < 0 and at_most < 0:
        return BoundKind.EXACT
    return BoundKind.AT_LEAST if at_least > at_most else BoundKind.AT_MOST


def _noun_phrases(text: str) -> List[List[str]]:
    """Zusammenhängende großgeschriebene Nominalphrasen eines Textstücks.

    Ohne Tagger reicht die deutsche Großschreibung. Artikel und Präpositionen
    fallen über :data:`_STOPWORDS` und die Mindestlänge heraus — sonst zöge
    jedes satzeinleitende "Die" eine Phrase auf.
    """
    groups: List[List[str]] = []
    current: List[str] = []
    for word in (text or "").split():
        bare = word.strip(",.;:()\"'").lower()
        if any(char.isdigit() for char in word):
            if current:
                groups.append(current)
                current = []
            continue
        if (
            word[:1].isupper()
            and bare not in _STOPWORDS
            and bare not in ENUMERATION_WORDS
            and len(bare) > 3
        ):
            current.append(word.strip(",.;:()\"'"))
            continue
        if current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _subject_from_prefix(prefix: str) -> str:
    """Bezugsgruppe aus dem Vorfeld, wenn rechts der Zahl keine steht.

    Deutsch stellt das Satzsubjekt regelmäßig vor das Verb: "Die Verwaltung
    erreichte 91 Prozent." Rechts der Zahl steht dort nur der Satzpunkt, und
    :func:`_split_subject_predicate` gab entsprechend nichts zurück — der Fakt
    entstand nie. Damit war die Zahl für den Trust-Layer unsichtbar: weder
    konnte sie einen Claim belegen (P1 „vorhandene Evidence wird nicht
    gefunden") noch einen echten Widerspruch aufdecken.

    Genommen wird die **letzte** Nominalphrase vor der Zahl, nicht die erste.
    Sie steht der Zahl am nächsten und ist deshalb ihre Bezugsgruppe: in "Die
    Basisschulung erreichte in der Ärzteschaft 83 Prozent" gehören die 83 zur
    Ärzteschaft, nicht zur Basisschulung. Das war die als ``xfail`` geführte
    Restlücke aus #1357.
    """
    groups = _noun_phrases(prefix)
    if not groups:
        return ""
    return " ".join(groups[-1])


def _stems(value: str) -> set[str]:
    return {t[:6] for t in _tokens(value) if len(t) > 3}


#: Präpositionen, die eine Teilpopulation oder einen Zeitraum einführen.
#: Nur was hinter einer von ihnen steht, grenzt eine Aussage ein.
#:
#: Bewusst ohne Quellenangaben ("laut", "gemäß", "zufolge"): die benennen, wer
#: etwas sagt, nicht worüber. Ließe man sie zu, wären "laut Betriebsrat 54 %"
#: und "laut Personalrat 31 %" über dieselbe Gruppe plötzlich zwei
#: verschiedene Sachverhalte — und ein echter Widerspruch verschwände.
_SCOPE_PREPOSITIONS = frozenset({
    "in", "im", "innerhalb", "bei", "beim", "unter", "für", "fuer",
    "bis", "ab", "seit", "während", "waehrend", "an", "am", "auf",
    "je", "pro", "zum", "zur",
})

#: Wie viele Wörter vor der Nominalphrase nach der Präposition abgesucht
#: werden. Deckt Präposition + Artikel + Adjektiv ab.
_SCOPE_PREPOSITION_WINDOW = 3


def _preceded_by_scope_preposition(prefix: str, phrase: List[str]) -> bool:
    """Führt eine eingrenzende Präposition diese Nominalphrase ein?"""
    if not phrase:
        return False
    words = prefix.split()
    head = phrase[0].strip(",.;:()\"'")
    for index in range(len(words) - 1, -1, -1):
        if words[index].strip(",.;:()\"'") != head:
            continue
        # Drei Wörter Fenster: Präposition, Artikel, Adjektiv — "im ersten
        # Quartal", "in der großen Abteilung". Ein festes Fenster ist hier
        # robuster als eine Wortartenprüfung, für die es keinen Tagger gibt.
        window = words[max(0, index - _SCOPE_PREPOSITION_WINDOW) : index]
        return any(
            word.strip(",.;:()\"'").lower() in _SCOPE_PREPOSITIONS for word in window
        )
    return False


def _scope_terms(prefix: str, subject: str) -> frozenset[str]:
    """Einschränkende Zusätze links der Zahl, ohne die Bezugsgruppe selbst.

    "In der Pflege-Nachtschicht sind 31 Prozent der Beschäftigten geschult"
    und "In der Pflege sind 54 Prozent der Beschäftigten geschult" reden über
    dieselbe Bezugsgruppe (Beschäftigte), aber über verschiedene
    Teilpopulationen. Beide Werte können gleichzeitig stimmen.
    """
    subject_stems = _stems(subject)
    groups = _noun_phrases(prefix)
    if not groups:
        return frozenset()
    # Nur die *letzte* Nominalphrase vor der Zahl, und nur wenn eine
    # eingrenzende Präposition sie einführt.
    #
    # Beides ist nötig. Ohne die Beschränkung auf die letzte Phrase zählt in
    # "Laut Betriebsrat sind in der Pflege 54 Prozent" auch die Quellenangabe
    # mit; ohne die Präposition wird in "Aktuell sind 31 Prozent geschult" das
    # satzeinleitende Adverb zur Teilpopulation. In beiden Fällen wichen die
    # Scopes zweier Sätze über *dieselbe* Gruppe voneinander ab, und ein
    # echter Widerspruch verschwände als "nicht vergleichbar".
    if not _preceded_by_scope_preposition(prefix, groups[-1]):
        return frozenset()
    return frozenset(
        word for word in groups[-1] if not (_stems(word) & subject_stems)
    )


def _scope_stems(scope: frozenset[str]) -> set[str]:
    """Normalisiert Scope-Wörter für den Vergleich; Komposita zählen einzeln."""
    out: set[str] = set()
    for word in scope:
        for token in re.split(r"[-/]", word.lower()):
            if len(token) > 3 and token not in _STOPWORDS:
                out.add(token[:6])
    return out


def _scopes_diverge(left: frozenset[str], right: frozenset[str]) -> bool:
    """Widersprechen sich die Teilpopulationen — oder schweigt eine Seite?

    Eine Seite ohne erkennbaren Qualifier ist nicht *anders* abgegrenzt,
    sondern unabgegrenzt. Sie darf einen echten Widerspruch nicht abwehren,
    sonst wäre jede Aussage durch bloßes Weglassen des Kontexts immun.
    """
    a, b = _scope_stems(left), _scope_stems(right)
    if not a or not b:
        return False
    return a != b


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
            prefix = sentence[: match.start()]
            subject, tail = _split_subject_predicate(sentence[match.end():])
            if not subject:
                # Deutsches Vorfeld: "Die Verwaltung erreichte 91 Prozent."
                subject = _subject_from_prefix(prefix)
            if not subject:
                continue
            predicate = _full_predicate(prefix, tail)
            facts.append(
                NumericFact(
                    value=value,
                    unit="percent",
                    subject=subject,
                    predicate=predicate,
                    modality=_modality_of(predicate, sentence),
                    raw=sentence.strip(),
                    bound=_bound_of(prefix),
                    scope=_scope_terms(prefix, subject),
                )
            )
        if not any(f.raw == sentence.strip() for f in facts):
            for match in _ABSOLUTE_RE.finditer(sentence):
                value = _parse_number(match.group("value"))
                if value is None:
                    continue
                prefix = sentence[: match.start()]
                subject, tail = _split_subject_predicate(sentence[match.start("noun"):])
                if not subject:
                    subject = _subject_from_prefix(prefix)
                if not subject:
                    continue
                predicate = _full_predicate(prefix, tail)
                facts.append(
                    NumericFact(
                        value=value,
                        unit="absolute",
                        subject=subject,
                        predicate=predicate,
                        modality=_modality_of(predicate, sentence),
                        raw=sentence.strip(),
                        bound=_bound_of(prefix),
                        scope=_scope_terms(prefix, subject),
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
    a, b = _stems(left), _stems(right)
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

#: Qualitativer Pfad (Regel 3): ab dieser Deckung trägt die Evidence den
#: Claim ohne Rückfrage. Gemessen als ``coverage_ratio(claim, evidence)`` —
#: wie viel von dem, was der Claim behauptet, steht in der Quelle.
#:
#: Bis #1357 entschied hier Containment (``_overlap_ratio``) und damit die
#: umgekehrte Richtung: sobald die Evidence *Teilmenge* des Claims war, galt
#: der Claim als belegt. Am Referenzlauf hatten alle 24 so entstandenen
#: Bindungen Containment-Median 1.00 bei Deckungs-Median 0.21 — der Claim
#: behauptete das Fünffache der Quelle. So band die Aussage "der ungestaffelte
#: Vollstart birgt gravierende Risiken für Patientensicherheit" an das
#: Projektankündigungs-Snippet.
QUALITATIVE_SUPPORT_THRESHOLD = 0.60
#: Darunter ist die Evidence bestenfalls thematisch verwandt. Zwischen beiden
#: Schwellen liegt die Grauzone, in der ein lexikalisches Maß nicht mehr
#: entscheiden kann und der Judge gefragt wird.
QUALITATIVE_RELATED_THRESHOLD = 0.10

#: Ab diesem Cosine-Ergebnis der Retrieval-Stufe gilt ein Kandidat als
#: thematisch einschlägig, ohne dass der lexikalische Vorfilter ihn bestätigen
#: muss. Bewusst über der Bindungsschwelle des Binders (0.55 im Report-Pfad):
#: ein schwacher Treffer soll den Filter nicht aushebeln.
RETRIEVAL_RELEVANCE_THRESHOLD = 0.60

#: Menschenlesbare Begründung je Vergleichbarkeits-Dimension. Sie landet im
#: Audit-Protokoll und muss ohne Codekenntnis verständlich sein.
_DIVERGENCE_REASONS = {
    "unit_mismatch": "verschiedene Einheiten",
    "fact_type_mismatch": "Ist-Wert gegen Zielvorgabe",
    "scope_mismatch": "verschiedene Teilpopulation oder Zeitraum",
    "bound_satisfied": "der Wert hält die genannte Schranke ein",
}

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


def facts_are_comparable(left: NumericFact, right: NumericFact) -> Optional[str]:
    """Reden beide Zahlen über denselben Sachverhalt?

    Gibt ``None`` zurück, wenn sie vergleichbar sind — sonst den Namen der
    Dimension, in der sie auseinanderlaufen. Nur vergleichbare Fakten dürfen
    einander widersprechen; ein abweichender Zahlenwert allein reicht nie.

    Geprüft werden die Dimensionen, in denen der Referenzlauf
    ``report_cc2ef45da5e9`` falsch lag:

    ``unit``
        Prozentwert gegen Absolutzahl.
    ``fact_type``
        Ist-Wert gegen Zielvorgabe (:class:`FactModality`) und Punktwert
        gegen Schranke (:class:`BoundKind`). "31 Prozent geschult" widerlegt
        keine Forderung nach "mindestens 80 Prozent" — der Satz benennt
        genau diese Lücke.
    ``scope``
        Teilpopulation oder Zeitraum. "Pflege-Nachtschicht" und "Pflege"
        sind nicht dieselbe Grundgesamtheit; beide Werte können zutreffen.

    Die Bezugsgruppe selbst prüft :func:`subjects_match` und bleibt hier
    außen vor.
    """
    if left.unit != right.unit:
        return "unit_mismatch"
    if left.modality is not right.modality:
        return "fact_type_mismatch"
    if _scopes_diverge(left.scope, right.scope):
        return "scope_mismatch"
    if left.bound is not right.bound and not _bound_is_violated(left, right):
        return "bound_satisfied"
    return None


def _bound_is_violated(left: NumericFact, right: NumericFact) -> bool:
    """Verletzt der gemessene Wert die behauptete Schranke?

    Eine Schranke ist keine Zahl, sondern ein Bereich. "Höchstens 15 Minuten"
    und "22 Minuten gemessen" schließen einander aus; "höchstens 15" und "9
    gemessen" nicht. Ohne diese Prüfung galt jede Schranke gegen jeden
    Punktwert als unvergleichbar, und ein tatsächlich gerissener Grenzwert
    verschwand als ``INSUFFICIENT``.

    Beide Angaben müssen dieselbe Modalität tragen; das prüft der Aufrufer.
    Ein Ist-Wert unter einer *Forderung* ist keine Verletzung, sondern eine
    unerfüllte Forderung — dafür ist der Bericht da, nicht der Trust-Layer.
    """
    # Zwei Schranken können einander ausschließen, ohne dass ein gemessener
    # Wert im Spiel ist: "mindestens 80 Prozent" und "höchstens 70 Prozent"
    # lassen für dieselbe Gruppe keinen gemeinsamen Wert zu.
    lower = next(
        (fact for fact in (left, right) if fact.bound is BoundKind.AT_LEAST), None
    )
    upper = next(
        (fact for fact in (left, right) if fact.bound is BoundKind.AT_MOST), None
    )
    if lower is not None and upper is not None:
        return lower.value > upper.value

    for bound_fact, point in ((left, right), (right, left)):
        if point.bound is not BoundKind.EXACT:
            continue
        if bound_fact.bound is BoundKind.AT_MOST and point.value > bound_fact.value:
            return True
        if bound_fact.bound is BoundKind.AT_LEAST and point.value < bound_fact.value:
            return True
    return False


def _classify_matching_number(
    claim_fact: NumericFact,
    ev_fact: NumericFact,
    predicate_overlap: float,
    checks: List[str],
) -> EntailmentResult:
    """Urteil für den Fall, dass Zahl *und* Bezugsgruppe übereinstimmen.

    Strittig ist dann nur noch die Aussage selbst. Ausgelagert aus
    :func:`classify_evidence`, das mit diesem Block über die
    Komplexitätsschwelle des radon-Gates lief.
    """
    if ev_fact.modality is FactModality.NORMATIVE and (
        claim_fact.modality is FactModality.FACTUAL
    ):
        # Issue #1356: kein Widerspruch, sondern ein nicht entscheidbarer
        # Fall. Die Modalität wird ohne Parser aus Markerlisten geraten;
        # jede Lücke darin erklärte sonst eine belegte Aussage für widerlegt
        # und löschte sie aus dem Fließtext. Zahl und Bezugsgruppe stimmen
        # ja — strittig ist allein die Lesart.
        return EntailmentResult(
            EntailmentVerdict.INSUFFICIENT,
            "Zahl und Bezugsgruppe passen; unklar, ob die Quelle "
            "einen Ist-Wert oder eine Zielvorgabe nennt",
            matched_fact=ev_fact,
            claim_fact=claim_fact,
            checks=checks + ["modality_mismatch"],
        )
    # Die Evidence muss die Aussage des Claims decken. Ein Claim, der die
    # Zahl korrekt zitiert und ihr zusätzlich eine unbelegte Aussage
    # anhängt, ist nicht gestützt.
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
    # coverage == 0.0 heißt hier nicht "der Claim behauptet mehr als
    # belegt" — ``coverage_ratio`` liefert dieselbe 0.0 auch, wenn Claim-
    # oder Evidence-Prädikat nach dem Stopword-/Kurzwort-Filter
    # (``_content_tokens``) leer bleibt, also gar keine Deckung *messbar*
    # ist. Ein kurzes Prädikat ("sind da") darf deshalb nicht als
    # Widerspruch gelten, sondern nur als nicht prüfbar (#1317).
    if coverage == 0.0 and (
        not _content_tokens(claim_fact.predicate)
        or not _content_tokens(ev_fact.predicate)
    ):
        # Vorher die Polarität prüfen: "sind da" und "sind nicht da"
        # reduzieren beide auf ein leeres Token-Set, weil ``nicht`` in
        # ``_STOPWORDS`` steht. Ohne diesen Zweig würde ein echter
        # Verneinungswiderspruch bei gleicher Zahl und Bezugsgruppe als
        # "nicht prüfbar" durchgehen.
        if _is_negated(claim_fact.predicate) != _is_negated(ev_fact.predicate):
            return EntailmentResult(
                EntailmentVerdict.CONTRADICTED,
                "Zahl und Bezugsgruppe passen, die Aussagen "
                "sind aber gegensätzlich verneint",
                matched_fact=ev_fact,
                claim_fact=claim_fact,
                checks=checks + ["polarity_mismatch"],
            )
        return EntailmentResult(
            EntailmentVerdict.INSUFFICIENT,
            "Zahl und Bezugsgruppe passen, die Aussage ist zu "
            "kurz, um gegen die Quelle geprüft zu werden",
            matched_fact=ev_fact,
            claim_fact=claim_fact,
            checks=checks + ["predicate_not_measurable"],
        )
    if coverage < PREDICATE_COVERAGE_THRESHOLD:
        # Issue #1356: eine unbelegte Zusatzaussage ist kein Widerspruch.
        # Die Quelle sagt nichts Gegenteiliges, sie sagt nur weniger. Im
        # Referenzlauf war dieser Zweig mit 14 von 28 Fällen der häufigste
        # Grund, aus dem belegte Zahlen aus dem Fließtext verschwanden —
        # jede Paraphrase kostet Deckung, und die Schwelle liegt bei 0.75.
        return EntailmentResult(
            EntailmentVerdict.INSUFFICIENT,
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


def classify_evidence(
    claim_text: str,
    evidence_item: Dict[str, Any],
    *,
    judge: Optional[EntailmentJudge] = None,
    retrieval_score: Optional[float] = None,
) -> EntailmentResult:
    """Entscheidet, ob ``evidence_item`` den Claim tatsächlich stützt.

    Reihenfolge ist bewusst: numerische und Mengen-Checks laufen zuerst und
    sind bindend. Der ``judge`` wird nur im qualitativen Pfad befragt, und
    auch dort nur in der Grauzone zwischen den beiden Deckungsschwellen.

    ``retrieval_score`` ist das Cosine-Ergebnis der ersten Bindungsstufe,
    sofern der Aufrufer eine hatte. Liegt es über
    :data:`RETRIEVAL_RELEVANCE_THRESHOLD`, entfällt der lexikalische
    Themenvorfilter: die Frage „geht es überhaupt um dasselbe" hat die
    Embedding-Stufe dann bereits besser beantwortet, als Wortzählung es kann.
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
        return _classify_numeric_claim(claim_facts, evidence_facts, checks)

    # --- Regel 2: Claim behauptet eine Mehrheit/Minderheit ------------------
    direction = _quantifier_direction(claim)
    if direction and evidence_facts:
        return _classify_quantifier_claim(claim, direction, evidence_facts, checks)

    return _classify_qualitative_claim(
        claim,
        evidence_text,
        checks,
        topic_overlap=topic_overlap,
        retrieval_score=retrieval_score,
        judge=judge,
    )


def _classify_numeric_claim(
    claim_facts: List[NumericFact],
    evidence_facts: List[NumericFact],
    checks: List[str],
) -> EntailmentResult:
    """Regel 1 — der Claim trägt eine Zahl, und die entscheidet.

    Aus :func:`classify_evidence` herausgelöst, damit beide Funktionen unter
    der Komplexitätsschwelle des radon-Gates bleiben.
    """
    checks = checks + ["numeric_claim"]
    for claim_fact in claim_facts:
        for ev_fact in evidence_facts:
            # Die Einheit gehört zum Wert. "15 Prozent der Beschäftigten"
            # und "15 Beschäftigte" sind nicht dieselbe Zahl — ohne diese
            # Bedingung lief der Fall in den Gleichheitszweig und galt als
            # belegt, obwohl die Quelle etwas anderes misst. Bei ungleichem
            # Wert prüft facts_are_comparable die Einheit ohnehin.
            same_value = (
                claim_fact.unit == ev_fact.unit
                and abs(claim_fact.value - ev_fact.value) < 0.001
            )
            same_subject = subjects_match(claim_fact.subject, ev_fact.subject)
            predicate_overlap = _overlap_ratio(claim_fact.predicate, ev_fact.predicate)

            if same_value and same_subject:
                return _classify_matching_number(
                    claim_fact, ev_fact, predicate_overlap, checks
                )

            if same_value and not same_subject:
                # Issue #1356: kein Widerspruch. Dass eine Quelle denselben
                # Zahlenwert für eine *andere* Gruppe nennt, sagt über die
                # hier behauptete Gruppe nichts aus — zwei Gruppen dürfen
                # denselben Wert haben. Ein Widerspruch wäre erst ein
                # abweichender Wert für dieselbe Gruppe (``value_mismatch``).
                # Im Referenzlauf kostete diese Fehleinstufung vier belegte
                # Aussagen, darunter den Satz mit den drei Schulungsquoten.
                return EntailmentResult(
                    EntailmentVerdict.INSUFFICIENT,
                    "Zahl belegt, aber für eine andere Bezugsgruppe",
                    matched_fact=ev_fact,
                    claim_fact=claim_fact,
                    checks=checks + ["subject_mismatch"],
                )

            if (
                same_subject
                and not same_value
                and predicate_overlap >= PREDICATE_MATCH_THRESHOLD
            ):
                # Nennt der Claim den belegten Wert selbst — nur an einer
                # anderen Zahl festgemacht —, widerspricht er der Quelle
                # nicht, sondern die Zuordnung der Bezugsgruppe ist
                # unscharf. Der Referenzlauf zu #1356 hat genau einen
                # solchen Fall: "83 Prozent im Ärztlichen Dienst und 91
                # Prozent in der Verwaltung" gegen eine Quelle, die die
                # 91 Prozent der Verwaltung belegt. Weil das Subjekt der
                # ersten Zahl bis zur zweiten Gruppe durchläuft (#1357),
                # verglich die Regel 83 mit 91 und löschte einen Satz,
                # den dieselbe Quelle stützt.
                if any(
                    abs(other.value - ev_fact.value) < 0.001 for other in claim_facts
                ):
                    return EntailmentResult(
                        EntailmentVerdict.INSUFFICIENT,
                        "der Claim nennt den belegten Wert an anderer Stelle; "
                        "welche Zahl zu welcher Bezugsgruppe gehört, ist nicht "
                        "eindeutig zuzuordnen",
                        matched_fact=ev_fact,
                        claim_fact=claim_fact,
                        checks=checks + ["value_mismatch_ambiguous_subject"],
                    )
                # Ein abweichender Zahlenwert allein ist kein Widerspruch.
                # Erst wenn beide Zahlen über denselben Sachverhalt reden —
                # gleiche Einheit, gleiche Faktenart, gleiche
                # Grundgesamtheit —, schließen sie einander aus. Im
                # Referenzlauf fehlte diese Prüfung, und ein Ist-Wert einer
                # Teilgruppe (31 % Pflege-Nachtschicht) galt als Widerlegung
                # einer Mindestanforderung an die Gesamtbelegschaft (80 %);
                # der Satz verschwand aus dem Fließtext und riss die
                # Aufzählung auf, in der er stand.
                divergence = facts_are_comparable(claim_fact, ev_fact)
                if divergence is not None:
                    return EntailmentResult(
                        EntailmentVerdict.INSUFFICIENT,
                        "abweichender Zahlenwert, aber die beiden Angaben "
                        "sind nicht vergleichbar "
                        f"({_DIVERGENCE_REASONS[divergence]})",
                        matched_fact=ev_fact,
                        claim_fact=claim_fact,
                        checks=checks + [divergence],
                    )
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


def _classify_quantifier_claim(
    claim: str,
    direction: str,
    evidence_facts: List[NumericFact],
    checks: List[str],
) -> EntailmentResult:
    """Regel 2 — der Claim behauptet eine Mehrheit oder Minderheit."""
    checks = checks + ["quantifier_claim"]
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


def _classify_qualitative_claim(
    claim: str,
    evidence_text: str,
    checks: List[str],
    *,
    topic_overlap: float,
    retrieval_score: Optional[float],
    judge: Optional[EntailmentJudge],
) -> EntailmentResult:
    """Regel 3 — der Claim trägt weder Zahl noch Mengenaussage.

    Der Themenvorfilter fragt nur, ob überhaupt vom Selben die Rede ist.
    Wortüberlappung ist dafür ein schlechtes Maß: ein Interviewzitat sagt
    dasselbe in völlig anderen Worten. Im Referenzlauf fielen 22 von 25
    Interview-Paaren hier heraus (Containment-Median 0.04), obwohl das
    Retrieval sie mit 0.65 bis 0.79 korrekt gefunden hatte — sie erreichten
    die inhaltliche Prüfung nie. Liegt ein Retrieval-Ergebnis vor, hat es
    diese Frage bereits beantwortet (#1357).
    """
    retrieved = (
        retrieval_score is not None
        and retrieval_score >= RETRIEVAL_RELEVANCE_THRESHOLD
    )
    if retrieved:
        checks.append("retrieval_relevant")
    elif topic_overlap < TOPIC_MATCH_THRESHOLD:
        return EntailmentResult(
            EntailmentVerdict.INSUFFICIENT,
            "zu geringe inhaltliche Überschneidung",
            checks=checks + ["low_overlap"],
        )

    # Deckungsrichtung: wie viel von dem, was der Claim behauptet, steht in
    # der Quelle. Nicht umgekehrt — Containment liefert 1.0, sobald die
    # Evidence Teilmenge des Claims ist, und band deshalb jede thematisch
    # passende Projektbeschreibung an jede weitreichende Behauptung (#1357).
    claim_coverage = coverage_ratio(claim, evidence_text)

    if claim_coverage >= QUALITATIVE_SUPPORT_THRESHOLD:
        # Ein zusammengesetzter Claim ist nur belegt, wenn die Quelle jede
        # seiner Teilaussagen berührt. Im Referenzlauf trugen einzelne Claims
        # gleichzeitig einen Seed-Fakt, eine Stakeholder-Aussage und eine
        # Ableitung; die Quelle deckte davon eine, und die Gesamtdeckung
        # reichte trotzdem über die Schwelle. Verlangt wird hier bewusst nur
        # thematische Präsenz je Teil — ein voller Deckungsnachweis pro
        # Teilsatz scheiterte an Paraphrasen und nähme die belegten Aussagen
        # mit, um die es gerade nicht geht.
        atoms = split_compound_claim(claim)
        if len(atoms) > 1:
            uncovered = [
                atom
                for atom in atoms
                if coverage_ratio(atom, evidence_text) < QUALITATIVE_RELATED_THRESHOLD
            ]
            if uncovered:
                return EntailmentResult(
                    EntailmentVerdict.INSUFFICIENT,
                    "der Claim behauptet mehreres; zu "
                    f"{len(uncovered)} von {len(atoms)} Teilaussagen sagt die "
                    "Quelle nichts",
                    checks=checks + ["compound_claim_partially_uncovered"],
                )
        # Polarität zuerst — aus demselben Grund wie im numerischen Pfad
        # (#1317): ``nicht`` steht in ``_STOPWORDS``, "die Betriebsvereinbarung
        # ist abgeschlossen" und "… ist *nicht* abgeschlossen" reduzieren
        # deshalb auf dasselbe Token-Set und erreichen Deckung 1.00. Ohne
        # diese Prüfung würde eine Quelle, die den Claim ausdrücklich
        # verneint, ihn als belegt ausweisen und die Confidence anheben
        # (Codex-Review PR #1361, P1).
        if _is_negated(claim) != _is_negated(evidence_text):
            return EntailmentResult(
                EntailmentVerdict.CONTRADICTED,
                "die Quelle deckt den Claim wörtlich ab, verneint ihn aber "
                f"gegenläufig (Deckung {claim_coverage:.2f})",
                checks=checks + ["qualitative_polarity_mismatch"],
            )
        return EntailmentResult(
            EntailmentVerdict.SUPPORTED,
            "die Quelle deckt den Claim weitgehend ab "
            f"(Deckung {claim_coverage:.2f})",
            checks=checks + ["high_claim_coverage"],
        )

    if claim_coverage < QUALITATIVE_RELATED_THRESHOLD and not retrieved:
        # Dieselbe Einschränkung wie beim Themenvorfilter, aus demselben
        # Grund: eine niedrige *lexikalische* Deckung schließt einen Beleg
        # nur aus, wenn es kein besseres Relevanzsignal gibt. Interviewzitate
        # haben im Referenzlauf eine Deckung um 0.02 — sie sagen dasselbe in
        # anderen Worten, nicht etwas anderes. Ohne diese Ausnahme wäre die
        # untere Schwelle das neue Nadelöhr an der Stelle des alten.
        return EntailmentResult(
            EntailmentVerdict.RELATED_ONLY,
            "thematisch verwandt, aber kein Beleg "
            f"(Deckung {claim_coverage:.2f})",
            checks=checks + ["low_claim_coverage"],
        )

    # Grauzone. Hier trennt kein lexikalisches Maß mehr: eine korrekte
    # Paraphrase und eine erfundene Zusatzbehauptung liegen dicht beieinander
    # (im Referenzlauf 0.50 gegen 0.56 — die erfundene sogar höher). Jede
    # Schwelle, die die eine fängt, löscht die andere mit. Entschieden wird
    # deshalb inhaltlich.
    if judge is not None:
        try:
            raw_verdict = str(judge(claim, evidence_text)).strip().upper()
            if raw_verdict in EntailmentVerdict.__members__:
                judge_verdict = EntailmentVerdict[raw_verdict]
                # ADR-0002 wird an dieser Stelle abgelöst
                # (docs/decisions/0002-supersedes.md): der Judge darf in der
                # Grauzone ein SUPPORTED *erzeugen*. Der alte Deckel war
                # sinnvoll, solange Regel 3 selbst großzügig SUPPORTED
                # vergab — jetzt ist er das Gegenteil: ohne ihn bliebe die
                # Grauzone für immer bei RELATED_ONLY, und Interviews, deren
                # Deckung nie über 0.29 kommt, könnten nie binden. Regel 1
                # und 2 bleiben unberührt bindend; ein regelbasiertes
                # CONTRADICTED erreicht diesen Code nie.
                return EntailmentResult(
                    judge_verdict, "strukturierter Judge", checks=checks + ["judge"]
                )
        except Exception as exc:  # noqa: BLE001 — Judge ist optional; Regelpfad bleibt gültig
            # Ein erschöpftes Run-Budget ist kein Judge-Fehler, sondern das
            # Ende des Laufs (Codex-Review PR #1361, P1). Lokaler Import, weil
            # ``run_budget`` diesen Modul-Baum sonst zirkulär zieht.
            from .run_budget import reraise_if_budget_exceeded  # noqa: PLC0415

            reraise_if_budget_exceeded(exc)
            checks.append("judge_failed")

    # Ohne Judge bleibt die Grauzone unentschieden — und unentschieden heißt
    # nicht belegt.
    return EntailmentResult(
        EntailmentVerdict.RELATED_ONLY,
        "thematisch verwandt, Beleggrad ohne inhaltliche Prüfung nicht "
        f"entscheidbar (Deckung {claim_coverage:.2f})",
        checks=checks + ["grey_zone_unjudged"],
    )


def classify_many(
    claim_text: str,
    evidence_items: Sequence[Dict[str, Any]],
    *,
    judge: Optional[EntailmentJudge] = None,
) -> List[EntailmentResult]:
    return [classify_evidence(claim_text, item, judge=judge) for item in evidence_items]


__all__ = [
    "ENUMERATION_WORDS",
    "BoundKind",
    "EntailmentJudge",
    "EntailmentResult",
    "EntailmentVerdict",
    "FactModality",
    "NumericFact",
    "PREDICATE_MATCH_THRESHOLD",
    "QUALITATIVE_RELATED_THRESHOLD",
    "RETRIEVAL_RELEVANCE_THRESHOLD",
    "QUALITATIVE_SUPPORT_THRESHOLD",
    "TOPIC_MATCH_THRESHOLD",
    "classify_evidence",
    "classify_many",
    "extract_numeric_facts",
    "facts_are_comparable",
    "subjects_match",
]
