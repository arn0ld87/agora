"""Contracts fuer ``/api/simulation/available-models`` (Issue #1395).

``Config.LLM_MODEL_PRESETS`` und die Endpoint-Response
(``backend/app/api/simulation_lifecycle.py::get_available_models``) waren
eine handgepflegte Liste von Dicts ohne Validierung am API-Rand und ohne
Zod-Spiegel — ein CodeRabbit-P1-Finding auf PR #1390 (Issue #1290), das die
Contracts-first-Regel aus AGENTS.md verletzt.

``ModelPreset`` deckt zwei Herkuenfte ab, die beide in ``presets[]`` bzw.
``ollama[]`` landen:

* kuratiert (``Config.LLM_MODEL_PRESETS``): ``name``, ``label_key``, ``kind``.
* lokal installierte Ollama-Tags (``/api/tags``-Probe): ``name``,
  ``label`` (= Modellname), ``size``, ``family``, ``parameter_size``,
  ``kind="ollama"``.

``label`` bleibt bewusst ein optionales Legacy-Feld: Ollama-Tag-Eintraege
setzen es weiterhin auf den rohen Modellnamen, und die Aufloesungskette in
``frontend/src/i18n/modelPresetLabel.ts::resolvePresetLabel`` faellt fuer
aeltere Backends im Mischbetrieb noch darauf zurueck. Kuratierte Presets
duerfen es nicht setzen — das bewacht
``backend/tests/api/test_model_preset_label_keys.py::test_no_preset_carries_hardcoded_label_text``.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_serializer

_STRICT = ConfigDict(extra="forbid")

# Bewusst ``str`` statt ``Literal`` (wie ``SystemStatusOllama.skipped_provider``
# in ``system_status_contract.py``): ein neues Preset-Kind (weiterer
# Cloud-Provider in ``Config.LLM_MODEL_PRESETS``) darf den Vertrag nicht
# brechen, bevor Frontend/i18n-Katalog es kennen.
ModelPresetKind = str


class ModelPreset(BaseModel):
    """Ein Eintrag aus ``presets[]`` bzw. ``ollama[]``."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    kind: ModelPresetKind | None = None
    label: str | None = None
    label_key: str | None = None
    size: int | None = None
    family: str | None = None
    parameter_size: str | None = None


class AvailableModelsResponse(BaseModel):
    """Response von ``GET /api/simulation/available-models``."""

    model_config = _STRICT

    ollama: list[ModelPreset] = Field(default_factory=list)
    presets: list[ModelPreset] = Field(default_factory=list)
    current_default: str = ""
    default_provider: str = "unknown"
    ollama_base_url: str | None = None
    ollama_reachable: bool = False
    ollama_error: str | None = None
    ollama_skipped: bool = False
    ollama_skipped_provider: str | None = None
    ollama_skip_reason: str | None = None
    neo4j_reachable: bool = False
    neo4j_error: str | None = None
    neo4j_uri: str | None = None
    default_language: str = "de"
    agent_tools_enabled: bool = False
    max_tool_calls_per_action: int = 2

    # Kuratierte Presets setzen nur name/label_key/kind, Ollama-Tag-Eintraege
    # zusaetzlich label/size/family/parameter_size. Ohne diesen Serializer
    # wuerde jedes ModelPreset ALLE Felder inkl. nicht gesetzter als
    # ``null`` mitschicken — z. B. ``"label": null`` fuer ein kuratiertes
    # Preset, obwohl der Vertrag ``label`` bewusst nur fuer Legacy-Faelle
    # vorsieht (siehe Modul-Docstring). Bewacht von
    # tests/api/test_model_preset_label_keys.py::test_available_models_endpoint_emits_label_keys.
    @field_serializer("ollama", "presets")
    def _serialize_presets(
        self, presets: list[ModelPreset], _info: object
    ) -> list[dict[str, object]]:
        return [p.model_dump(mode="json", exclude_none=True) for p in presets]
