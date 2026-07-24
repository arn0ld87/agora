"""Tests for ontology generation post-processing."""

from app.config import Config
from app.services.ontology_generator import OntologyGenerator, OntologyDefinition


class _DummyLLMClient:
    """Stub für Tests, die nur die LLM-freien Post-Processing-Methoden
    (`_validate_and_process`, `_build_user_message`) ausüben. Vermeidet
    `LLM_API_KEY`-Auflösung in Test-Setups ohne lebendes Provider-Backend.
    """

    def chat(self, *args, **kwargs):  # pragma: no cover - nicht aufgerufen
        raise AssertionError("Dummy-LLM-Client darf in diesen Tests nicht aufgerufen werden")

    def chat_json(self, *args, **kwargs):  # pragma: no cover - nicht aufgerufen
        raise AssertionError("Dummy-LLM-Client darf in diesen Tests nicht aufgerufen werden")


def _entity(name: str):
    return {
        "name": name,
        "description": f"{name} description",
        "attributes": [],
        "examples": [],
    }


def _edge(index: int):
    return {
        "name": f"REL_{index}",
        "description": "relationship",
        "source_targets": [],
        "attributes": [],
    }


def test_validate_process_uses_configured_entity_cap(monkeypatch):
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_ENTITY_TYPES", 12)
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_EDGE_TYPES", 12)
    result = {
        "entity_types": [_entity(f"Type{i}") for i in range(14)],
        "edge_types": [_edge(i) for i in range(3)],
    }

    processed = OntologyGenerator(llm_client=_DummyLLMClient())._validate_and_process(result)

    assert len(processed["entity_types"]) == 12
    assert processed["entity_types"][-2]["name"] == "Person"
    assert processed["entity_types"][-1]["name"] == "Organization"


def test_validate_process_preserves_existing_fallbacks_when_trimming(monkeypatch):
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_ENTITY_TYPES", 6)
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_EDGE_TYPES", 12)
    result = {
        "entity_types": (
            [_entity(f"Type{i}") for i in range(8)]
            + [_entity("Person"), _entity("Organization")]
        ),
        "edge_types": [],
    }

    processed = OntologyGenerator(llm_client=_DummyLLMClient())._validate_and_process(result)

    names = [entity["name"] for entity in processed["entity_types"]]
    assert len(names) == 6
    assert names[-2:] == ["Person", "Organization"]


def test_validate_process_uses_configured_edge_cap(monkeypatch):
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_ENTITY_TYPES", 16)
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_EDGE_TYPES", 4)
    result = {
        "entity_types": [_entity("Person"), _entity("Organization")],
        "edge_types": [_edge(i) for i in range(8)],
    }

    processed = OntologyGenerator(llm_client=_DummyLLMClient())._validate_and_process(result)

    assert len(processed["edge_types"]) == 4


def test_build_user_message_uses_configured_entity_range(monkeypatch):
    monkeypatch.setattr(Config, "ONTOLOGY_MIN_ENTITY_TYPES", 7)
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_ENTITY_TYPES", 13)

    message = OntologyGenerator(llm_client=_DummyLLMClient())._build_user_message(["text"], "simulate", None)

    assert "between 7 and 13 entity types" in message


class _CapturingLLMClient:
    """Stub, der chat_json-Argumente für Regression-Tests einfängt.

    Vermeidet LLM_API_KEY-Auflösung und gibt ein valides Ontology-JSON zurück,
    damit ``generate()`` durchlaufen kann, während wir die übergebenen kwargs
    inspizieren (schema, schema_name, force_no_thinking).
    """

    def __init__(self):
        self.captured_kwargs = None

    def chat(self, *args, **kwargs):  # pragma: no cover - nicht aufgerufen
        raise AssertionError("chat() darf in diesen Tests nicht aufgerufen werden")

    def chat_json(self, messages, temperature=0.3, max_tokens=4096,
                  schema=None, schema_name="structured_response",
                  context="chat_json", force_no_thinking=False, **kwargs):
        """
                  Erfasst die übergebenen Chat-Parameter und liefert eine feste Ontologie-Struktur zurück.
                  
                  Parameters:
                      messages: Chat-Nachrichten.
                      schema: Optionales Schema für die strukturierte Antwort.
                      schema_name: Name des Antwortschemas.
                      context: Kontext der Anfrage.
                      force_no_thinking: Steuert, ob interne Denkprozesse deaktiviert werden.
                  
                  Returns:
                      Eine Ontologie-Struktur mit den Entitätstypen „Person“ und „Organization“.
                  """
                  self.captured_kwargs = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "schema": schema,
            "schema_name": schema_name,
            "context": context,
            "force_no_thinking": force_no_thinking,
        }
        return {
            "entity_types": [
                {"name": "Person", "description": "fallback",
                 "attributes": [], "examples": []},
                {"name": "Organization", "description": "fallback",
                 "attributes": [], "examples": []},
            ],
            "edge_types": [],
            "analysis_summary": "stub",
        }


def test_generate_passes_ontology_definition_schema():
    """Regression: generate() muss chat_json mit schema=OntologyDefinition aufrufen.

    MiniMax-M3 mischt ohne strict-``json_schema``-Mode in ~20 % der Läufe
    erklärenden Prosa-Text ins JSON ein (finish=stop, Budget nicht voll) →
    Parse-Fehler. Übergabe des Pydantic-Schemas erzwingt strukturierte JSON-
    Ausgabe beim Provider.
    """
    stub = _CapturingLLMClient()
    generator = OntologyGenerator(llm_client=stub)
    generator.generate(document_texts=["some text"], simulation_requirement="e2e")

    assert stub.captured_kwargs is not None, "chat_json wurde nicht aufgerufen"
    assert stub.captured_kwargs["schema"] is OntologyDefinition, (
        "generate() muss schema=OntologyDefinition übergeben, damit der Provider "
        "im strict json_schema-Mode antwortet"
    )
    assert stub.captured_kwargs["schema_name"] == "ontology_definition"


def test_generate_passes_force_no_thinking_true():
    """Regression: generate() muss force_no_thinking=True setzen.

    Verhindert, dass Reasoning-Token das max_tokens-Budget belegen und der
    Content-Teil mid-JSON abgeschnitten wird. Analog zu
    report_agent/planning.py:plan_outline().
    """
    stub = _CapturingLLMClient()
    generator = OntologyGenerator(llm_client=stub)
    generator.generate(document_texts=["some text"], simulation_requirement="e2e")

    assert stub.captured_kwargs is not None, "chat_json wurde nicht aufgerufen"
    assert stub.captured_kwargs["force_no_thinking"] is True, (
        "generate() muss force_no_thinking=True übergeben, damit Reasoning-Output "
        "deaktiviert wird und das Token-Budget voll für den Content zur Verfügung steht"
    )
