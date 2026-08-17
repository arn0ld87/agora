"""Regressionstests für die Vertrauenswürdigkeit der Report-Pipeline.

Referenz-Testlauf: report_d9023bd1f55a / sim_7058c126da03 (30 Agents,
315 Interaktionen, 5 Cluster, Echo-Chamber-Index 0.4317, Modus balanced).

Jeder Test hier bildet genau einen der P0-Defekte ab, die in diesem Lauf
sichtbar wurden. Sie sind bewusst eng geschnitten: sie prüfen die
Pipeline-Invariante, nicht die Formulierung eines konkreten LLM-Outputs.
"""
from __future__ import annotations

import pytest

from app.contracts.report_contract import EvidenceSourceKind
from app.services.evidence_binder import bind_evidence_to_claim
from app.services.evidence_entailment import (
    EntailmentVerdict,
    classify_evidence,
    extract_numeric_facts,
)
from app.services.report_agent.output_contract import (
    FinalContentRejected,
    sanitize_final_content,
)
from app.services.report_intent import ReportIntent, detect_report_intent, sections_for_intent


# ---------------------------------------------------------------------------
# Seed-Fixture: die Zahlen aus dem echten Testdokument
# ---------------------------------------------------------------------------

SEED_SENTENCES = [
    "72 % der Schülerinnen und Schüler bewerteten die zusätzliche Lernhilfe positiv.",
    "61 % der Lehrkräfte berichteten von Zeitersparnis bei mindestens einer "
    "wöchentlichen Routineaufgabe.",
    "48 % der Lehrkräfte berichteten zusätzlichen Aufwand durch Kontrolle von KI-Inhalten.",
    "37 % der Eltern äußerten Datenschutz- und Abhängigkeitsbedenken.",
    "70 % der Lehrkräfte sollen vor Einführung eine Basisschulung abgeschlossen haben.",
]


def _seed_item(text: str) -> dict:
    return {
        "snippet": text,
        "source_kind": EvidenceSourceKind.seed_corpus.value,
        "type": "seed_corpus",
    }


# ---------------------------------------------------------------------------
# Test 1 — Zahlen dürfen ihre Bezugsgruppe nicht wechseln
# ---------------------------------------------------------------------------


def test_1_percentage_may_not_migrate_to_wrong_stakeholder():
    """61 % gehört zu Zeitersparnis der Lehrkräfte, nicht zur Lernhilfe-Bewertung."""
    claim = "61 % der Lehrkräfte bewerten die zusätzliche Lernhilfe positiv."
    evidence = [_seed_item(s) for s in SEED_SENTENCES]

    results = [classify_evidence(claim, item) for item in evidence]

    assert all(r.verdict is not EntailmentVerdict.SUPPORTED for r in results), (
        "Ein Claim, der 61 % auf die Lernhilfe-Bewertung umdeutet, darf von "
        "keinem Seed-Satz gestützt werden — 61 % steht dort für Zeitersparnis."
    )


def test_1b_correct_percentage_attribution_is_supported():
    """Die korrekte Wiedergabe muss weiterhin als SUPPORTED durchgehen."""
    claim = "72 % der Schülerinnen und Schüler bewerteten die zusätzliche Lernhilfe positiv."
    result = classify_evidence(claim, _seed_item(SEED_SENTENCES[0]))
    assert result.verdict is EntailmentVerdict.SUPPORTED


def test_1c_training_target_is_not_approval():
    """'70 % sollen geschult sein' ist eine Zielvorgabe, keine Zustimmungsquote."""
    claim = "70 % der Lehrkräfte stimmen der Einführung zu."
    result = classify_evidence(claim, _seed_item(SEED_SENTENCES[4]))
    assert result.verdict is not EntailmentVerdict.SUPPORTED


def test_1e_rendered_prose_must_flag_the_wrong_attribution():
    """Der SICHTBARE Reporttext muss die Falschzuordnung kenntlich machen.

    Der E2E-Lauf gegen sim_7058c126da03 zeigte: Das Entailment verwarf die
    Aussage korrekt (0 Claims, Routing zur Hypothese) — im gelesenen Report
    stand sie trotzdem, weil der Abschnitt die rohe LLM-Prosa ist. Dieser
    Test prüft deshalb den gerenderten Text, nicht ``claims[]``.

    Issue #1356 — Wechsel von "entfernen" zu "kennzeichnen". Die Deckung
    trennt diesen Fall nicht von einer korrekten Paraphrase:

        "…forderten bereits im Vorfeld eine Verschiebung"   0.50  korrekt
        "…bewerteten positiv und berichteten von …"         0.56  erfunden

    Die erfundene Aussage liegt *höher*. Eine Schwelle, die sie fängt,
    löscht die korrekte mit — im Referenzlauf kostete das 28 belegte
    Aussagen. Bis ein semantisches Urteil zur Verfügung steht (Issue #1357),
    bleibt die Aussage deshalb sichtbar und trägt ihre Einschränkung.
    """
    from app.services.report_agent.text_verification import (
        UNVERIFIED_MARKER,
        verify_prose,
    )

    prose = (
        "Im Zentrum der Lehrkräfte-Reaktionen steht eine positive Bewertung. "
        "61 Prozent der Lehrkräfte bewerteten die zusätzliche Lernhilfe positiv "
        "und berichteten von einer Zeitersparnis bei mindestens einer "
        "wöchentlichen Routineaufgabe.\n"
        "72 % der Schülerinnen und Schüler bewerteten die zusätzliche Lernhilfe positiv."
    )
    pool = [_seed_item(s) for s in SEED_SENTENCES]

    result = verify_prose(prose, pool)

    flagged_sentence = next(
        (line for line in result.content.splitlines() if "61" in line), ""
    )
    assert UNVERIFIED_MARKER in flagged_sentence, (
        "Die Falschzuordnung '61 % → Lernhilfe positiv' steht ohne Kennzeichnung "
        f"im gerenderten Report:\n{result.content}"
    )
    # Der korrekt belegte Seed-Fakt muss erhalten bleiben — und zwar ohne Marker.
    assert "72" in result.content
    assert result.unverified, "Die beanstandete Aussage muss auditierbar bleiben"
    assert all(
        statement.verdict is not EntailmentVerdict.SUPPORTED
        for statement in result.unverified
    )


def test_1f_rejected_prose_statement_becomes_a_hypothesis():
    from app.services.report_agent.text_verification import verify_prose

    prose = (
        "61 Prozent der Lehrkräfte bewerteten die zusätzliche Lernhilfe positiv "
        "und berichteten von einer Zeitersparnis bei mindestens einer "
        "wöchentlichen Routineaufgabe."
    )
    result = verify_prose(prose, [_seed_item(s) for s in SEED_SENTENCES])
    # Issue #1356: beanstandet wird sie weiterhin — entfernt nur noch bei
    # aktivem Widerspruch. Beide Ausgänge landen in ``flagged``.
    assert result.flagged
    hypothesis = result.flagged[0].as_hypothesis(1)
    assert hypothesis["hypothesis_text"]
    assert "fließtext" in hypothesis["rationale"].lower()


def test_1i_prose_hypothesis_ids_satisfy_the_contract():
    """Die aus dem Fließtext erzeugten Hypothesen müssen valide sein.

    Zweiter Fall desselben Fehlertyps wie bei gap_id: eine sprechende ID
    ("hypothesis_text_01") verletzt ^hypothesis_\\d{2,}$ und ließ die gesamte
    EvidenceMap-Validierung — und damit den ganzen Report — scheitern.
    """
    from app.contracts.report_contract import ReportSectionHypothesisModel
    from app.services.report_agent.text_verification import verify_prose

    prose = (
        "61 Prozent der Lehrkräfte bewerteten die zusätzliche Lernhilfe positiv "
        "und berichteten von einer Zeitersparnis bei mindestens einer "
        "wöchentlichen Routineaufgabe."
    )
    result = verify_prose(prose, [_seed_item(s) for s in SEED_SENTENCES])
    assert result.flagged

    for position, statement in enumerate(result.flagged, start=1):
        ReportSectionHypothesisModel.model_validate(statement.as_hypothesis(position))


def test_1g_prose_without_evidence_pool_is_left_untouched():
    """Ohne Vergleichsbasis darf die Prüfung den Bericht nicht leeren."""
    from app.services.report_agent.text_verification import verify_prose

    prose = "61 Prozent der Lehrkräfte bewerteten die Lernhilfe positiv."
    result = verify_prose(prose, [])
    assert result.content == prose
    assert not result.rejected


def test_1h_analytical_prose_without_numbers_survives():
    """Nur quantitative Aussagen werden geprüft — Einordnung bleibt stehen."""
    from app.services.report_agent.text_verification import verify_prose

    prose = (
        "Die Elternschaft reagiert spürbar zurückhaltender als die Lehrkräfte "
        "und positioniert sich als Korrektiv gegenüber dem Vorhaben."
    )
    result = verify_prose(prose, [_seed_item(s) for s in SEED_SENTENCES])
    assert result.content == prose
    assert not result.rejected


def test_1d_numeric_extraction_binds_number_to_group_and_predicate():
    facts = extract_numeric_facts(SEED_SENTENCES[1])
    assert facts, "Prozentwert muss erkannt werden"
    fact = facts[0]
    assert fact.value == pytest.approx(61.0)
    assert "lehrkr" in fact.subject.lower()
    assert "zeitersparnis" in fact.predicate.lower()


def test_1d_en_english_seeds_yield_numeric_facts():
    """Englische Seeds müssen ebenfalls Fakten liefern (Handover P2.7).

    _split_subject_predicate war auf deutsche Nomen-Großschreibung
    zugeschnitten; _PERCENT_RE kannte nur 'Prozent' und '%', nicht das
    englische 'percent'. Englische Sätze lieferten subject='' → 0 Fakten
    → die Fließtext-Prüfung übersprang sie still. Fix: Regex um 'percent'
    und 'of' erweitert, Fallback nimmt Bezugsgruppe bis zum ersten
    bekannten Report-Verb.
    """
    cases = [
        ("61 percent of teachers rated the learning aid positively.", "teachers"),
        ("48 percent of parents reported that control caused work.", "parents"),
        ("61% of teachers reported time savings.", "teachers"),
        ("70 percent of students stated they liked it.", "students"),
    ]
    for sentence, expected_subject in cases:
        facts = extract_numeric_facts(sentence)
        assert facts, f"kein Fakt extrahiert: {sentence!r}"
        fact = facts[0]
        assert fact.subject.lower() == expected_subject, (
            f"subject={fact.subject!r} erwartet={expected_subject!r} — {sentence!r}"
        )
        assert fact.predicate, f"leeres Prädikat: {sentence!r}"


_WORD_ORDER_EVIDENCE = "31 Honorarkräfte stehen auf der Personalliste des Trägers."

#: Reine Umstellung: identisches Wortmaterial, nur das Vorfeld wechselt.
#: Deutsch besetzt das Vorfeld frei, der Aussageteil darf links der Zahl stehen.
_WORD_ORDER_VARIANTS = [
    "31 Honorarkräfte stehen auf der Personalliste des Trägers.",
    "Auf der Personalliste des Trägers stehen 31 Honorarkräfte.",
]

#: Umstellung *und* Verbwechsel ("stehen auf" → "werden geführt"). Das ist
#: Synonymie, nicht Wortstellung — der lexikalische Vergleich in
#: ``coverage_ratio`` kann das nicht überbrücken. Bewusst als offene Lücke
#: geführt statt stillschweigend übergangen; siehe #1217.
_PARAPHRASE_VARIANTS = [
    "Auf der Personalliste des Trägers werden 31 Honorarkräfte geführt.",
    "Der Träger führt auf seiner Personalliste 31 Honorarkräfte.",
]


@pytest.mark.parametrize("sentence", _WORD_ORDER_VARIANTS + _PARAPHRASE_VARIANTS)
def test_1j_predicate_covers_the_whole_sentence_not_only_the_tail(sentence):
    """Das Prädikat darf nicht davon abhängen, wo im Satz die Zahl steht.

    ``extract_numeric_facts`` las den Aussageteil nur aus ``sentence[match.end():]``
    — dem Text *rechts* der Zahl. Im deutschen Vorfeld steht er oft links, dann
    blieb ein Fragment übrig ("geführt") und die Deckungsprüfung verglich gegen
    fast nichts. Reproduziert an #1209/#1217 (Report ``report_4786a1a3d4ea``,
    Section 2): "31 Honorarkräfte" wurde aus dem Fließtext entfernt, obwohl der
    Satz wörtlich im Evidence-Pool steht.
    """
    facts = extract_numeric_facts(sentence)
    assert facts, f"kein Fakt extrahiert: {sentence!r}"
    fact = facts[0]
    assert fact.value == pytest.approx(31.0)
    assert "honorarkr" in fact.subject.lower()
    assert "personalliste" in fact.predicate.lower(), (
        f"Aussageteil links der Zahl verloren: predicate={fact.predicate!r} — {sentence!r}"
    )


@pytest.mark.parametrize("sentence", _WORD_ORDER_VARIANTS)
def test_1k_belegter_fakt_ist_bei_umstellung_kein_widerspruch(sentence):
    """Eine Umstellung darf einen belegten Fakt nicht zum Widerspruch machen.

    ``CONTRADICTED`` ist das teuerste Urteil: es entfernt den Satz aus dem
    Fließtext *und* schlägt über ``detect_contradiction_penalty`` auf die
    Confidence durch. Vor dem Fix trugen zwei der vier Varianten
    ``predicate_overreach`` mit "Deckung 0.00" — die Deckung war nicht 0, sie
    war nie gemessen worden.
    """
    result = classify_evidence(sentence, {"snippet": _WORD_ORDER_EVIDENCE})
    assert result.verdict is not EntailmentVerdict.CONTRADICTED, (
        f"{sentence!r} → {result.verdict.value} ({result.reason}); checks={result.checks}"
    )


@pytest.mark.parametrize("sentence", _WORD_ORDER_VARIANTS)
def test_1l_umgestellter_belegter_satz_bleibt_im_fliesstext(sentence):
    """Regression am Seam, an dem der Defekt sichtbar wurde."""
    from app.services.report_agent.text_verification import verify_prose

    result = verify_prose(sentence, [_seed_item(_WORD_ORDER_EVIDENCE)])
    assert not result.rejected, (
        f"belegter Satz entfernt: {sentence!r} — "
        f"{result.rejected[0].verdict.value}: {result.rejected[0].reason}"
    )


@pytest.mark.parametrize("sentence", _PARAPHRASE_VARIANTS)
def test_1m_paraphrasierter_belegter_satz_bleibt_im_fliesstext(sentence):
    # Issue #1356 schließt die als #1217 offengehaltene Lücke — allerdings
    # nicht dadurch, dass die Deckung besser gemessen würde. Sie wird nach
    # wie vor lexikalisch bestimmt und liegt bei einem Verbwechsel weiterhin
    # unter der Schwelle. Geändert hat sich die Konsequenz: eine zu geringe
    # Deckung ist kein Widerspruch mehr, sondern ein nicht entscheidbarer
    # Fall, und der löscht nicht. Das eigentliche Messproblem bleibt offen
    # und wird in #1357 mit einem semantischen Urteil angegangen.
    from app.services.report_agent.text_verification import verify_prose

    result = verify_prose(sentence, [_seed_item(_WORD_ORDER_EVIDENCE)])
    assert not result.rejected


def test_1n_leeres_praedikat_ist_insufficient_nicht_contradicted():
    """"Deckung 0.00" heißt "nicht messbar", nicht "widerlegt" (#1317).

    ``coverage_ratio`` liefert 0.0 sowohl, wenn der Claim tatsächlich mehr
    behauptet als die Quelle deckt, als auch, wenn das Prädikat nach dem
    Stopword-/Kurzwort-Filter (``_content_tokens``) leer bleibt — dann ist
    gar nichts gemessen worden. Ein kurzes Prädikat wie "sind da" darf den
    Satz nicht als Widerspruch aus dem Fließtext werfen.
    """
    claim = "82 % der Eltern sind da."
    evidence = "82 % der Eltern sind da, sagt die Studie."

    result = classify_evidence(claim, {"snippet": evidence})

    assert result.verdict is EntailmentVerdict.INSUFFICIENT, (
        f"{result.verdict.value} ({result.reason}); checks={result.checks}"
    )
    assert "predicate_not_measurable" in result.checks


@pytest.mark.parametrize(
    "evidence",
    [
        "82 % der Eltern sind nicht da.",
        "82 % der Eltern sind keine Teilnehmer.",
    ],
)
def test_1n_verneinung_bleibt_widerspruch_trotz_kurzem_praedikat(evidence):
    """Die Untergrenze aus #1317 darf keine Verneinung verschlucken.

    ``nicht`` steht selbst in ``_STOPWORDS`` — "sind da" und "sind nicht da"
    reduzieren beide auf ein leeres Content-Token-Set. Ohne Polaritaetspruefung
    haette der neue ``predicate_not_measurable``-Zweig einen echten
    Verneinungswiderspruch bei gleicher Zahl und Bezugsgruppe als "nicht
    pruefbar" durchgewinkt.
    """
    claim = "82 % der Eltern sind da."

    result = classify_evidence(claim, {"snippet": evidence})

    assert result.verdict is EntailmentVerdict.CONTRADICTED, (
        f"{result.verdict.value} ({result.reason}); checks={result.checks}"
    )
    assert "polarity_mismatch" in result.checks


def test_1n_seam_nicht_messbarer_satz_wird_ehrlich_begruendet_markiert():
    """Seam-Regression zu #1317: der Satz wird beanstandet, aber ehrlich.

    Was #1317 geaendert hat, ist die *Begruendung*. Vorher behauptete Agora
    einen Widerspruch ("Deckung 0.00") und setzte ueber
    ``bind_evidence_to_claim`` zusaetzlich ``contradicts_claim=True``.
    Nachher heisst es korrekt: nicht pruefbar.

    Was #1356 geaendert hat, ist die *Konsequenz*. Die frueher hier
    dokumentierte Abgrenzung — ein nicht pruefbarer Satz wird entfernt, weil
    ihn stehen zu lassen eine ADR-0002-Entscheidung waere — ist genau diese
    Entscheidung, und sie ist getroffen: ein Referenzlauf verlor 28 Aussagen,
    die weit ueberwiegende Mehrheit davon belegt. Der Satz bleibt jetzt
    stehen und traegt seine Einschraenkung sichtbar. Gegated bleibt er
    trotzdem: er zaehlt nicht als Beleg und wandert in die Hypothesen.
    """
    from app.services.report_agent.text_verification import (
        UNVERIFIED_MARKER,
        verify_prose,
    )

    claim = "82 % der Eltern sind da."
    evidence = "82 % der Eltern sind da, sagt die Studie."

    result = verify_prose(claim, [_seed_item(evidence)])

    assert not result.rejected, "Nicht pruefbar ist kein Widerspruch."
    assert result.unverified, "Ein nicht pruefbarer numerischer Satz bleibt gegated."
    flagged = result.unverified[0]
    assert flagged.verdict is EntailmentVerdict.INSUFFICIENT, (
        f"{flagged.verdict.value}: {flagged.reason}"
    )
    assert "Deckung" not in flagged.reason
    assert UNVERIFIED_MARKER in result.content

    # Gegenprobe auf dem Binder-Pfad: kein Widerspruchs-Flag mehr.
    def embed(text: str):  # identische Vektoren => cosine 1.0
        return [1.0, 0.0, 0.0]

    bound = bind_evidence_to_claim(claim, [_seed_item(evidence)], embed, threshold=0.5)
    assert bound, "Kandidat sollte oberhalb des Thresholds gebunden werden."
    assert bound[0]["entailment"] == EntailmentVerdict.INSUFFICIENT.value
    assert "contradicts_claim" not in bound[0]


# ---------------------------------------------------------------------------
# Test 2 — kein Thought-/Tool-Leak im sichtbaren Content
# ---------------------------------------------------------------------------

LEAK_SAMPLES = [
    "Thought: The interview tool is unavailable.\nLet me use quick_search instead.",
    "Action: quick_search\nObservation: nothing found",
    "I need to ground claims in evidence before writing.",
    "I will now call the tool_call block again.",
    '<tool_call>{"name": "quick_search"}</tool_call>',
]


@pytest.mark.parametrize("raw", LEAK_SAMPLES)
def test_2_thought_and_tool_planning_never_reaches_content(raw):
    with pytest.raises(FinalContentRejected):
        sanitize_final_content(raw)


def test_2b_mixed_content_keeps_only_the_report_body():
    raw = (
        "Thought: I need to check the stakeholder positions first.\n"
        "Action: quick_search\n"
        "Final Answer:\n"
        "**Zustimmung**\n\n"
        "Die Lehrkräfte im Szenario bewerten die Zeitersparnis überwiegend positiv."
    )
    cleaned = sanitize_final_content(raw)
    assert "Thought:" not in cleaned.content
    assert "Action:" not in cleaned.content
    assert "Zeitersparnis" in cleaned.content
    assert cleaned.removed_segments


def test_2d_unclosed_tool_call_is_rejected():
    """Ein geöffneter, nie geschlossener Tool-Call darf nicht durchrutschen.

    Aus dem Full-Report-E2E: das Modell lief in eine Endlosschleife und
    schrieb ein abgeschnittenes '<tool_call>' in den Abschnitt. Der Sanitizer
    entfernte nur vollständige Blöcke, das Fragment blieb im Report stehen.
    """
    raw = (
        "Die simulierten Gruppen äußern sich überwiegend zurückhaltend zum Vorhaben.\n"
        '<tool_call>\n{"name": "quick_search"'
    )
    cleaned = sanitize_final_content(raw)
    assert "<tool_call>" not in cleaned.content
    assert "quick_search" not in cleaned.content
    assert "zurückhaltend" in cleaned.content


def test_2e_degenerate_repetition_is_rejected():
    """LLM-Endlosschleifen sind kein Abschnittsinhalt."""
    raw = "Final Answer:\n" + ('function_calls>quick_search</invoke">' * 60)
    with pytest.raises(FinalContentRejected):
        sanitize_final_content(raw)


def test_2c_clean_content_passes_unchanged():
    raw = "Die simulierten Eltern äußern vor allem Datenschutzbedenken."
    cleaned = sanitize_final_content(raw)
    assert cleaned.content == raw
    assert not cleaned.removed_segments


def test_2f_min_content_chars_threshold_is_conservative():
    """MIN_CONTENT_CHARS muss konservativ sein (Handover P2.9).

    Herleitung an realen Läufen: kürzester echter Section-Inhalt 4230
    Zeichen (report_e2e_trust01), längster Fallback-Text 217 Zeichen
    (report_e2e_full01/section_03). 40 liegt deutlich unter beiden —
    es fängt nur leer/fast-leer gerenderte Outputs ab, nicht Fallback-Text
    (den filtert is_fallback_content semantisch).
    """
    from app.services.report_agent.output_contract import (
        MIN_CONTENT_CHARS,
        is_fallback_content,
    )

    # Schwelle ist klein genug für kürzeste reale Section (4230 chars)
    assert MIN_CONTENT_CHARS < 4230
    # Schwelle ist groß genug, um leere Outputs abzufangen
    assert MIN_CONTENT_CHARS >= 10
    # Fallback-Text wird nicht durch MIN_CONTENT_CHARS gefangen, sondern
    # durch is_fallback_content — das ist ein separater Guard.
    fallback = (
        "Dieser Abschnitt konnte nicht generiert werden: Das Modell "
        "lieferte ausschließlich interne Arbeitsschritte."
    )
    assert len(fallback) > MIN_CONTENT_CHARS
    assert is_fallback_content(fallback)


# ---------------------------------------------------------------------------
# Test 3 — Ähnlichkeit ist kein Beweis
# ---------------------------------------------------------------------------


def test_3_high_retrieval_score_alone_does_not_support_claim():
    """Themengleiche, aber nicht belegende Evidence: hoher Score, kein Support."""

    def embed(text: str):  # identische Vektoren => cosine 1.0
        return [1.0, 0.0, 0.0]

    claim = "Die Eltern lehnen die Plattform mehrheitlich ab."
    candidates = [
        {
            "snippet": "37 % der Eltern äußerten Datenschutz- und Abhängigkeitsbedenken.",
            "source_kind": EvidenceSourceKind.seed_corpus.value,
        }
    ]

    bound = bind_evidence_to_claim(claim, candidates, embed, threshold=0.5)
    assert bound, "Kandidat muss als Retrieval-Treffer erhalten bleiben"
    item = bound[0]
    assert item["retrieval_score"] >= 0.5
    assert item["supports_claim"] is False, (
        "Cosine-Similarity darf supports_claim nicht setzen — 37 % Bedenken "
        "belegen keine mehrheitliche Ablehnung."
    )
    assert item["entailment"] in {
        EntailmentVerdict.RELATED_ONLY.value,
        EntailmentVerdict.INSUFFICIENT.value,
        EntailmentVerdict.CONTRADICTED.value,
    }


def test_3b_retrieval_score_and_supports_claim_are_separate_fields():
    def embed(text: str):
        return [1.0, 0.0]

    bound = bind_evidence_to_claim(
        "72 % der Schülerinnen und Schüler bewerteten die zusätzliche Lernhilfe positiv.",
        [_seed_item(SEED_SENTENCES[0])],
        embed,
        threshold=0.5,
    )
    assert bound
    assert "retrieval_score" in bound[0]
    assert "supports_claim" in bound[0]
    assert bound[0]["supports_claim"] is True
    assert bound[0]["entailment"] == EntailmentVerdict.SUPPORTED.value


# ---------------------------------------------------------------------------
# Test 4 — Provenance: Simulationsevidence ist kein Seed-Fakt
# ---------------------------------------------------------------------------


def test_4_agent_action_is_a_distinct_source_kind():
    assert EvidenceSourceKind.agent_action.value == "agent_action"
    assert EvidenceSourceKind.agent_action is not EvidenceSourceKind.seed_corpus


def test_4b_agent_action_is_not_persisted_as_seed_corpus():
    from app.services.report_agent.evidence import normalize_source_kind

    item = {"type": "agent_action", "snippet": "Agent 12 teilte den Beitrag."}
    assert normalize_source_kind(item) == EvidenceSourceKind.agent_action.value


def test_4c_unknown_evidence_does_not_silently_default_to_seed_corpus():
    from app.services.report_agent.evidence import normalize_source_kind

    item = {"type": "model_generated_inference", "snippet": "Vermutlich…"}
    assert normalize_source_kind(item) != EvidenceSourceKind.seed_corpus.value


def test_4e_explicit_inferred_source_kind_is_respected():
    """Ein explizit gesetztes ``source_kind="inferred"`` muss gewonnen werden.

    CodeRabbit PR #929: ``normalize_source_kind`` prüfte explizite Werte gegen
    ``_TYPE_TO_SOURCE_KIND.values()`` — die Menge schloss ``inferred`` aus.
    Ein Caller, der ein Modellableitungs-Fakt bewusst als ``inferred``
    markierte, wurde ignoriert und der interne ``type`` übernahm. Der Docstring
    sagt aber: „Ein explizit gesetztes source_kind gewinnt.“
    """
    from app.services.report_agent.evidence import normalize_source_kind

    item = {"type": "seed_corpus", "source_kind": "inferred", "snippet": "Vermutlich…"}
    assert normalize_source_kind(item) == EvidenceSourceKind.inferred.value


def test_4d_every_evidence_type_maps_to_a_real_provenance():
    """Kein produktiver EvidenceType darf als 'inferred' durchfallen.

    Der E2E-Lauf gegen sim_7058c126da03 lieferte 125 von 125 Evidence-Items
    mit ``type='graph_fact'``. Weil das Mapping diesen Wert nicht kannte,
    landeten alle auf ``inferred`` — echte Graph-Evidence sah damit aus wie
    eine Modellableitung. Dieser Test pinnt die Vollstaendigkeit.
    """
    from app.contracts.report_contract import EvidenceType
    from app.services.report_agent.evidence import normalize_source_kind

    unmapped = [
        t.value
        for t in EvidenceType
        if t is not EvidenceType.model_generated_inference
        and normalize_source_kind({"type": t.value}) == EvidenceSourceKind.inferred.value
    ]
    assert not unmapped, f"EvidenceType(s) ohne Provenance-Zuordnung: {unmapped}"


# ---------------------------------------------------------------------------
# Test 5 — Fallback-Fehlertext erzeugt keinen Claim
# ---------------------------------------------------------------------------


def test_5_llm_fallback_error_text_produces_no_claims():
    from app.services.report_agent.output_contract import is_fallback_content

    fallback = (
        "(Dieser Abschnitt konnte nicht generiert werden: LLM lieferte eine "
        "leere Antwort. Report-ID: report_d9023bd1f55a, Abschnitt 7.)"
    )
    assert is_fallback_content(fallback) is True


def test_5b_claim_extraction_skips_fallback_sections():
    from app.services.report_agent.output_contract import is_fallback_content

    assert is_fallback_content("Die simulierten Eltern äußern Datenschutzbedenken.") is False


def test_5c_fallback_section_data_gap_satisfies_the_contract():
    """Die Ersatz-Datenlücke einer fehlgeschlagenen Section muss valide sein.

    Der E2E-Lauf scheiterte an ``gap_id='gap_section_03'``:
    ReportSectionDataGapModel erzwingt ``^gap_\\d{2,}$``. Ein einziger
    ungültiger Ersatz-Gap ließ die gesamte EvidenceMap-Validierung und damit
    den kompletten Report fehlschlagen.
    """
    from app.contracts.report_contract import ReportSectionDataGapModel

    ReportSectionDataGapModel.model_validate({
        "gap_id": f"gap_{3:02d}",
        "gap_reason": "Abschnitt konnte nicht generiert werden (LLM-Fehler).",
        "claim_text": "Zentrale Kritikpunkte",
    })


# ---------------------------------------------------------------------------
# Test 6 — fehlgeschlagene Pflichtsection ⇒ INCOMPLETE
# ---------------------------------------------------------------------------


def test_6_failed_required_section_yields_incomplete_status():
    from app.models.report import ReportStatus
    from app.services.report_agent.output_contract import resolve_report_status

    status = resolve_report_status(
        total_sections=11,
        failed_section_indices=[10],
        required_section_indices=[10],
    )
    assert status == ReportStatus.INCOMPLETE


def test_6b_all_sections_ok_yields_completed():
    from app.models.report import ReportStatus
    from app.services.report_agent.output_contract import resolve_report_status

    status = resolve_report_status(
        total_sections=11,
        failed_section_indices=[],
        required_section_indices=list(range(1, 12)),
    )
    assert status == ReportStatus.COMPLETED


# ---------------------------------------------------------------------------
# Test 7 — Section-Metadata landet in ReportV3
# ---------------------------------------------------------------------------


def test_7_section_metadata_reaches_report_v3():
    from app.services.report_agent.metadata_merge import merge_section_metadata

    sections = [
        {
            "section_index": 2,
            "structured_metadata": {
                "personas": [
                    {
                        "id": "persona_01",
                        "voice_register": "neutral-de",
                        "alter_range": "35–50",
                        "beruf": "Lehrkraft",
                        "region": "Sachsen-Anhalt",
                    }
                ],
                "segments": [
                    {
                        "id": "seg_01",
                        "name": "Lehrkräfte",
                        "beschreibung": "Unterrichtende an Sekundarschulen",
                    }
                ],
                "friction_points": [
                    {
                        "id": "fp_01",
                        "beschreibung": "Kontrollaufwand für KI-Inhalte",
                        "severity": "high",
                    }
                ],
            },
        }
    ]

    merged = merge_section_metadata(sections)
    assert [p.id for p in merged.personas] == ["persona_01"]
    assert [s.id for s in merged.segments] == ["seg_01"]
    assert [f.id for f in merged.friction_points] == ["fp_01"]


def test_7b_persona_table_schema_to_report_v3_chain():
    """DoD-Punkt 7 Teilbeleg: Personas/Segmente in ReportV3 (Handover P1.3).

    Der echte E2E-Beweis braucht einen Full-Report-Lauf gegen eine lebende
    Simulation (report_e2e_full01 starb am gap_id-Bug vor Section 3).
    Dieser Test pinnt die Kette, die im Lauf durchlaufen wird:

      Section-Titel 'Persona-Tabelle'
        → _section_schema_for wählt PersonaTable-DTO
        → LLM liefert structured_metadata.personas
        → merge_section_metadata sammelt sie in MergedMetadata.personas
        → as_report_v3_kwargs() liefert sie für ReportV3

    Die parametrisierten Schema-Tests in test_report_agent_strict_schema
    decken Stufe 1 ab; hier wird Stufe 2+3 (Merge → ReportV3-Kwargs) für
    Personas UND Segmente gepinnt.
    """
    from app.services.report_agent.metadata_merge import merge_section_metadata
    from app.services.report_agent.schemas import _section_schema_for, _make_table_metadata
    from app.contracts.report_v3 import Persona, Segment

    # Stufe 1: Section-Titel → korrektes DTO
    assert _section_schema_for("Persona-Tabelle") is _make_table_metadata(Persona)
    assert _section_schema_for("Segment-Tabelle") is _make_table_metadata(Segment)

    # Stufe 2+3: structured_metadata mit personas/segments → MergedMetadata → ReportV3-Kwargs
    sections = [
        {
            "section_index": 3,
            "section_title": "Persona-Tabelle",
            "structured_metadata": {
                "personas": [
                    {
                        "id": "persona_05",
                        "voice_register": "formal-de",
                        "alter_range": "45–60",
                        "beruf": "Schulleitung",
                        "region": "Sachsen-Anhalt",
                    },
                    {
                        "id": "persona_07",
                        "voice_register": "neutral-de",
                        "alter_range": "30–45",
                        "beruf": "Lehrkraft",
                        "region": "Bayern",
                    },
                ],
            },
        },
        {
            "section_index": 2,
            "section_title": "Segment-Tabelle",
            "structured_metadata": {
                "segments": [
                    {"id": "seg_02", "name": "Schulleitungen", "beschreibung": "Administrative Ebene"},
                ],
            },
        },
    ]
    merged = merge_section_metadata(sections)
    assert [p.id for p in merged.personas] == ["persona_05", "persona_07"]
    assert [s.id for s in merged.segments] == ["seg_02"]

    # Stufe 3: ReportV3-Kwargs enthalten nur befüllte Slots
    kwargs = merged.as_report_v3_kwargs()
    assert "personas" in kwargs
    assert "segments" in kwargs
    assert "friction_points" not in kwargs  # leer → nicht befüllt
    assert all(isinstance(p, Persona) for p in kwargs["personas"])
    assert all(isinstance(s, Segment) for s in kwargs["segments"])


# ---------------------------------------------------------------------------
# Test 8 — ReportV3 → Markdown/HTML bleibt semantisch identisch
# ---------------------------------------------------------------------------


def test_8_markdown_and_json_render_the_same_structured_items():
    """ReportV3 ist die kanonische Quelle: was im JSON steht, steht im Markdown.

    HTML wird im Frontend aus genau diesem Markdown/JSON gerendert; der
    Backend-seitig prüfbare Teil der Invariante ist JSON ≡ Markdown.
    """
    from datetime import datetime, timezone

    from app.contracts.report_v3 import FrictionPoint, Persona, ReportV3
    from app.services.report_agent.markdown_renderer import render_report_v3

    report = ReportV3(
        report_id="report_d9023bd1f55a",
        generated_at=datetime.now(timezone.utc),
        personas=[
            Persona(
                id="persona_01",
                voice_register="neutral-de",
                alter_range="35–50",
                beruf="Lehrkraft",
                region="Sachsen-Anhalt",
            )
        ],
        friction_points=[
            FrictionPoint(
                id="fp_01",
                beschreibung="Kontrollaufwand für KI-Inhalte",
                severity="high",
            )
        ],
    )

    markdown = render_report_v3(report)
    payload = report.model_dump(mode="json")

    for needle in ("persona_01", "Kontrollaufwand für KI-Inhalte"):
        assert needle in markdown, f"{needle} fehlt im Markdown"

    assert [p["id"] for p in payload["personas"]] == ["persona_01"]
    assert [f["id"] for f in payload["friction_points"]] == ["fp_01"]


# ---------------------------------------------------------------------------
# Test 9 — "Was denken die Leute?" ⇒ kompakter Opinion-Report
# ---------------------------------------------------------------------------


def test_9_opinion_question_selects_compact_preset():
    assert detect_report_intent("Was denken die Leute?") is ReportIntent.OPINION

    sections = sections_for_intent(ReportIntent.OPINION)
    assert len(sections) == 7  # 6 + Handlungsempfehlung (#1322)
    assert len(sections) < len(sections_for_intent(ReportIntent.FULL))
    joined = " ".join(sections).lower()
    for absent in ("content-idee", "positionierung", "multiplikator"):
        assert absent not in joined, f"{absent} gehört nicht in den Opinion-Report"


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Was denken die Leute über die Plattform?", ReportIntent.OPINION),
        ("Wie ist die Stimmung bei den Eltern?", ReportIntent.OPINION),
        ("Welche Risiken drohen bei der Einführung?", ReportIntent.RISK),
        ("Vergleiche Variante A und Variante B.", ReportIntent.COMPARISON),
    ],
)
def test_9b_intent_detection_matrix(question, expected):
    assert detect_report_intent(question) is expected


def test_9c_vor_1322_geplante_outline_bleibt_ein_bekanntes_preset():
    """Codex-Review PR #1331: Bestandsreports dürfen beim Resume nicht brechen.

    Die Handlungsempfehlung kam mit #1322 nachträglich in die Presets. Eine
    Outline, die davor geplant und persistiert wurde, trägt sie nicht — ohne
    Lockerung fällt sie beim Resume auf den Full-Report-Pflichtsatz zurück und
    der Report endet als ``incomplete``, obwohl er zum Planungszeitpunkt
    korrekt war.

    Die Lockerung bleibt eng: sie gilt nur für die Empfehlung selbst, nicht
    für beliebige Kurz-Outlines.
    """
    from app.services.report_agent.contract_validator import (  # noqa: PLC0415
        matches_known_preset,
    )
    from app.services.report_prompts import (  # noqa: PLC0415
        RECOMMENDATION_SECTION_TITLE,
    )

    aktuell = sections_for_intent(ReportIntent.OPINION)
    legacy = [title for title in aktuell if title != RECOMMENDATION_SECTION_TITLE]
    assert len(legacy) == len(aktuell) - 1

    assert matches_known_preset(aktuell)
    assert matches_known_preset(legacy)
    # EXPLORATIVE hat bewusst keine Empfehlung — unverändert ein Treffer.
    assert matches_known_preset(sections_for_intent(ReportIntent.EXPLORATIVE))
    # Der Full-Report bleibt gegen versehentliche Verkürzung geschützt.
    assert not matches_known_preset(["Kurzfazit", "Irgendwas"])
    assert not matches_known_preset(legacy[:-1])


# ---------------------------------------------------------------------------
# Test 10 — Full-Report bleibt unverändert
# ---------------------------------------------------------------------------


def test_10_full_report_preset_keeps_all_twelve_sections():
    sections = sections_for_intent(ReportIntent.FULL)
    assert len(sections) == 12
    # #1322: Der Bericht endet mit dem Beschlussvorschlag, nicht mit dem,
    # was er nicht weiß.
    assert sections[-1] == "Handlungsempfehlung"


def test_10b_unspecific_question_defaults_to_full():
    assert detect_report_intent("Erstelle eine umfassende Analyse des Vorhabens.") is (
        ReportIntent.FULL
    )


# ---------------------------------------------------------------------------
# Test 11 — LLM-Judge: ADR-0002-Anker und Builder (P2.8)
# ---------------------------------------------------------------------------


def _qualitative_claim_and_evidence():
    """Claim/Evidence-Paar, das im Regelpfad RELATED_ONLY liefert.

    Ohne Zahl- oder Mengen-Claim fällt es in den qualitativen Pfad
    (Regel 3 in classify_evidence). Nur hier greift der Judge.
    """
    claim = "Die Eltern sind besorgt wegen des Datenschutzes."
    evidence = {
        "snippet": (
            "Eltern äußern in der Befragung Bedenken gegen die Datenverarbeitung "
            "der neuen Plattform."
        ),
        "source_kind": "seed_corpus",
    }
    return claim, evidence


def test_11a_judge_supported_is_downgraded_to_related_only():
    """ADR-0002: Der LLM-Judge darf SUPPORTED nie erzeugen.

    Im qualitativen Pfad gibt es kein regelbasiertes SUPPORTED. Ein
    Judge-SUPPORTED wäre also ein ungedeckter Claim, der durch das Tor
    geschlüpft wäre. Der Klassifikator muss es auf RELATED_ONLY abschwächen.
    """
    claim, evidence = _qualitative_claim_and_evidence()

    def judge(_claim, _evidence):
        return "SUPPORTED"

    result = classify_evidence(claim, evidence, judge=judge)
    assert result.verdict is EntailmentVerdict.RELATED_ONLY
    assert "judge_downgraded" in result.checks


def test_11b_judge_contradicted_is_passed_through():
    """Judge-CONTRADICTED wird durchgereicht — Abschwächung ist erlaubt."""
    claim, evidence = _qualitative_claim_and_evidence()

    def judge(_claim, _evidence):
        return "CONTRADICTED"

    result = classify_evidence(claim, evidence, judge=judge)
    assert result.verdict is EntailmentVerdict.CONTRADICTED
    assert "judge" in result.checks


def test_11c_judge_failure_falls_back_to_rule_path():
    """Judge-Exception → judge_failed-Check, Regelpfad bleibt gültig."""
    claim, evidence = _qualitative_claim_and_evidence()

    def judge(_claim, _evidence):
        raise RuntimeError("LLM nicht erreichbar")

    result = classify_evidence(claim, evidence, judge=judge)
    assert "judge_failed" in result.checks
    # Regelpfad liefert RELATED_ONLY oder SUPPORTED für hohe Overlap — niemals
    # einen Judge-Verdict.
    assert result.verdict in {EntailmentVerdict.RELATED_ONLY, EntailmentVerdict.SUPPORTED}


def test_11d_judge_invalid_verdict_is_ignored():
    """Ein Judge-Output außerhalb der Enum wird still ignoriert (Regelpfad)."""
    claim, evidence = _qualitative_claim_and_evidence()

    def judge(_claim, _evidence):
        return "MAYBE"

    result = classify_evidence(claim, evidence, judge=judge)
    # Kein judge-Check, weil der Verdict nicht in der Enum war.
    assert "judge" not in result.checks
    assert "judge_downgraded" not in result.checks


def test_11e_build_llm_judge_uses_chat_json_with_verdict_schema():
    """build_llm_judge liefert ein Callable, das chat_json mit dem
    EntailmentJudgeVerdict-Schema aufruft und den verdict-Namen zurückgibt."""
    from app.services.llm_entailment_judge import (
        EntailmentJudgeVerdict,
        build_llm_judge,
    )

    class _StubClient:
        def __init__(self):
            self.last_schema = None
            self.last_messages = None
            self.last_context = None
            self.last_max_tokens = None
            self.last_enforce_token_floor = None

        def chat_json(
            self,
            *,
            messages,
            schema,
            schema_name,
            context,
            temperature,
            max_tokens,
            enforce_token_floor=True,
        ):
            self.last_schema = schema
            self.last_messages = messages
            self.last_context = context
            self.last_max_tokens = max_tokens
            self.last_enforce_token_floor = enforce_token_floor
            # Pydantic-Schema → chat_json liefert validiertes Dict.
            return EntailmentJudgeVerdict(verdict=EntailmentVerdict.RELATED_ONLY, reason="test").model_dump()

    stub = _StubClient()
    judge = build_llm_judge(stub)  # type: ignore[arg-type]

    verdict_name = judge("Ein Claim.", "Eine Evidence.")
    assert verdict_name == "RELATED_ONLY"
    assert stub.last_schema is EntailmentJudgeVerdict
    assert stub.last_context == "report"
    # Issue #1168: Das enge Limit ist Absicht — der Judge gibt ein Label plus
    # kurze Begründung zurück. Der Stub hatte den neuen Parameter bisher nur
    # geschluckt; fiele das Opt-out weg, ginge derselbe Call mit dem
    # 32k-Boden raus, ohne dass irgendwo etwas rot wird.
    assert stub.last_enforce_token_floor is False
    assert stub.last_max_tokens == 256
    # System-Prompt erwähnt die Verdict-Typen.
    assert stub.last_messages[0]["role"] == "system"
    assert "SUPPORTED" in stub.last_messages[0]["content"]


def test_11f_build_llm_judge_propagates_chat_json_errors():
    """chat_json-Fehler propagieren — classify_evidence fängt sie als judge_failed."""
    from app.services.llm_entailment_judge import build_llm_judge

    class _FailingClient:
        def chat_json(self, **_kwargs):
            raise RuntimeError("provider down")

    judge = build_llm_judge(_FailingClient())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="provider down"):
        judge("Claim", "Evidence")
