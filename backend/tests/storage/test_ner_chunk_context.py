"""Tests für Chunk-Kontext-Builder und NER-Pronomen-Filter (Issue #1470, Slice 4.4).

Verifiziert:
- build_chunk_contexts: Kontext enthält letzte Überschrift und Vorlauf
- build_chunk_contexts: Chunk-Texte bleiben unverändert
- build_chunk_contexts: Rückgabe-Länge gleich Eingabe-Länge
- NERExtractor._validate_and_clean: Pronomen-Entitäten werden verworfen
- NERExtractor.extract: Prompt enthält den Kontext-Block getrennt vom Chunk
- NERExtractor.extract: Warnung bei 0 Entitäten in substantiellem Chunk
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from app.storage.ner_chunk_context import build_chunk_contexts
from app.storage.ner_extractor import NERExtractor, _PRONOUN_BLOCKLIST


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def simple_ontology():
    return {
        "entity_types": [
            {"name": "Person", "description": "Eine Person"},
            {"name": "Organization", "description": "Eine Firma oder Institution"},
        ],
        "relation_types": [
            {"name": "WORKS_AT", "description": "Person arbeitet bei Org"},
        ],
    }


def _extractor_with_capture(captured: list, return_entities=None, return_relations=None):
    """Hilfsfunktion: NERExtractor mit gemocktem LLM, der Aufrufe protokolliert."""
    if return_entities is None:
        return_entities = []
    if return_relations is None:
        return_relations = []

    llm = MagicMock()

    def fake_chat_json(messages, temperature, max_tokens, schema=None, **kwargs):
        captured.append({"messages": messages, "schema": schema})
        return {"entities": return_entities, "relations": return_relations}

    llm.chat_json.side_effect = fake_chat_json
    return NERExtractor(llm_client=llm)


# ---------------------------------------------------------------------------
# Tests: build_chunk_contexts
# ---------------------------------------------------------------------------


def test_kontext_endet_an_der_document_id_grenze():
    """Codex-Review PR #1620 (P1): kein Vorlauf aus Dokument A im ersten
    Chunk von Dokument B — sonst löst die NER ein Pronomen gegen eine
    fremde Entität auf und schreibt die Relation mit Bs Provenance."""
    chunks = [
        "# Klinikum Nord\nDie Geschäftsführerin Dr. Weber plant den Start.",
        "Sie verantwortet das Budget.",
        "Er lehnt den Zeitplan ab.",
        "Der Betriebsrat fordert eine Vereinbarung.",
    ]
    contexts = build_chunk_contexts(chunks, ["doc_a", "doc_a", "doc_b", "doc_b"])
    assert "Dr. Weber" in contexts[1]
    assert contexts[2] == ""
    assert "Weber" not in contexts[3] and "Klinikum Nord" not in contexts[3]
    assert "Er lehnt den Zeitplan ab." in contexts[3]


def test_kontext_endet_am_dokument_marker_ohne_manifest():
    """Altprojekte und Neustart-Pfad: der ``=== name ===``-Marker am
    Chunk-Anfang ist die Dokumentgrenze."""
    chunks = [
        "=== a.md ===\nDie Geschäftsführerin Dr. Weber plant den Start.",
        "Sie verantwortet das Budget.",
        "=== b.md ===\nEr lehnt den Zeitplan ab.",
        "Der Betriebsrat fordert eine Vereinbarung.",
    ]
    contexts = build_chunk_contexts(chunks)
    assert contexts[2] == ""
    assert contexts[3].startswith("=== b.md ===")
    assert "a.md" not in contexts[3] and "Budget" not in contexts[3]


def test_document_ids_mit_falscher_laenge_werden_abgelehnt():
    with pytest.raises(ValueError):
        build_chunk_contexts(["a", "b"], ["doc_a"])


class TestBuildChunkContexts:
    def test_first_chunk_has_empty_context(self):
        chunks = ["# Einleitung\nErster Text.", "Zweiter Text."]
        contexts = build_chunk_contexts(chunks)
        assert contexts[0] == ""

    def test_second_chunk_contains_previous_heading(self):
        chunks = ["# Einleitung\nErster Text.", "Zweiter Text."]
        contexts = build_chunk_contexts(chunks)
        assert "# Einleitung" in contexts[1]

    def test_second_chunk_contains_tail_of_first(self):
        chunks = ["Langer erster Text mit Inhalt.", "Zweiter Text."]
        contexts = build_chunk_contexts(chunks)
        assert "Langer erster Text mit Inhalt." in contexts[1]

    def test_doc_marker_is_picked_up(self):
        chunks = ["=== Projektbeschreibung ===\nEin Projekt.", "Nächster Chunk."]
        contexts = build_chunk_contexts(chunks)
        assert "=== Projektbeschreibung ===" in contexts[1]

    def test_heading_propagates_across_multiple_chunks(self):
        """Eine Überschrift in Chunk 0 landet auch im Kontext von Chunk 2."""
        chunks = [
            "# Abschnitt A\nText A.",
            "Text B ohne eigene Überschrift.",
            "Text C.",
        ]
        contexts = build_chunk_contexts(chunks)
        assert "# Abschnitt A" in contexts[2]

    def test_later_heading_overrides_earlier(self):
        """Wenn Chunk 1 eine neue Überschrift enthält, wird sie für Chunk 2 aktiv."""
        chunks = [
            "# Erster Abschnitt\nText A.",
            "# Zweiter Abschnitt\nText B.",
            "Text C.",
        ]
        contexts = build_chunk_contexts(chunks)
        assert "# Zweiter Abschnitt" in contexts[2]
        assert "# Erster Abschnitt" not in contexts[2]

    def test_tail_limited_to_300_chars(self):
        long_chunk = "X" * 500
        chunks = [long_chunk, "Zweiter."]
        contexts = build_chunk_contexts(chunks)
        # Kontext enthält höchstens 300 Zeichen aus long_chunk
        # (plus ggf. eine Überschrift, hier keine → nur der Tail)
        assert len(contexts[1]) <= 310  # leichte Toleranz für Whitespace

    def test_chunk_texts_unchanged(self):
        """Die Chunk-Texte selbst dürfen durch build_chunk_contexts nie verändert werden."""
        original = ["# H\nChunk A.", "Chunk B.", "Chunk C."]
        chunks = list(original)
        _ = build_chunk_contexts(chunks)
        assert chunks == original

    def test_returns_same_length_as_input(self):
        chunks = ["A", "B", "C", "D"]
        contexts = build_chunk_contexts(chunks)
        assert len(contexts) == len(chunks)

    def test_empty_list_returns_empty_list(self):
        assert build_chunk_contexts([]) == []

    def test_single_chunk_returns_one_empty_context(self):
        contexts = build_chunk_contexts(["Einziger Chunk."])
        assert contexts == [""]

    def test_context_does_not_alter_chunks_list_in_place(self):
        chunks = ["# X\nA", "B"]
        before = [c for c in chunks]
        build_chunk_contexts(chunks)
        assert chunks == before


# ---------------------------------------------------------------------------
# Tests: NERExtractor — Pronomen-Filter
# ---------------------------------------------------------------------------

class TestPronounBlocklist:
    def test_blocklist_contains_german_pronouns(self):
        for pronoun in ("er", "sie", "es", "wir", "man", "dieser"):
            assert pronoun in _PRONOUN_BLOCKLIST, f"{pronoun!r} fehlt in _PRONOUN_BLOCKLIST"

    def test_blocklist_contains_english_pronouns(self):
        for pronoun in ("he", "she", "they", "it", "we"):
            assert pronoun in _PRONOUN_BLOCKLIST, f"{pronoun!r} fehlt in _PRONOUN_BLOCKLIST"

    def test_pronoun_entity_is_discarded(self, simple_ontology):
        captured: list = []
        extractor = _extractor_with_capture(
            captured,
            return_entities=[
                {"name": "er", "type": "Person", "attributes": {}},
                {"name": "Anna", "type": "Person", "attributes": {}},
            ],
        )
        result = extractor.extract("Er sprach mit Anna.", simple_ontology)
        names = {e["name"] for e in result["entities"]}
        assert "er" not in names, "Pronomen 'er' darf nicht als Entität erscheinen"
        assert "Anna" in names

    def test_english_pronoun_entity_is_discarded(self, simple_ontology):
        captured: list = []
        extractor = _extractor_with_capture(
            captured,
            return_entities=[
                {"name": "she", "type": "Person", "attributes": {}},
                {"name": "Müller GmbH", "type": "Organization", "attributes": {}},
            ],
        )
        result = extractor.extract("She works at Müller GmbH.", simple_ontology)
        names = {e["name"] for e in result["entities"]}
        assert "she" not in names
        assert "Müller GmbH" in names

    def test_non_pronoun_entity_is_kept(self, simple_ontology):
        captured: list = []
        extractor = _extractor_with_capture(
            captured,
            return_entities=[
                {"name": "Bundesagentur für Arbeit", "type": "Organization", "attributes": {}},
            ],
        )
        result = extractor.extract("Die Behörde …", simple_ontology)
        names = {e["name"] for e in result["entities"]}
        assert "Bundesagentur für Arbeit" in names


# ---------------------------------------------------------------------------
# Tests: NERExtractor — Kontext-Block im Prompt
# ---------------------------------------------------------------------------

class TestContextInPrompt:
    def test_context_block_appears_in_system_message(self, simple_ontology):
        captured: list = []
        extractor = _extractor_with_capture(captured)
        extractor.extract(
            text="Text des Chunks.",
            ontology=simple_ontology,
            context="# Vorherige Überschrift\nEnde des Vorgängers.",
        )
        assert len(captured) == 1
        system_content = captured[0]["messages"][0]["content"]
        assert "# Vorherige Überschrift" in system_content
        assert "Kontext" in system_content  # Marker-Zeile vorhanden
        assert "Ende des Vorgängers" in system_content

    def test_chunk_text_in_user_message(self, simple_ontology):
        captured: list = []
        extractor = _extractor_with_capture(captured)
        extractor.extract(
            text="Chunk-Inhalt hier.",
            ontology=simple_ontology,
            context="Vorgänger-Info.",
        )
        user_content = captured[0]["messages"][1]["content"]
        assert "Chunk-Inhalt hier." in user_content

    def test_no_context_block_when_context_empty(self, simple_ontology):
        captured: list = []
        extractor = _extractor_with_capture(captured)
        extractor.extract(text="Ein Text.", ontology=simple_ontology, context="")
        system_content = captured[0]["messages"][0]["content"]
        # Kein leerer Kontext-Block darf im Prompt erscheinen
        assert "[Kontext" not in system_content

    def test_context_block_separated_from_chunk(self, simple_ontology):
        """Kontext-Block und Chunk-Text landen in verschiedenen Nachrichten."""
        captured: list = []
        extractor = _extractor_with_capture(captured)
        extractor.extract(
            text="Chunk-Text.",
            ontology=simple_ontology,
            context="Kontext-Vorlauf.",
        )
        system_content = captured[0]["messages"][0]["content"]
        user_content = captured[0]["messages"][1]["content"]
        assert "Kontext-Vorlauf" in system_content
        assert "Chunk-Text." in user_content
        # Kontext darf nicht in der User-Message stehen
        assert "Kontext-Vorlauf" not in user_content


# ---------------------------------------------------------------------------
# Tests: NERExtractor — 0-Entitäten-Warnung
# ---------------------------------------------------------------------------

@pytest.fixture
def ner_caplog(caplog):
    """Der Logger-Baum "agora" propagiert nicht zum Root — caplog muss am
    Logger selbst hängen, sonst bliebe die Prüfung wirkungslos."""
    ner_logger = logging.getLogger("agora.ner_extractor")
    ner_logger.addHandler(caplog.handler)
    yield caplog
    ner_logger.removeHandler(caplog.handler)


class TestZeroEntityWarning:
    def test_warning_logged_for_long_chunk_with_no_entities(
        self, simple_ontology, ner_caplog
    ):
        caplog = ner_caplog
        """Chunk über 200 Zeichen ohne Entitäten → strukturierte Warnung."""
        long_text = "A" * 250
        captured: list = []
        extractor = _extractor_with_capture(captured, return_entities=[], return_relations=[])

        with caplog.at_level(logging.WARNING, logger="agora.ner_extractor"):
            result = extractor.extract(text=long_text, ontology=simple_ontology)

        assert result["entities"] == []
        assert any("0" in r.message or "kein" in r.message.lower() for r in caplog.records), (
            "Es wurde keine Warnung über fehlende Entitäten geloggt"
        )

    def test_no_warning_for_short_chunk_with_no_entities(
        self, simple_ontology, ner_caplog
    ):
        caplog = ner_caplog
        """Kurzer Chunk (≤ 200 Zeichen) darf still 0 Entitäten zurückgeben."""
        short_text = "Kurz."
        captured: list = []
        extractor = _extractor_with_capture(captured, return_entities=[], return_relations=[])

        with caplog.at_level(logging.WARNING, logger="agora.ner_extractor"):
            extractor.extract(text=short_text, ontology=simple_ontology)

        # Keine Warnung erwartet (nur NER-eigene Warnungen prüfen)
        ner_warnings = [
            r for r in caplog.records
            if r.name == "agora.ner_extractor" and r.levelno >= logging.WARNING
        ]
        assert not ner_warnings


def test_relation_mit_pronomen_legt_das_pronomen_nicht_wieder_an(simple_ontology):
    """Lead-Review: das Nachtragen fehlender Endpunkte umging die Pronomen-Sperre."""
    captured: list = []
    extractor = _extractor_with_capture(
        captured,
        return_entities=[{"name": "Projekt AURORA", "type": "Project"}],
        return_relations=[
            {"source": "er", "target": "Projekt AURORA", "type": "LEITET", "fact": "er leitet"},
            {"source": "Dr. Vogt", "target": "Projekt AURORA", "type": "LEITET", "fact": "Vogt leitet"},
        ],
    )
    result = extractor.extract(text="Er leitet das Projekt AURORA.", ontology=simple_ontology)

    names = {e["name"] for e in result["entities"]}
    assert "er" not in {n.lower() for n in names}
    assert [r["source"] for r in result["relations"]] == ["Dr. Vogt"]
