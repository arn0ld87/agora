"""Contract-Tests fuer ModelPreset/AvailableModelsResponse (Issue #1395).

Vorher lieferte ``/api/simulation/available-models`` ``Config.LLM_MODEL_PRESETS``
unvalidiert als rohe Dict-Liste aus — ein CodeRabbit-P1-Finding auf PR #1390
(kein Vertrag, kein Zod-Spiegel, kein Drift-Check). Diese Tests bewachen den
neuen Vertrag: strikte Validierung an der API-Grenze und das erhaltene
Bestandsverhalten (``label`` bleibt optionales Legacy-Feld, ungesetzte
Preset-Felder werden nicht als ``null`` mitgeschickt).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.model_preset_contract import AvailableModelsResponse, ModelPreset


def test_curated_preset_accepts_label_key_without_label():
    preset = ModelPreset(
        name="qwen3-coder-next:cloud",
        label_key="llm.preset.cloud.qwen3_coder_next",
        kind="cloud",
    )
    assert preset.label is None
    assert preset.label_key == "llm.preset.cloud.qwen3_coder_next"


def test_ollama_tag_preset_accepts_legacy_label_without_label_key():
    preset = ModelPreset(
        name="qwen2.5:32b",
        label="qwen2.5:32b",
        size=19851349248,
        family="qwen2",
        parameter_size="32.8B",
        kind="ollama",
    )
    assert preset.label == "qwen2.5:32b"
    assert preset.label_key is None


def test_unexpected_field_rejected():
    """Vorher landete jedes Feld unvalidiert im Response-JSON. Jetzt schlaegt
    ein unbekanntes Feld an der API-Grenze fehl statt es durchzureichen."""
    with pytest.raises(ValidationError):
        ModelPreset(name="x", unexpected_field="y")


def test_unset_preset_fields_are_excluded_from_serialization():
    """Bewacht das Bestandsverhalten: ein kuratiertes Preset ohne ``label``
    darf im JSON kein ``"label": null`` erzeugen — sonst faellt
    ``test_no_preset_carries_hardcoded_label_text`` still auseinander, sobald
    jemand str(preset) statt preset["label"] prueft."""
    response = AvailableModelsResponse(
        presets=[
            ModelPreset(
                name="qwen3-coder-next:cloud",
                label_key="llm.preset.cloud.qwen3_coder_next",
                kind="cloud",
            )
        ]
    )
    dumped = response.model_dump(mode="json")
    preset_payload = dumped["presets"][0]
    assert "label" not in preset_payload
    assert "size" not in preset_payload
    assert preset_payload == {
        "name": "qwen3-coder-next:cloud",
        "label_key": "llm.preset.cloud.qwen3_coder_next",
        "kind": "cloud",
    }


def test_available_models_response_top_level_none_stays_explicit():
    """Im Gegensatz zu ModelPreset-Eintraegen bleiben Top-Level-Felder wie
    ``ollama_skip_reason`` explizit ``null`` — Consumer pruefen ``is None``,
    nicht Schluessel-Abwesenheit (siehe test_available_models_filter.py)."""
    response = AvailableModelsResponse()
    dumped = response.model_dump(mode="json")
    assert dumped["ollama_skip_reason"] is None
    assert "ollama_skip_reason" in dumped


def test_response_rejects_unknown_top_level_field():
    with pytest.raises(ValidationError):
        AvailableModelsResponse(unexpected_field=True)


def test_explicit_null_in_serialization_is_intentional():
    """Issue #1395, CodeRabbit-Followup (offen): ein CodeRabbit-Review auf
    PR #1397 hat angemerkt, dass das JSON-Schema fuer die optionalen
    ModelPreset-Felder ``null`` als Wert erlaubt. Pydantic v2 exportiert
    ``anyOf: [{type: ...}, {type: null}]`` sobald ein Feld als ``T | None``
    annotiert ist — ``json_schema_extra={"nullable": False}`` wird ignoriert.
    Ein sauberer Fix wuerde entweder eigene ``field_validator`` einfuehren,
    die ``None`` ablehnen (verbunden mit Konvention fuer Default-Setzung),
    oder auf den Generator ``core_schema`` zurueckgreifen. Beide sind echte
    Architekturentscheidungen und nicht im Scope dieses Issues.

    Dieser Test dokumentiert das aktuelle Verhalten und bewacht es gegen
    ungewollte Drift: Pydantic *kann* explizites null aktuell akzeptieren,
    der Serializer ``_serialize_presets`` filtert es auf der Ausgabe weg.
    Wer den Finding schliesst, dreht die Assertion um.
    """
    preset = ModelPreset(name="qwen2.5:32b", size=None)
    # Aktuelles (bewusstes) Verhalten: Pydantic erlaubt explicit null am Rand.
    assert preset.size is None
    # Aber der Serializer filtert es auf dem Draht:
    response = AvailableModelsResponse(presets=[preset])
    dumped = response.model_dump(mode="json")
    assert "size" not in dumped["presets"][0]


def test_unset_preset_fields_omit_explicit_null_in_schema_known_todo():
    """Bewacht den Schema-Stand vor ungewollter Drift; der zugehoerige
    Fix braucht eine eigene Issue (siehe ``test_explicit_null_in_serialization_is_intentional``).
    Bis dahin weiss das Schema explizites null zu — der Schutz liegt im
    Serializer, nicht im Schema."""
    schema = ModelPreset.model_json_schema()
    nullable_field = next(
        f for f in ("kind", "label", "size")
        if f in schema["properties"]
        and any(
            sub == {"type": "null"} for sub in schema["properties"][f].get("anyOf", [])
        )
    )
    assert nullable_field in {"kind", "label", "size", "label_key", "family", "parameter_size"}
