"""
Tests für Edge-Yield in der NER-Pipeline.

Fokus: Die Filter-Stufe ``NERExtractor._validate_and_clean`` darf keine
gültigen Relations verwerfen. Getestet mit LLM-Stubs, damit kein
Ollama-Aufruf nötig ist. Echter LLM-Smoke-Test via ``@pytest.mark.llm``.

Root-Cause #216: ``_SYSTEM_PROMPT`` Rule 1 verbot Relationen außerhalb der
Ontologie — LLM emittierte bei unvollständiger Ontologie gar keine Edges.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from app.storage.ner_extractor import NERExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures" / "edge_yield"

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_ner(stub_response: Dict[str, Any]) -> NERExtractor:
    """NERExtractor mit gemocktem LLMClient."""
    mock_llm = MagicMock()
    mock_llm.chat_json.return_value = stub_response
    return NERExtractor(llm_client=mock_llm)


# ---------------------------------------------------------------------------
# Unit-Tests: _validate_and_clean — Filter-Pfad
# ---------------------------------------------------------------------------

class TestValidateAndClean:
    """Stellt sicher, dass der Filter-Pfad valide Relations nicht verwirft."""

    def test_relation_with_type_not_in_ontology_passes_through(self):
        """Relation mit unbekanntem Typ soll trotzdem im Output landen.

        Typ-Restriktion liegt im Prompt, nicht im Filter — _validate_and_clean
        muss auf Validierung per Typliste verzichten.
        """
        ner = _make_ner({
            "entities": [
                {"name": "Müller GmbH", "type": "Company", "attributes": {}},
                {"name": "Schmidt KG", "type": "Company", "attributes": {}},
            ],
            "relations": [
                {
                    "source": "Müller GmbH",
                    "target": "Schmidt KG",
                    "type": "ACQUIRED",  # nicht in Ontologie
                    "fact": "Müller GmbH übernahm Schmidt KG.",
                }
            ],
        })
        ontology = {
            "entity_types": [{"name": "Company", "description": "Ein Unternehmen"}],
            "edge_types": [
                {"name": "WORKS_FOR", "description": "Arbeitet für"}
            ],
        }
        result = ner.extract("Müller GmbH übernahm Schmidt KG.", ontology)
        assert len(result["relations"]) == 1, (
            "Relation mit unbekanntem Typ darf nicht gefiltert werden"
        )
        assert result["relations"][0]["type"] == "ACQUIRED"

    def test_relation_auto_creates_missing_entity(self):
        """Quelle oder Ziel fehlt in entities-Liste → wird nachträglich angelegt."""
        ner = _make_ner({
            "entities": [
                {"name": "Anna", "type": "Person", "attributes": {}},
            ],
            "relations": [
                {
                    "source": "Anna",
                    "target": "Boris",  # nicht in entities
                    "type": "REPORTS_TO",
                    "fact": "Anna berichtet an Boris.",
                }
            ],
        })
        result = ner.extract("Anna berichtet an Boris.", ontology={})
        assert len(result["relations"]) == 1, "Relation soll trotz fehlendem Ziel-Entity durchkommen"
        entity_names = {e["name"] for e in result["entities"]}
        assert "Boris" in entity_names, "Fehlendes Target-Entity muss automatisch angelegt werden"

    def test_multiple_relations_all_survive(self):
        """Mehrere Relations in einem Chunk sollen vollständig erhalten bleiben."""
        ner = _make_ner({
            "entities": [
                {"name": "Universität Leipzig", "type": "University", "attributes": {}},
                {"name": "Fraunhofer-Institut", "type": "ResearchInstitute", "attributes": {}},
            ],
            "relations": [
                {
                    "source": "Universität Leipzig",
                    "target": "Fraunhofer-Institut",
                    "type": "COLLABORATES_WITH",
                    "fact": "Beide arbeiten gemeinsam an einer Studie.",
                },
                {
                    "source": "Fraunhofer-Institut",
                    "target": "Universität Leipzig",
                    "type": "JOINT_RESEARCH",
                    "fact": "Fraunhofer-Institut betreibt gemeinsam mit der Uni Forschung.",
                },
            ],
        })
        result = ner.extract(
            "Die Universität Leipzig arbeitet mit dem Fraunhofer-Institut.",
            ontology={},
        )
        assert len(result["relations"]) == 2, (
            f"Alle Relations müssen erhalten bleiben; got {result['relations']}"
        )

    def test_empty_relation_source_is_dropped(self):
        """Relation ohne Quell-Entity soll still verworfen werden."""
        ner = _make_ner({
            "entities": [
                {"name": "Anna", "type": "Person", "attributes": {}},
            ],
            "relations": [
                {
                    "source": "",  # ungültig
                    "target": "Anna",
                    "type": "KNOWS",
                    "fact": "Jemand kennt Anna.",
                }
            ],
        })
        result = ner.extract("Anna.", ontology={})
        assert len(result["relations"]) == 0, "Relation ohne Source soll verworfen werden"

    def test_fact_fallback_when_empty(self):
        """Leeres fact-Feld soll durch synthetischen Fallback ersetzt werden."""
        ner = _make_ner({
            "entities": [
                {"name": "A", "type": "Entity", "attributes": {}},
                {"name": "B", "type": "Entity", "attributes": {}},
            ],
            "relations": [
                {"source": "A", "target": "B", "type": "LINKED_TO", "fact": ""},
            ],
        })
        result = ner.extract("A und B.", ontology={})
        assert result["relations"][0]["fact"] != "", "Leeres fact muss durch Fallback ersetzt werden"


# ---------------------------------------------------------------------------
# Parametrisierter Stub-Test: Minimum-Edge-Yield je Fixture
# ---------------------------------------------------------------------------

_FIXTURE_STUBS: Dict[str, Dict[str, Any]] = {
    "fixture_a.txt": {
        "entities": [
            {"name": "Müller GmbH", "type": "Company", "attributes": {}},
            {"name": "Schmidt KG", "type": "Company", "attributes": {}},
        ],
        "relations": [
            {
                "source": "Müller GmbH",
                "target": "Schmidt KG",
                "type": "ACQUIRED",
                "fact": "Müller GmbH übernahm Schmidt KG am 1. Januar 2024 für 5 Mio EUR.",
            }
        ],
    },
    "fixture_b.txt": {
        "entities": [
            {"name": "Anna", "type": "Person", "attributes": {}},
            {"name": "Boris", "type": "Person", "attributes": {}},
            {"name": "Lichtblick", "type": "Project", "attributes": {}},
        ],
        "relations": [
            {
                "source": "Anna",
                "target": "Lichtblick",
                "type": "LEADS",
                "fact": "Anna leitet das Projekt Lichtblick.",
            },
            {
                "source": "Anna",
                "target": "Boris",
                "type": "REPORTS_TO",
                "fact": "Anna berichtet an Boris.",
            },
        ],
    },
    "fixture_c.txt": {
        "entities": [
            {"name": "Universität Leipzig", "type": "University", "attributes": {}},
            {"name": "Fraunhofer-Institut", "type": "ResearchInstitute", "attributes": {}},
        ],
        "relations": [
            {
                "source": "Universität Leipzig",
                "target": "Fraunhofer-Institut",
                "type": "COLLABORATES_WITH",
                "fact": "Die Universität Leipzig arbeitet mit dem Fraunhofer-Institut an einer GraphRAG-Studie.",
            }
        ],
    },
}


@pytest.mark.parametrize("fname", ["fixture_a.txt", "fixture_b.txt", "fixture_c.txt"])
def test_minimum_edge_yield_per_fixture(fname: str) -> None:
    """Mindest-Edge-Yield: ≥ 1 Relation pro 2 Entitäten.

    Testet, dass die Pipeline valide LLM-Antworten nicht wegfiltert.
    Der Stub liefert schemavalide Antworten mit echten Triplets aus dem Fixture.
    """
    text = (FIXTURES / fname).read_text(encoding="utf-8")
    stub = _FIXTURE_STUBS[fname]
    ner = _make_ner(stub)

    result = ner.extract(text, ontology={})

    n_entities = len(result["entities"])
    n_edges = len(result["relations"])

    assert n_edges >= max(1, n_entities // 2), (
        f"{fname}: {n_entities} Entitäten, nur {n_edges} Edges — "
        f"minimum ist max(1, n_entities // 2) = {max(1, n_entities // 2)}"
    )


# ---------------------------------------------------------------------------
# LLM-Smoke-Tests (nur mit @pytest.mark.llm explizit ausführen)
# ---------------------------------------------------------------------------

@pytest.mark.llm
@pytest.mark.parametrize("fname", ["fixture_a.txt", "fixture_b.txt", "fixture_c.txt"])
def test_llm_edge_yield_smoke(fname: str) -> None:
    """Echter LLM-Aufruf — Smoke-Test für Ollama-Instanz.

    Nur ausführen mit: pytest -m llm
    Erwartung: mindestens 1 Edge pro 2 Entitäten.
    """
    text = (FIXTURES / fname).read_text(encoding="utf-8")
    ner = NERExtractor()  # echten LLM-Client

    ontology = {
        "entity_types": [
            {"name": "Company", "description": "Unternehmen"},
            {"name": "Person", "description": "Natürliche Person"},
            {"name": "University", "description": "Universität"},
            {"name": "Organization", "description": "Organisation"},
        ],
        "edge_types": [
            {"name": "ACQUIRED", "description": "Übernahme"},
            {"name": "COLLABORATES_WITH", "description": "Zusammenarbeit"},
            {"name": "REPORTS_TO", "description": "Berichtet an"},
        ],
    }

    result = ner.extract(text, ontology)
    n_entities = len(result["entities"])
    n_edges = len(result["relations"])

    assert n_edges >= max(1, n_entities // 2), (
        f"{fname}: {n_entities} Entitäten, nur {n_edges} Edges — "
        f"Prompt-Fix hat Edge-Yield nicht verbessert"
    )
