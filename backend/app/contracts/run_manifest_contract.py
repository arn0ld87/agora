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

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from .ai_provider_contract import AiModelRef, AiRoute, RouteSource, _LEGACY_ROUTE_OPTIONS_KEY
from .llm_routing_contract import ReasoningEffort, StageId

_STRICT = ConfigDict(extra="forbid")

ManifestStatus = Literal["draft", "final", "legacy"]


class ManifestInputs(BaseModel):
    """Eingangsdaten-Hashes und -Referenzen.

    ``seed_document_hash``/``seed_document_filename`` sind ``Optional``
    (Issue #1274 Punkt 6): ist die Quelle eines Runs wirklich nicht
    ermittelbar, ist ``None`` ehrlicher als der frühere Platzhalter
    ``"unknown"``, der wie ein echter Wert aussah.
    """

    model_config = _STRICT

    seed_document_hash: Optional[str] = None
    seed_document_filename: Optional[str] = None
    simulation_config_hash: str
    graph_id: str
    graph_version: Optional[str] = None
    embedding_version: Optional[str] = None


class ManifestVersions(BaseModel):
    """Agora- und Schema-Version zum Zeitpunkt des Runs."""

    model_config = _STRICT

    agora_version: str
    schema_version: str


class AiRouteSnapshot(BaseModel):
    """Strikter Manifest-Snapshot einer aufgelösten ``AiRoute`` (Issue #1274 Punkt 2).

    Ersetzt das vorherige offene ``dict[str, Any]``: der interne
    ``__legacy_stage_route__``-Transportkanal von :class:`AiRoute` (siehe
    ``ai_provider_contract.stage_route_from_ai_route``) ist hier bereits
    aufgelöst — ``temperature``/``max_tokens``/``reasoning_effort`` liegen auf
    oberster Ebene — und secret-tragende Provider-Optionen sind entfernt.
    ``extra="forbid"`` lehnt jedes weitere Feld ab, damit kein künftiger
    interner Transportkanal ungeprüft ins Manifest durchsickert.
    """

    model_config = _STRICT

    stage: Optional[StageId] = None
    provider_connection_id: Optional[str] = None
    model_id: Optional[str] = None
    source: RouteSource
    fallback_reason: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    reasoning_effort: ReasoningEffort = "none"
    provider_options: dict[str, Any] = Field(default_factory=dict)


def ai_route_snapshot_from_ai_route(route: AiRoute) -> AiRouteSnapshot:
    """Baut den strikten Manifest-Snapshot aus einer aufgelösten ``AiRoute``.

    Löst den ``__legacy_stage_route__``-Transportkanal auf und entfernt ihn
    zusammen mit ``secret_ref`` aus ``provider_options`` — das Manifest ist
    eine Persistenzgrenze, kein internes Transportformat, und ``secret_ref``
    ist trotz nur einer Referenz-ID kein Feld, das dort weiterreisen muss.
    """
    options = dict(route.provider_options)
    legacy = options.pop(_LEGACY_ROUTE_OPTIONS_KEY, None)
    options.pop("secret_ref", None)
    legacy = legacy if isinstance(legacy, dict) else None
    return AiRouteSnapshot(
        stage=route.stage,
        provider_connection_id=route.provider_connection_id,
        model_id=route.model_id,
        source=route.source,
        fallback_reason=route.fallback_reason,
        temperature=(legacy or {}).get("temperature"),
        max_tokens=(legacy or {}).get("max_tokens"),
        reasoning_effort=(legacy or {}).get("reasoning_effort") or "none",
        provider_options=options,
    )


def _coerce_legacy_ai_route_snapshot(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Alte ``StageRoute.ai_route_snapshot``-Dicts (offener ``AiRoute``-Dump,
    Issue #763..#901) in die strikte :class:`AiRouteSnapshot`-Form übersetzen
    (Issue #1274 Punkt 2).

    Übernimmt bekannte Felder, löst den ``__legacy_stage_route__``-Kanal auf
    und verwirft alles andere (``validated_capabilities``, ``routing_version``,
    ``resolved_at`` existieren im alten ``AiRoute``-Dump, aber nicht im neuen
    Snapshot). Idempotent für bereits neue Snapshots — die kennen keinen
    Legacy-Kanal und tragen bereits nur bekannte Felder. Fehlt ein
    Pflichtfeld (``source``) oder bleibt der normalisierte Snapshot ungültig,
    ist der Altbestand nicht rettbar — ``None`` statt eines kaputten
    Manifests.
    """
    raw_options = raw.get("provider_options")
    options = dict(raw_options) if isinstance(raw_options, dict) else {}
    legacy = options.pop(_LEGACY_ROUTE_OPTIONS_KEY, None)
    legacy = legacy if isinstance(legacy, dict) else None
    options.pop("secret_ref", None)

    normalized: dict[str, Any] = {
        "stage": raw.get("stage"),
        "provider_connection_id": raw.get("provider_connection_id"),
        "model_id": raw.get("model_id"),
        "source": raw.get("source"),
        "fallback_reason": raw.get("fallback_reason"),
        "temperature": (legacy or {}).get("temperature", raw.get("temperature")),
        "max_tokens": (legacy or {}).get("max_tokens", raw.get("max_tokens")),
        "reasoning_effort": (
            (legacy or {}).get("reasoning_effort") or raw.get("reasoning_effort") or "none"
        ),
        "provider_options": options,
    }
    try:
        AiRouteSnapshot.model_validate(normalized)
    except ValidationError:
        return None
    return normalized


class StageRoute(BaseModel):
    """Pro-Stage-Modell- und Provider-Information (ohne Secrets).

    ``base_url`` ist ``Optional`` (Issue #1274 Punkt 4): eine aus
    Run-Metadaten rekonstruierte Legacy-Route kennt oft nur Modell und
    Provider, nie die Basis-URL der Verbindung.
    """

    model_config = _STRICT

    model: str
    provider: str
    base_url: Optional[str] = None
    ai_route_snapshot: Optional[AiRouteSnapshot] = None

    @model_validator(mode="before")
    @classmethod
    def _tolerate_legacy_ai_route_snapshot(cls, data: Any) -> Any:
        """Alte ``ai_route_snapshot``-Dicts vor der Feldvalidierung normalisieren.

        Läuft dem eigentlichen Feld-Parsing von ``ai_route_snapshot`` voran,
        damit ein nicht rettbarer Altbestand als ``None`` statt als
        ``ValidationError`` durch die gesamte Manifest-Lesekette bricht.
        """
        if not isinstance(data, dict):
            return data
        raw = data.get("ai_route_snapshot")
        if raw is None or not isinstance(raw, dict):
            return data
        data = dict(data)
        data["ai_route_snapshot"] = _coerce_legacy_ai_route_snapshot(raw)
        return data


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
    """Random-Seed-Informationen.

    ``random_seed`` ist ``Optional`` (Issue #1274 Punkt 1): Agora hat kein
    echtes RNG-Seed-Konzept (kein ``np.random.seed`` o.ä.). Ein aus der
    ``simulation_id`` abgeleiteter Platzhalter-Hash suggerierte hier
    Reproduzierbarkeit, die nicht besteht — ``None`` ist die ehrliche
    Aussage "kein Seed vorhanden". ``simulation_id_seed`` ist ``Optional``
    aus demselben Grund: eine Legacy-Rekonstruktion ohne bekannte
    ``simulation_id`` darf keinen fabrizierten Platzhalter (``"legacy"``)
    tragen.
    """

    model_config = _STRICT

    random_seed: Optional[int] = None
    simulation_id_seed: Optional[str] = None


class ManifestRuntime(BaseModel):
    """Laufzeitdaten — nur im finalen Manifest."""

    model_config = _STRICT

    started_at: AwareDatetime
    completed_at: Optional[AwareDatetime] = None
    duration_seconds: Optional[int] = None
    rounds_completed: Optional[int] = None
    usage_summary: Optional[dict[str, Any]] = None
    termination_reason: Optional[str] = None


class ManifestSimulationParams(BaseModel):
    """Start-Parameter des Simulationslaufs für 1:1-Replay (Issue #1274 Punkt 3).

    Ohne diese Felder setzte ``POST /api/runs/<id>/replay`` stillschweigend
    ``platform="parallel"`` sowie Runner-Defaults für ``max_rounds`` und das
    Graph-Memory-Update statt das Original zu reproduzieren. ``Optional`` auf
    :class:`RunManifest`-Ebene, damit Manifeste vor dieser Änderung lesbar
    bleiben — ein fehlendes Feld dort bedeutet "unbekannt", nicht "Defaults
    galten".
    """

    model_config = _STRICT

    platform: str
    max_rounds: Optional[int] = None
    enable_graph_memory_update: bool
    memory_update_graph_id: Optional[str] = None


class ManifestDeviation(BaseModel):
    """Eine dokumentierte Abweichung eines Replay-Runs vom Original (Issue #1274 Punkt 3).

    Übersteuerbar ist beim Replay ausschließlich die Modell-Route — jede
    Abweichung hier beschreibt also, wo genau ein Override gegenüber dem
    Original gewirkt hat, statt Replay-Runs stillschweigend als 1:1-Kopien
    auszugeben.
    """

    model_config = _STRICT

    field: str
    original: Any = None
    replay: Any = None


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
    simulation: Optional[ManifestSimulationParams] = None
    deviations: list[ManifestDeviation] = Field(default_factory=list)

    status: ManifestStatus

    @model_validator(mode="after")
    def _final_requires_runtime(self) -> "RunManifest":
        """``status="final"`` ohne Laufzeitdaten verletzt den Lifecycle-Vertrag.

        Ein finales Manifest ist der Reproduktionsanker eines abgeschlossenen
        Runs — ohne ``runtime`` fehlen Start-, Endzeit und Terminierungsgrund.
        ``draft`` (Run läuft noch) und ``legacy`` (Alt-Run ohne erfasste
        Laufzeitdaten) bleiben bewusst ohne ``runtime`` gültig.
        """
        if self.status == "final" and self.runtime is None:
            raise ValueError('status="final" requires runtime data')
        return self


class ReplayOverrides(BaseModel):
    """Override-Parameter für Varianten-Replay.

    Alle Felder optional — nur gesetzte Felder werden überschrieben.
    """

    model_config = _STRICT

    seed_document_id: Optional[str] = None
    random_seed: Optional[int] = None
    # Kanonischer AiModelRef statt offenem dict: erzwingt beide Pflichtfelder
    # (provider_connection_id, model_id) und lehnt unbekannte Schlüssel ab.
    # Gleiche Modell-ID auf zwei Connections ist sonst nicht unterscheidbar.
    ai_model_ref: Optional[AiModelRef] = None


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
