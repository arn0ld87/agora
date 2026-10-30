"""Tests für NER-Extractor — Sub-Slice 05.4 (strict-Schema + max_tokens=8192).

Verifiziert dass:
- `chat_json` mit `schema=NerExtractionResult` aufgerufen wird (triggert
  bei Ollama-Provider den nativen /api/chat-Pfad aus 05.1/05.3)
- max_tokens=8192 (vorher 4096) — adressiert truncierte Outputs
- _validate_and_clean bleibt funktionsidentisch (Pydantic-Validation lässt
  semantische Ontology-Validierung unangetastet)
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from app.storage.ner_extractor import (
    NerEntity,
    NerExtractionResult,
    NerRelation,
    NERExtractor,
    _preprocess_structured_text,
    detect_structural_elements,
)


@pytest.fixture()
def ner_caplog(caplog):
    ner_logger = logging.getLogger("agora.ner_extractor")
    ner_logger.addHandler(caplog.handler)
    yield caplog
    ner_logger.removeHandler(caplog.handler)


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


class TestNerExtractionResultSchema:
    """Pydantic-Schema selbst — Shape + Defaults."""

    def test_empty_payload_valid(self):
        result = NerExtractionResult.model_validate({})
        assert result.entities == []
        assert result.relations == []

    def test_complete_payload_valid(self):
        result = NerExtractionResult.model_validate(
            {
                "entities": [
                    {"name": "Anna", "type": "Person", "attributes": {"role": "CTO"}},
                ],
                "relations": [
                    {
                        "source": "Anna",
                        "target": "Müller GmbH",
                        "type": "WORKS_AT",
                        "fact": "Anna arbeitet bei Müller GmbH.",
                    },
                ],
            }
        )
        assert len(result.entities) == 1
        assert result.entities[0].name == "Anna"
        assert result.relations[0].type == "WORKS_AT"

    def test_extra_fields_ignored(self):
        """LLM darf zusätzliche Felder liefern — wir sind tolerant."""
        result = NerExtractionResult.model_validate(
            {
                "entities": [{"name": "X", "type": "Y", "attributes": {}, "confidence": 0.9}],
                "relations": [],
                "model_thought": "I think ...",
            }
        )
        assert result.entities[0].name == "X"

    def test_entity_defaults(self):
        """type+attributes haben Defaults, nur name ist Pflicht."""
        e = NerEntity.model_validate({"name": "X"})
        assert e.type == "Entity"
        assert e.attributes == {}

    def test_relation_defaults(self):
        r = NerRelation.model_validate({"source": "A", "target": "B"})
        assert r.type == "RELATED_TO"
        assert r.fact == ""

    def test_entity_name_required(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            NerEntity.model_validate({"type": "Person"})

    def test_relation_source_target_required(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            NerRelation.model_validate({"type": "WORKS_AT"})


class TestExtractPassesStrictSchema:
    """`extract()` ruft `chat_json` mit `schema=NerExtractionResult` und
    `max_tokens=8192` auf — adressiert den Truncation-Bug + erzwingt
    Schema-Enforcement bei Ollama (lokal + Cloud)."""

    def _make_extractor(self, captured: list):
        llm = MagicMock()

        def fake_chat_json(messages, temperature, max_tokens, schema=None, **kwargs):
            captured.append(
                {
                    "max_tokens": max_tokens,
                    "schema": schema,
                    "temperature": temperature,
                    "n_messages": len(messages),
                }
            )
            return {
                "entities": [{"name": "Anna", "type": "Person", "attributes": {}}],
                "relations": [
                    {
                        "source": "Anna",
                        "target": "Müller GmbH",
                        "type": "WORKS_AT",
                        "fact": "Anna arbeitet bei Müller GmbH.",
                    }
                ],
            }

        llm.chat_json.side_effect = fake_chat_json
        return NERExtractor(llm_client=llm)

    def test_extract_passes_ner_extraction_result_schema(self, simple_ontology):
        captured: list = []
        extractor = self._make_extractor(captured)

        result = extractor.extract(
            text="Anna arbeitet bei Müller GmbH.", ontology=simple_ontology
        )

        assert len(captured) == 1, "extract muss genau einen chat_json-Call machen"
        assert captured[0]["schema"] is NerExtractionResult, (
            f"schema muss NerExtractionResult sein, bekommen: {captured[0]['schema']}"
        )
        # Output wird durch _validate_and_clean gereicht — Shape bleibt
        assert "entities" in result and "relations" in result
        assert result["entities"][0]["name"] == "Anna"
        assert result["relations"][0]["type"] == "WORKS_AT"

    def test_extract_uses_8192_max_tokens(self, simple_ontology):
        """Hochziehen von 4096 auf 8192 — adressiert finish=length-Bug
        bei dichten Chunks aus dem 05.4-Live-Smoke."""
        captured: list = []
        extractor = self._make_extractor(captured)

        extractor.extract(text="Test text", ontology=simple_ontology)

        assert captured[0]["max_tokens"] == 8192, (
            f"max_tokens muss 8192 sein, bekommen: {captured[0]['max_tokens']}"
        )

    def test_extract_empty_text_no_llm_call(self, simple_ontology):
        captured: list = []
        extractor = self._make_extractor(captured)

        result = extractor.extract(text="", ontology=simple_ontology)
        assert result == {"entities": [], "relations": []}
        assert len(captured) == 0, "Leerer Text darf keinen LLM-Call triggern"

    def test_extract_retries_on_value_error(self, simple_ontology):
        """Wenn chat_json ValueError wirft → max_retries+1 Versuche."""
        llm = MagicMock()
        call_count = [0]

        def fail_then_succeed(messages, temperature, max_tokens, schema=None, **kwargs):
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("truncated JSON")
            return {"entities": [], "relations": []}

        llm.chat_json.side_effect = fail_then_succeed
        extractor = NERExtractor(llm_client=llm, max_retries=2)
        result = extractor.extract(text="some text", ontology=simple_ontology)

        assert result == {"entities": [], "relations": []}
        assert call_count[0] == 2

    def test_validate_and_clean_still_runs(self, simple_ontology):
        """Pydantic-Schema ersetzt _validate_and_clean nicht — semantische
        Ontology-Validierung + Dedup + auto-create-Entity-for-Relation laufen
        weiter."""
        llm = MagicMock()

        # Relation mit unbekannter Entity → _validate_and_clean muss die Entity
        # automatisch als type="Entity" anlegen.
        llm.chat_json.return_value = {
            "entities": [{"name": "Anna", "type": "Person", "attributes": {}}],
            "relations": [
                {
                    "source": "Anna",
                    "target": "Berlin",  # not in entities list!
                    "type": "LIVES_IN",
                    "fact": "Anna lebt in Berlin.",
                }
            ],
        }
        extractor = NERExtractor(llm_client=llm)
        result = extractor.extract(text="Anna lebt in Berlin.", ontology=simple_ontology)

        names = {e["name"] for e in result["entities"]}
        assert "Anna" in names
        assert "Berlin" in names, (
            "_validate_and_clean muss fehlende Relation-Endpunkte als Entity nachziehen"
        )
        # Berlin als auto-created → type fallback "Entity"
        berlin = next(e for e in result["entities"] if e["name"] == "Berlin")
        assert berlin["type"] == "Entity"


class TestStructuredElementsAndPreprocessing:
    """Issue #1292: Erkennung und Vorverarbeitung von Markdown-Tabellen & Listen."""

    def test_detect_table(self):
        table_text = "| Akteur | Rolle |\n|---|---|\n| Bundeskanzleramt | Koordination |"
        has_table, has_list = detect_structural_elements(table_text)
        assert has_table is True
        assert has_list is False

    def test_detect_list_bullet(self):
        list_text = "- Ministerium für Finanzen\n- Wirtschaftsrat"
        has_table, has_list = detect_structural_elements(list_text)
        assert has_table is False
        assert has_list is True

    def test_detect_list_numbered(self):
        list_text = "1. Phase eins: Beteiligung der Verbände\n2. Phase zwei: Beschluss"
        has_table, has_list = detect_structural_elements(list_text)
        assert has_table is False
        assert has_list is True

    def test_detect_neither(self):
        prose = "Dies ist ein normaler Fließtext ohne Tabellen oder Listen über DACH-Akteure."
        has_table, has_list = detect_structural_elements(prose)
        assert has_table is False
        assert has_list is False

    def test_preprocess_removes_table_separators(self):
        raw_table = (
            "| Organisation | Standort | Budget |\n"
            "|:---|:---:|---:|\n"
            "| Fraunhofer-Gesellschaft | München | 2.8 Mrd EUR |\n"
        )
        cleaned = _preprocess_structured_text(raw_table)
        assert "|:---|:---:|---:|" not in cleaned
        assert "| Organisation | Standort | Budget |" in cleaned
        assert "| Fraunhofer-Gesellschaft | München | 2.8 Mrd EUR |" in cleaned

    def test_preprocess_preserves_plain_text(self):
        text = "Ein einfacher Absatz ohne Tabellentrennlinie."
        assert _preprocess_structured_text(text) == text


class TestTableAndListPromptInjection:
    """Issue #1292: Sicherstellen, dass User-Prompt Hinweise für Tabellen & Listen erhält."""

    def test_table_hint_injected_in_user_prompt(self, simple_ontology):
        llm = MagicMock()
        llm.chat_json.return_value = {"entities": [], "relations": []}
        extractor = NERExtractor(llm_client=llm)

        table_chunk = (
            "| Stakeholder | Haltung | Region |\n"
            "|---|---|---|\n"
            "| Deutscher Bauernverband | Kritisch | Berlin |\n"
        )
        extractor.extract(text=table_chunk, ontology=simple_ontology)

        user_content = llm.chat_json.call_args[1]["messages"][1]["content"]
        assert "contains one or more tables" in user_content
        # Separator-Zeile wurde bereinigt im prompt text
        assert "|---|---|---|" not in user_content

    def test_list_hint_injected_in_user_prompt(self, simple_ontology):
        llm = MagicMock()
        llm.chat_json.return_value = {"entities": [], "relations": []}
        extractor = NERExtractor(llm_client=llm)

        list_chunk = (
            "Zentrale Stakeholder der Initiative:\n"
            "* Bundesverband der Deutschen Industrie (BDI)\n"
            "* Deutscher Gewerkschaftsbund (DGB)\n"
        )
        extractor.extract(text=list_chunk, ontology=simple_ontology)

        user_content = llm.chat_json.call_args[1]["messages"][1]["content"]
        assert "contains bullet/numbered lists" in user_content


class TestZeroEntityStructuredLogging:
    """Issue #1292: Warning-Log bei substantiellem Chunk (>100 Zeichen) mit 0 Entitäten inkl. Strukturflags."""

    def test_zero_entity_warning_with_table_and_list_flags(self, simple_ontology, ner_caplog):
        caplog = ner_caplog
        llm = MagicMock()
        llm.chat_json.return_value = {"entities": [], "relations": []}
        extractor = NERExtractor(llm_client=llm)

        table_chunk = (
            "| Organisation | Vertretung | Programm |\n"
            "|---|---|---|\n"
            "| Zürcher Handelskammer | Schweiz | Innovationsförderung 2025 |\n"
            "| Wirtschaftskammer Österreich | Wien | KMU-Digital-Initiative |\n"
        )
        assert len(table_chunk) > 100

        with caplog.at_level(logging.WARNING, logger="agora.ner_extractor"):
            extractor.extract(text=table_chunk, ontology=simple_ontology)

        warning_records = [
            r for r in caplog.records
            if r.name == "agora.ner_extractor" and r.levelno >= logging.WARNING
        ]
        assert len(warning_records) >= 1
        msg = warning_records[-1].message
        assert "has_table=True" in msg
        assert "has_list=False" in msg
        assert "chunk_len=" in msg

    def test_zero_entity_warning_on_chunk_over_100_chars(self, simple_ontology, ner_caplog):
        caplog = ner_caplog
        llm = MagicMock()
        llm.chat_json.return_value = {"entities": [], "relations": []}
        extractor = NERExtractor(llm_client=llm)

        text_120_chars = "Dies ist ein Fließtext über die deutsche Energiewirtschaft mit mehr als einhundert Zeichen Gesamtlänge für diesen Testfall."
        assert len(text_120_chars) > 100

        with caplog.at_level(logging.WARNING, logger="agora.ner_extractor"):
            extractor.extract(text=text_120_chars, ontology=simple_ontology)

        warning_records = [
            r for r in caplog.records
            if r.name == "agora.ner_extractor" and r.levelno >= logging.WARNING
        ]
        assert len(warning_records) >= 1
        msg = warning_records[-1].message
        assert "has_table=False" in msg
        assert "has_list=False" in msg
