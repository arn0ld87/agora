"""
Run-Manifest-Contract v1 (Issue #763).

Kanonischer, versionierter Vertrag für reproduzierbare Runs:
  - RunManifest: vollständiger Snapshot aller Run-Parameter
  - ReplayRequest: Override-Parameter für Varianten-Replay
  - ReplayResponse: Bestätigung eines gestarteten Replays

Regeln:
  - Keine Secrets im Manifest (API-Keys, Passwörter).
  - Prompt-Texte sind byte-genaue Snapshots zum Zeitpunkt des Runs.
  - Draft-Manifest bei Run-Start, final bei Run-Ende.
  - Legacy-Runs bekommen status="legacy" mit rekonstruierten Feldern.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

ManifestStatus = Literal["draft", "final", "legacy"]


class ManifestInputs(BaseModel):
    """Eingangsdaten-Hashes und -Referenzen."""

    model_config = _STRICT

    seed_document_hash: str
    seed_document_filename: str
    simulation_config_hash: str
    graph_id: str
    graph_version: Optional[str] = None
    embedding_version: Optional[str] = None


class ManifestVersions(BaseModel):
    """Agora- und Schema-Version zum Zeitpunkt des Runs."""

    model_config = _STRICT

    agora_version: str
    schema_version: str


class StageRoute(BaseModel):
    """Pro-Stage-Modell- und Provider-Information (ohne Secrets)."""

    model_config = _STRICT

    model: str
    provider: str
    base_url: str
    ai_route_snapshot: Optional[dict[str, Any]] = None


class ManifestRouting(BaseModel):
    """LLM-Routing-Tabelle pro Stage."""

    model_config = _STRICT

    stages: dict[str, StageRoute] = Field(default_factory=dict)


class PromptSnapshot(BaseModel):
    """Byte-genauer Prompt-Text mit Herkunftsangabe."""

    model_config = _STRICT

    content: str
    source_file: str


class ManifestPrompts(BaseModel):
    """Alle Prompt-Snapshots eines Runs."""

    model_config = _STRICT

    entries: dict[str, PromptSnapshot] = Field(default_factory=dict)


class ManifestSeeds(BaseModel):
    """Random-Seed-Informationen."""

    model_config = _STRICT

    random_seed: int
    simulation_id_seed: str


class ManifestRuntime(BaseModel):
    """Laufzeitdaten — nur im finalen Manifest."""

    model_config = _STRICT

    started_at: AwareDatetime
    completed_at: Optional[AwareDatetime] = None
    duration_seconds: Optional[int] = None
    rounds_completed: Optional[int] = None
    usage_summary: Optional[dict[str, Any]] = None
    termination_reason: Optional[str] = None


class RunManifest(BaseModel):
    """Kanonisches, maschinenlesbares Manifest eines Runs.

    Enthält alle Parameter, die zur Reproduktion nötig sind:
    Eingangsdaten, Versionen, Routing, Prompts, Seeds und Laufzeitdaten.
    """

    model_config = _STRICT

    schema_version: Literal[1] = 1
    run_id: str
    replayed_from_run_id: Optional[str] = None
    captured_at: AwareDatetime

    inputs: ManifestInputs
    versions: ManifestVersions
    routing: ManifestRouting
    prompts: ManifestPrompts
    seeds: ManifestSeeds
    runtime: Optional[ManifestRuntime] = None

    status: ManifestStatus


class ReplayOverrides(BaseModel):
    """Override-Parameter für Varianten-Replay.

    Alle Felder optional — nur gesetzte Felder werden überschrieben.
    """

    model_config = _STRICT

    seed_document_id: Optional[str] = None
    random_seed: Optional[int] = None
    ai_model_ref: Optional[dict[str, str]] = None


class ReplayRequest(BaseModel):
    """Request-Body für POST /api/runs/<run_id>/replay.

    Leere Overrides = identisches Replay.
    """

    model_config = _STRICT

    overrides: Optional[ReplayOverrides] = None


class ReplayResponse(BaseModel):
    """Response für gestartetes Replay."""

    model_config = _STRICT

    run_id: str
    status: str
