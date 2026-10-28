"""Regex-Muster, Wortlisten und Schwellwerte für das Evidence-Entailment."""

from __future__ import annotations

import re

#: Ausgeschriebene Zahlwoerter. Die deutsche Schreibkonvention setzt Zahlen bis
#: zwoelf als Wort — "sechs Qualifizierungsangebote" ist derselbe pruefbare
#: Fakt wie "6 Qualifizierungsangebote", erzeugte aber keinen ``NumericFact``,
#: weil beide Muster eine Ziffer verlangten (#1492, Restbefund).
#:
#: ``ein``/``eine`` fehlt bewusst: im Deutschen weit oefter unbestimmter Artikel
#: als Zahlwort. Aus "eine Lehrkraft berichtet von Zeitgewinn" wuerde sonst der
#: Fakt "1 Lehrkraft" — eine Mengenbehauptung, die der Satz gar nicht aufstellt,
#: und im Trust-Layer damit eine erfundene Zahl.
#:
#: ``null`` fehlt aus dem Gegengrund: als Mengenangabe praktisch nie
#: ausgeschrieben, als Wort dagegen haeufig ("null Ahnung").
_WORD_NUMBERS: dict[str, float] = {
    "zwei": 2.0,
    "drei": 3.0,
    "vier": 4.0,
    "fünf": 5.0,
    "fuenf": 5.0,
    "sechs": 6.0,
    "sieben": 7.0,
    "acht": 8.0,
    "neun": 9.0,
    "zehn": 10.0,
    "elf": 11.0,
    "zwölf": 12.0,
    "zwoelf": 12.0,
}

#: Klein- und Grossschreibung getrennt gefuehrt statt ``re.IGNORECASE``: das
#: Flag wuerde auch ``(?P<noun>[A-ZÄÖÜ]…)`` aufweichen, und genau diese
#: Grossschreibung traegt im Deutschen die Nominalphrase.
_WORD_NUMBER_ALTERNATION = "|".join(
    sorted(
        {form for word in _WORD_NUMBERS for form in (word, word.capitalize())},
        key=len,
        reverse=True,
    )
)

#: Zahlwert als Ziffernfolge oder ausgeschriebenes Wort. Die Lookbehind-Sperre
#: gilt nur im Wortzweig und verhindert Treffer im Wortinneren ("Entzweiung").
_NUMBER_VALUE = (
    r"\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?"
    rf"|(?<![A-Za-zÄÖÜäöüßÀ-ÿ])(?:{_WORD_NUMBER_ALTERNATION})"
)

_PERCENT_RE = re.compile(
    rf"(?P<value>{_NUMBER_VALUE})\s*(?:%|Prozent|percent)\s*"
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
    rf"(?P<value>{_NUMBER_VALUE})\s+"
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

_NEGATION_MARKERS = frozenset({
    "nicht", "kein", "keine", "keiner", "keines", "keinem", "keinen",
    "nie", "niemals", "niemand", "ohne", "weder", "not", "no", "never", "without",
    "nobody",
})

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

#: Ab wie vielen Inhaltswörtern der Teil rechts der Zahl als eigenständige
#: Aussage gilt. Darunter ist er ein Fragment ("", "geführt") und das Vorfeld
#: trägt die Aussage.
_TAIL_PREDICATE_MIN_TOKENS = 2

_FROM_TO_RE = re.compile(
    rf"von\s+(?:{_NUMBER_VALUE})\s*(?:%|Prozent)?\s*bis\s+zu\s+(?:{_NUMBER_VALUE})",
    re.IGNORECASE,
)

_RANGE_RE = re.compile(
    rf"(?:{_NUMBER_VALUE})\s*(?:bis(?!\s+zu\b)|to|[–—]|(?<=\d)\s*-\s*(?=\d))\s*"
    rf"(?:{_NUMBER_VALUE})",
    re.IGNORECASE,
)

_BETWEEN_RE = re.compile(
    rf"zwischen\s+(?:{_NUMBER_VALUE})\s*(?:%|Prozent)?\s*und\s*(?:{_NUMBER_VALUE})",
    re.IGNORECASE,
)

#: Ab diesem Containment-Overlap gilt eine Aussage als dieselbe Aussage.
PREDICATE_MATCH_THRESHOLD = 0.5
#: Darunter besteht nicht einmal thematische Nähe.
TOPIC_MATCH_THRESHOLD = 0.2
#: Mindestanteil der Claim-Aussage, der von der Evidence gedeckt sein muss,
#: damit ein numerischer Fakt als übernommen gilt. Höchstens ein Viertel der
#: inhaltlichen Aussage darf über die Evidence hinausgehen.
PREDICATE_COVERAGE_THRESHOLD = 0.75

#: Qualitativer Pfad (Regel 3): ab dieser Deckung trägt die Evidence den
#: Claim ohne Rückfrage. Gemessen als ``coverage_ratio(claim, evidence)``.
QUALITATIVE_SUPPORT_THRESHOLD = 0.60
#: Darunter ist die Evidence bestenfalls thematisch verwandt. Zwischen beiden
#: Schwellen liegt die Grauzone, in der ein lexikalisches Maß nicht mehr
#: entscheiden kann und der Judge gefragt wird.
QUALITATIVE_RELATED_THRESHOLD = 0.10

#: Ab diesem Cosine-Ergebnis der Retrieval-Stufe gilt ein Kandidat als
#: thematisch einschlägig, ohne dass der lexikalische Vorfilter ihn bestätigen
#: muss.
RETRIEVAL_RELEVANCE_THRESHOLD = 0.60

#: Menschenlesbare Begründung je Vergleichbarkeits-Dimension. Sie landet im
#: Audit-Protokoll und muss ohne Codekenntnis verständlich sein.
_DIVERGENCE_REASONS = {
    "unit_mismatch": "verschiedene Einheiten",
    "fact_type_mismatch": "Ist-Wert gegen Zielvorgabe",
    "scope_mismatch": "verschiedene Teilpopulation oder Zeitraum",
    "bound_satisfied": "der Wert hält die genannte Schranke ein",
}

__all__ = [
    "ENUMERATION_WORDS",
    "PREDICATE_COVERAGE_THRESHOLD",
    "PREDICATE_MATCH_THRESHOLD",
    "QUALITATIVE_RELATED_THRESHOLD",
    "QUALITATIVE_SUPPORT_THRESHOLD",
    "RETRIEVAL_RELEVANCE_THRESHOLD",
    "TOPIC_MATCH_THRESHOLD",
    "_ABSOLUTE_RE",
    "_AT_LEAST_MARKERS",
    "_AT_MOST_MARKERS",
    "_BETWEEN_RE",
    "_BOUND_WINDOW",
    "_DIVERGENCE_REASONS",
    "_EN_SUBJECT_VERBS",
    "_FROM_TO_RE",
    "_MAJORITY_MARKERS",
    "_MINORITY_MARKERS",
    "_NEGATION_MARKERS",
    "_NORMATIVE_MARKERS",
    "_NORMATIVE_NOUN_MARKERS",
    "_NUMBER_VALUE",
    "_PERCENT_RE",
    "_RANGE_RE",
    "_SCOPE_PREPOSITIONS",
    "_SCOPE_PREPOSITION_WINDOW",
    "_STOPWORDS",
    "_SUBJECT_CONNECTORS",
    "_TAIL_PREDICATE_MIN_TOKENS",
    "_WORD_NUMBERS",
]
