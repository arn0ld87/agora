"""Regressionstest für Issue #1267.

Der Section-Prompt beschreibt dem Modell, wie ein ``seed_anchor`` auszusehen
hat und was mit ihm geschieht. Beides war nach der #1249-Umsetzung falsch:

* Die Zusage ``"seed_doc:" prefix is accepted as an opaque reference without
  further lookup`` beschrieb ein Verhalten, das ``validate_quote_anchors``
  nicht mehr zeigt — dort wird seit #1249 jeder Anker präfixunabhängig gegen
  ``known_anchors`` geprüft.
* Das vorgegebene Format ``seed_doc:<document_id>`` ist strukturell nie
  auflösbar. ``build_seed_document_anchor`` erzeugt ausschließlich Anker der
  Form ``seed_doc:<document_id>#chunk:<chunk_id>`` (ADR-0013), und nur die
  landen als ``source_id_anchor`` in ``known_anchors``.

Der zweite Punkt ist der wichtigere: ohne ihn wäre die Aufforderung, einen
auflösbaren Anker zu setzen, eine Anweisung, die das Modell nicht befolgen
kann.

Abgrenzung zu ``test_seed_anchor_prompt_placeholder.py`` (#1244): dort geht es
um einen kopierbaren Beispielwert. Hier geht es darum, dass die
Formatbeschreibung und die Zusage mit dem tatsächlichen Validator-Verhalten
übereinstimmen.
"""

from __future__ import annotations

import re

from app.contracts.report_contract import EVIDENCE_ID_PATTERN
from app.services import report_prompts
from app.services.report_agent.evidence import (
    _ATTR_RE,
    _QUOTE_TAG_RE,
    is_verified_seed_document_anchor,
)


def _rendered_section_prompt() -> str:
    return report_prompts.SECTION_SYSTEM_PROMPT_TEMPLATE.format(
        report_title="T",
        report_summary="S",
        simulation_requirement="R",
        section_title="Sec",
        language="German",
        tools_description="tools",
    )


def test_prompt_does_not_promise_an_unchecked_seed_doc_prefix() -> None:
    """Der Prompt darf kein Verhalten zusagen, das der Validator nicht zeigt.

    Seit #1249 prüft ``validate_quote_anchors`` jeden Anker gegen
    ``known_anchors``. Ein Prompt, der dem Modell eine Freikarte verspricht,
    provoziert genau die erfundenen Anker, die #1249 sichtbar machen soll —
    und kostet über den Repair-Retry in ``_validate_quotes_with_repair`` einen
    zweiten vollständigen Section-Durchlauf, der nicht erfolgreich sein kann.
    """
    rendered = _rendered_section_prompt().lower()

    assert "without further lookup" not in rendered, (
        "Der Section-Prompt sagt weiterhin zu, dass seed_doc:-Anker ohne "
        "Auflösung akzeptiert werden. Seit #1249 prüft validate_quote_anchors "
        "jeden Anker präfixunabhängig gegen known_anchors."
    )
    assert "opaque reference" not in rendered, (
        "Der Section-Prompt bezeichnet den seed_doc:-Anker weiterhin als "
        "opake Referenz — er wird aufgelöst."
    )


def test_prompt_seed_doc_format_is_accepted_by_the_reader() -> None:
    """Das im Prompt vorgegebene Ankerformat muss der Lesepfad akzeptieren.

    Koppelt Prompt und Validator hart aneinander: Das Formatmuster wird aus
    dem gerenderten Prompt extrahiert, mit konkreten Werten gefüllt und gegen
    ``is_verified_seed_document_anchor`` geprüft — dieselbe Funktion, die auch
    ``build_seed_document_anchor`` auf dem Schreibpfad gegenprüft.

    Gegen den Stand vor #1267 schlägt das fehl: der Prompt gab
    ``seed_doc:<document_id>`` ohne ``#chunk:`` vor.
    """
    rendered = _rendered_section_prompt()

    pattern = re.compile(r"seed_doc:DOCUMENT_ID(?:#chunk:CHUNK_INDEX)?")
    matches = pattern.findall(rendered)
    assert matches, (
        "Der Section-Prompt beschreibt kein seed_doc:-Formatmuster mehr — "
        "das Modell kann dann keinen gültigen Anker bauen."
    )

    for template in set(matches):
        concrete = template.replace("DOCUMENT_ID", "kursdokument").replace(
            "CHUNK_INDEX", "7"
        )
        assert is_verified_seed_document_anchor(concrete), (
            f"Das im Prompt vorgegebene Format {template!r} ergibt mit "
            f"konkreten Werten {concrete!r} keinen Anker, den der Lesepfad "
            "als Dokumentherkunft anerkennt (ADR-0013 verlangt "
            "seed_doc:<document_id>#chunk:<chunk_id>). Ein Modell, das dem "
            "Prompt folgt, erzeugt damit garantiert einen ungebundenen Anker."
        )


def test_prompt_quote_examples_survive_the_production_parser() -> None:
    """Kein Beispiel-Tag im Prompt darf den eigenen Section-Parser zerlegen.

    ``_QUOTE_TAG_RE`` liest die Attributliste mit ``[^>]+`` — sie endet am
    ersten ``>``. Ein Platzhalter in spitzen Klammern *innerhalb* eines
    Attributwerts (``seed_anchor="seed_doc:<document_id>#chunk:<chunk_id>"``)
    schneidet das Tag also mittendrin ab. Der Rest ist nicht bloß unschön:
    ``seed_anchor`` bleibt unterminiert und fällt aus ``_ATTR_RE`` heraus, das
    Zitat gilt als ankerlos, und der Attributrest landet im Zitattext.

    Der Prompt ist das Vorbild, dem das Modell folgt — ein Beispiel, das den
    eigenen Parser bricht, ist damit ein Defekt im Prompt, nicht im Parser.
    """
    rendered = _rendered_section_prompt()

    values = re.findall(r'seed_anchor="([^"]*)"', rendered)
    assert values, "Der Prompt zeigt kein seed_anchor-Attribut mehr."
    broken = sorted({v for v in values if "<" in v or ">" in v})
    assert not broken, (
        f"Attributwerte {broken} enthalten spitze Klammern. _QUOTE_TAG_RE "
        "schneidet das Tag am ersten '>' ab — der Anker geht verloren und der "
        "Rest leckt in den Zitattext. Platzhalter ohne < > schreiben."
    )

    example = re.search(
        r"<simulated_quote persona_id=.*?</simulated_quote>", rendered, re.DOTALL
    )
    assert example is not None, "Kein vollständiges Positivbeispiel im Prompt."

    parsed = _QUOTE_TAG_RE.findall(example.group(0))
    assert len(parsed) == 1, (
        f"Das Positivbeispiel {example.group(0)!r} ergibt {len(parsed)} statt "
        "genau einem Treffer im Produktions-Parser."
    )
    attrs_raw, body = parsed[0]
    assert set(dict(_ATTR_RE.findall(attrs_raw))) == {"persona_id", "seed_anchor"}, (
        "Aus dem Positivbeispiel liest der Produktions-Parser nicht beide "
        f"Pflichtattribute heraus, sondern nur {attrs_raw!r}."
    )
    assert "#chunk" not in body and '"' not in body, (
        f"Attributreste sind in den Zitattext geleckt: {body!r}"
    )


def test_prompt_evidence_id_literals_match_the_contract() -> None:
    """Jedes ``ev_``-Literal im Prompt muss dem Evidence-ID-Vertrag genügen.

    ``EVIDENCE_ID_PATTERN`` verlangt ``ev_`` plus 32 Hex-Zeichen. Ein
    Beispielwert wie ``ev_kg_042`` ist als Anker nie auflösbar — dieselbe
    Fehlerklasse wie der kopierbare Beispielwert aus #1244, nur im anderen
    Namensraum.

    Kein ``ev_``-Literal im Prompt ist ein gültiges Ergebnis: die reine
    Formatbeschreibung genügt und ist nach #1244 sogar vorzuziehen.
    """
    literals = set(re.findall(r"ev_[0-9a-zA-Z_]+", _rendered_section_prompt()))
    invalid = sorted(
        literal
        for literal in literals
        if re.fullmatch(EVIDENCE_ID_PATTERN, literal) is None
    )
    assert not invalid, (
        f"Evidence-ID-Beispiele {invalid} im Section-Prompt verletzen "
        f"EVIDENCE_ID_PATTERN ({EVIDENCE_ID_PATTERN}). Ein Modell, das sie "
        "nachahmt, erzeugt einen Anker, der nie in known_anchors steht."
    )


def test_prompt_restricts_seed_doc_form_to_actual_document_passages() -> None:
    """Issue #1300: seed_doc-Form nur für Zitate aus einer Dokumentpassage.

    Der Referenzlauf zeigte Persona-O-Töne mit erfundenen Ankern wie
    ``seed_doc:seed_aurora#chunk:0`` — Interview-Aussagen, die eine
    Dokumentherkunft behaupten, die der Lauf nie produzierte. Der Prompt
    muss die Form (b) ausdrücklich auf Zitate beschränken, die tatsächlich
    aus einer Seed-Dokument-Passage stammen, und Interview-Aussagen der
    ev_-Form (a) zuweisen — sonst kopiert das Modell genau die Kombination
    aus dem Positivbeispiel (contracts-first, PR #1312 Revert-Notiz).
    """
    rendered = _rendered_section_prompt()

    assert "ONLY when the quoted words actually come" in rendered, (
        "Der Section-Prompt beschränkt die seed_doc:-Form nicht auf Zitate, "
        "die tatsächlich aus der referenzierten Dokumentpassage stammen."
    )
    assert "simulation output, not document text" in rendered, (
        "Der Section-Prompt weist Interview-Aussagen nicht eindeutig als "
        "Simulations-Output aus — seed_doc:-Anker darauf sind erfundene "
        "Quellen (Issue #1300)."
    )


def test_prompt_positive_example_is_not_an_interview_with_seed_doc_anchor() -> None:
    """Issue #1300: Das Positivbeispiel darf Interview x seed_doc nicht zeigen.

    Das Modell kopiert Beispiele. Ein ✅-Beispiel, das eine Persona-Aussage
    mit seed_doc:-Anker zeigt, ist die Vorlage für genau die Fehlanbindung
    aus #1300 — unabhängig davon, was die Regel dazu sagt.
    """
    rendered = _rendered_section_prompt()

    # Nicht auf das erste "✅" im gesamten Prompt ankern: Section 1 enthält
    # bereits ein unabhängiges ✅ (Zeile ~25), und der Format-Hinweis in
    # Regel 5 zeigt VOR dem eigentlichen Positivbeispiel ein in sich
    # geschlossenes ``<simulated_quote ...>…</simulated_quote>``-Template
    # (Zeile ~189) — ein nicht verankertes "✅.*?</simulated_quote>" träfe
    # dessen schließenden Tag zuerst und ließe das echte Beispiel unten aus.
    example = re.search(
        r"✅ Correct shape.*?</simulated_quote>", rendered, re.DOTALL
    )
    assert example is not None, "Kein Positivbeispiel (✅ Correct shape) im Prompt."
    assert "seed_doc:" not in example.group(0), (
        "Das Positivbeispiel zeigt weiterhin einen seed_doc:-Anker an einer "
        "Persona-Aussage — die Kombination, die Issue #1300 verbietet."
    )
    # CodeRabbit-Finding (PR #1313): ein Platzhalter wie
    # "EVIDENCE_ID_OF_INTERVIEW_ANSWER" besteht ``test_prompt_evidence_id_literals_
    # match_the_contract`` nur, weil er nicht mit "ev_" beginnt — er zeigt dem
    # Modell aber keine formgültige ID zum Nachahmen. Das Positivbeispiel muss
    # selbst einen ``ev_``-Anker mit genau 32 Hex-Zeichen tragen.
    assert re.search(r'seed_anchor="ev_[0-9a-f]{32}"', example.group(0)), (
        "Das Positivbeispiel zeigt keinen formgültigen ev_-Anker "
        "(ev_ + 32 Hex-Zeichen) — ein Modell, das den Platzhalter nachahmt, "
        "erzeugt keine auflösbare Evidence-ID."
    )
