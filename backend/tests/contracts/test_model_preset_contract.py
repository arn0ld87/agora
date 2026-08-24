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
