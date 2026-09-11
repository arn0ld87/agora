"""Request contracts and input/routing parsing for simulation preparation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, ConfigDict, ValidationError

from ..contracts import PersonaQuotaPlan
from ..contracts.ai_provider_contract import AiModelRef
from ..contracts.run_budget_contract import RunBudgetConfig
from ..models.project import ProjectManager
from ..services.llm_runtime import parse_runtime_llm_config
from ..services.report_agent import MIN_SIMULATION_AGENTS
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import json_error
from ..utils.validation import validate_simulation_id
from .simulation_common import logger

if TYPE_CHECKING:
    from ..services.llm_runtime import RuntimeLlmConfig

def _coerce_optional_str(value: Any) -> "str | None":
    """Erzwingt ``str | None`` aus beliebigem JSON-Wert ohne ``AttributeError``.

    ``value.strip()`` auf einer Nicht-Zahl (z.B. ``"language": 5``) würde als
    HTTP 500 enden; Client-Fehler im Wire-Format müssen aber als Fehlen
    behandelt werden wie ein ungültiges ``max_agents`` — konsistente
    None-Semantik statt Typ-Crash (CodeRabbit-Finding PR #1497).
    """
    if not isinstance(value, str):
        return None
    return value

def _parse_quota_plan(data: dict) -> Optional[PersonaQuotaPlan]:
    """Parse ``quota_plan`` aus dem POST-Body in ein ``PersonaQuotaPlan``.

    Sub-Slice 20a — API-Boundary für Persona-Quoten. Backwards-Compat:
    fehlendes oder ``None``-Feld → ``None`` (Service verhält sich wie
    bisher). Leerer Dict ``{}`` zählt ebenfalls als „nicht gesetzt“, weil
    ein leerer Plan keinerlei Aussagekraft hat und sonst eine
    ``ValidationError`` für „targets darf nicht leer sein“ werfen würde —
    Frontend kann den Eintrag dann mit `{}` defaulten ohne 400.

    Bei strukturell vorhandenem, aber inkonsistentem Plan
    (``total != sum(targets)``, ``targets`` mit ``count<1``,
    nicht-Dict-Payload) wird die ``pydantic.ValidationError`` propagiert
    und vom Caller in eine HTTP-400-Antwort übersetzt.
    """
    raw: Any = data.get("quota_plan")
    if raw is None:
        return None
    if isinstance(raw, dict) and not raw:
        return None
    return PersonaQuotaPlan.model_validate(raw)

def _resolve_max_agents_with_floor(raw_value: object) -> int | None:
    """Parse optional ``max_agents`` and enforce the simulation-pool floor.

    Der Floor steht bewusst auf ``MIN_SIMULATION_AGENTS`` (10), nicht auf
    ``MIN_PERSONA_TABLE_ROWS`` (50). Das erlaubt Schnell-Tests mit Mini-Seeds
    (Smoke #6 2026-05-15); die Report-Generation skaliert den Persona-Pool im
    Nachgang via Round-Robin auf ``MIN_PERSONA_TABLE_ROWS`` hoch
    (``_apply_persona_floor_to_entities`` in prepare_service.py).
    """
    if raw_value is None or raw_value == "" or raw_value == 0:
        return None
    if not isinstance(raw_value, (str, int, float)):
        return None
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    if parsed < MIN_SIMULATION_AGENTS:
        logger.info(
            "Applying simulation-agents floor for max_agents: requested=%s floor=%s",
            parsed,
            MIN_SIMULATION_AGENTS,
        )
        return MIN_SIMULATION_AGENTS
    return parsed

class PrepareRejected(Exception):
    """Bricht eine Prepare-Phase mit einer fertig gebauten Fehler-Response ab.

    Die Phasen unterhalb von :func:`prepare_simulation` sind einzeln testbar
    und müssen ihren Ablehnungsfall deshalb selbst formulieren können. Sie
    tragen die bereits gebaute ``json_error``-Response, damit Status-Code,
    Fehlercode und Meldung wortgleich das bleiben, was der monolithische
    Handler vorher zurückgegeben hat (#1080).
    """

    def __init__(self, response: Any, run_failure_message: "str | None" = None) -> None:
        super().__init__("simulation prepare rejected")
        self.response = response
        if run_failure_message is not None:
            # Sprechende failed-Meldung für einen bereits registrierten Run —
            # ausgewertet vom RunLifecycle (#841: die detaillierte Meldung
            # landet zuletzt auf dem Run, nach fail_task()).
            self.run_failure_message = run_failure_message

class PrepareRequest(BaseModel):
    """Volldefinierte Pydantic-Contracts für ``POST /api/simulation/prepare``.

    Konsistente Validierungs-Semantik vermeidet inkonsonante Fehler-Routing:
    - Feld-Level-Validierung statt .strip() auf potentiell nicht-string Werten
    - Einheitliche HTTP-400-Antworten bei Validierungsfehlern
    - Explizite Typkonversion durch Pydantic vermeidet None/Fehler-Unsicherheit
    """

    simulation_id: str
    ai_model_ref: "AiModelRef | None" = None
    budget_config: "RunBudgetConfig | None" = None
    force_regenerate: bool = False

    model_config = ConfigDict(str_strip_whitespace=True, str_to_lower=False)

@dataclass(frozen=True)
class PrepareRouting:
    """Ergebnis der Routing-Auflösung (Profil, Modell-Override, Runtime)."""

    llm_model_override: "str | None"
    llm_runtime: "RuntimeLlmConfig"
    routed_profile_id: "str | None"
    client_requested_override: bool

@dataclass(frozen=True)
class PrepareInputs:
    """Fachliche Eingaben des Vorbereitungslaufs jenseits des Routings."""

    simulation_requirement: str
    document_text: str
    entity_types: Any
    use_llm_for_profiles: Any
    parallel_profile_count: Any
    max_agents: "int | None"
    quota_plan: Optional[PersonaQuotaPlan]
    agent_language_override: "str | None"

def _parse_prepare_identity(data: "dict[str, Any]") -> "tuple[str, AiModelRef | None]":
    """Phase 1a — ``simulation_id`` und optionale ``ai_model_ref`` validieren.

    Eine explizite Ref ist die alleinige Routing-Quelle und darf deshalb nicht
    mit Legacy-Feldern kombiniert werden (Issue #817).
    """
    simulation_id = data.get('simulation_id')
    if not simulation_id:
        raise PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message="Please provide simulation_id",
            )
        )

    if not validate_simulation_id(simulation_id):
        raise PrepareRejected(
            json_error(
                ApiErrorCode.INVALID_ID,
                status=400,
                message="Invalid simulation_id format",
            )
        )

    raw_ai_model_ref = data.get("ai_model_ref")
    if raw_ai_model_ref is None:
        return simulation_id, None

    try:
        ai_model_ref = AiModelRef.model_validate(raw_ai_model_ref)
    except ValidationError:
        raise PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message="ai_model_ref ist ungültig",
            )
        ) from None

    conflicting = [
        key
        for key in ("llm_model", "llm_profile_id", "llm_provider", "llm_runtime")
        if data.get(key)
    ]
    if conflicting:
        raise PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=(
                    f"ai_model_ref darf nicht mit {', '.join(conflicting)} "
                    "kombiniert werden"
                ),
            )
        )
    return simulation_id, ai_model_ref

def _parse_prepare_budget(data: "dict[str, Any]") -> "RunBudgetConfig | None":
    """Phase 1b — Run-Budget (Issue #764): optionale Limits für den Prepare-Run."""
    raw_budget = data.get('budget')
    if raw_budget is None:
        return None

    try:
        return RunBudgetConfig.model_validate(raw_budget)
    except ValidationError:
        raise PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message="budget ist ungültig",
            )
        ) from None

def _load_prepare_project(state):
    """Projekt einmalig laden — für Profil-Fallback, Anforderung und Metadaten.

    (Gemini-MEDIUM auf PR #528: vorher wurde derselbe Datensatz zwei Mal aus
    dem ProjectManager geholt.)
    """
    project = ProjectManager.get_project(state.project_id)
    if not project:
        raise PrepareRejected(
            json_error(
                ApiErrorCode.NOT_FOUND,
                status=404,
                message=f"Project does not exist: {state.project_id}",
            )
        )
    return project

@dataclass(frozen=True)
class ClientChoice:
    """Was der Client an Routing *explizit* gewählt hat.

    Wird vor der Profil-Expansion festgehalten: ``expand_profile_in_data``
    schreibt einen `llm_provider`-Block aus dem Profil (Provider/Key/Base-URL)
    und würde `llm_runtime.enabled` sonst ununterscheidbar von einem echten
    Client-Provider-Override machen.
    """

    data_profile: "str | None"
    project_profile: "str | None"
    explicit_model_override: bool
    explicit_runtime_request: bool

    @property
    def explicit_profile_override(self) -> bool:
        return bool(self.data_profile and self.data_profile != self.project_profile)

def _read_client_choice(data: "dict[str, Any]", project) -> ClientChoice:
    """Explizite Client-Wahl aus Body und Projekt lesen.

    `default` ist die UI-Platzhalterwahl (`useEnvForm.effectiveModel()` liefert
    dafür `null`) und zählt deshalb nicht als explizite Modellwahl.
    """
    data_profile = (_coerce_optional_str(data.get('llm_profile_id')) or '').strip() or None
    project_profile = (_coerce_optional_str(getattr(project, 'llm_profile_id', None)) or '').strip() or None
    data_model = (_coerce_optional_str(data.get('llm_model')) or '').strip() or None
    return ClientChoice(
        data_profile=data_profile,
        project_profile=project_profile,
        explicit_model_override=bool(data_model and data_model.lower() != 'default'),
        explicit_runtime_request=bool(data.get('llm_provider')),
    )

def _resolve_prepare_routing(
    data: "dict[str, Any]", project, ai_model_ref: "AiModelRef | None"
) -> PrepareRouting:
    """Phase 2 — Profil-, Modell- und Runtime-Routing auflösen.

    Profil-Routing (Issue #888). `llm_profile_id` ist eine Routing-Anweisung,
    kein Fallback-Unterdrücker — analog graph.py / report.py, wo das Feld
    ebenfalls echtes Routing auslöst.

    Vorher kehrte das Feld seine eigene Absicht um: ein mitgeschicktes
    `llm_profile_id` übersprang den P5.3-Fallback, ohne selbst irgendetwas
    aufzulösen (`expand_profile_in_data` reagiert nur auf ein `llm_model` mit
    `profile:`-Präfix). Der Standardfall — Projekt hat ein Profil, User lässt
    die Modellauswahl auf "default" — landete damit still im
    Server-Default-Modell.

    Das Profil wird bewusst NICHT hier zu `llm_model` expandiert, sondern als
    `llm_profile_id` an `seed_run_stage_routing` durchgereicht. Dessen
    Profil-Branch löst die aktivierte ProviderConnection auf und koppelt sie an
    deren gebundenes Secret (SSoT, Issue #817); die lokale Expansion würde
    stattdessen Endpoint und Key aus dem Legacy-Profil einbrennen und damit
    nach einer Connection- oder Secret-Rotation auf veraltete Credentials
    zeigen. Ein unauflösbares Profil wirft dort `ValueError` → HTTP 400 über
    `@handle_api_errors`, statt mit dem literalen Modellnamen `profile:<id>`
    in die Queue zu laufen.

    Die explizite Client-Wahl selbst liest :func:`_read_client_choice`.
    """
    choice = _read_client_choice(data, project)
    # Request-Profil schlägt Projekt-Profil (Single-Run-Override), beide schlagen
    # das Server-Default-Modell. Eine explizite Modellwahl schlägt alles.
    routed_profile_id = (
        None
        if choice.explicit_model_override
        else (choice.data_profile or choice.project_profile)
    )
    if ai_model_ref is not None:
        # Eine explizite Ref ist die alleinige Routing-Quelle: kein Legacy-
        # Profil, kein Runtime-Override und kein Projektprofil-Fallback.
        routed_profile_id = None
        llm_model_override = None
        llm_runtime = parse_runtime_llm_config({})
    else:
        # UI-Profile-Token expandieren: schickt der Client selbst ein
        # `llm_model="profile:<id>"` (Legacy-Pfad aus `HeroNewRun.vue`), muss es hier
        # aufgelöst werden — `seed_run_stage_routing` kennt nur das separate Feld.
        from ..utils.llm_profile_resolver import expand_profile_in_data

        expand_profile_in_data(data)
        llm_model_override = (data.get('llm_model') or '').strip() or None
        try:
            llm_runtime = parse_runtime_llm_config(data)
        except ValueError as exc:
            raise PrepareRejected(
                json_error(
                    ApiErrorCode.VALIDATION_FAILED,
                    status=400,
                    message=str(exc),
                )
            ) from exc

    # Der "bereits vorbereitet"-Kurzschluss hängt bewusst an der *expliziten*
    # Client-Wahl, nicht an `llm_model_override`/`llm_runtime.enabled` (Issue
    # #888). Wäre er an sie gebunden, würde er für jedes Projekt mit hinterlegtem
    # Profil nie mehr greifen und jedes Betreten von Step 2 eine vollständige
    # Neu-Vorbereitung samt Persona-Neugenerierung auslösen.
    #
    # Ein Request-Profil, das vom Projekt-Default *abweicht*, ist dagegen sehr
    # wohl eine explizite Wahl: sonst käme der Endpoint mit `already_prepared`
    # zurück und die Personas blieben die des vorherigen Modells — im Widerspruch
    # zur Präzedenz "Request-Profil schlägt Projekt-Profil". Dasselbe Profil
    # erneut zu schicken bleibt der billige Revisit.
    client_requested_override = bool(
        choice.explicit_model_override
        or choice.explicit_profile_override
        or (llm_runtime.enabled and choice.explicit_runtime_request)
        or ai_model_ref is not None
    )
    return PrepareRouting(
        llm_model_override=llm_model_override,
        llm_runtime=llm_runtime,
        routed_profile_id=routed_profile_id,
        client_requested_override=client_requested_override,
    )

def _collect_prepare_inputs(data: "dict[str, Any]", project, state) -> PrepareInputs:
    """Phase 4 — fachliche Eingaben des Laufs einsammeln und validieren."""
    simulation_requirement = project.simulation_requirement or ""
    if not simulation_requirement:
        raise PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message="Project missing simulation requirement description (simulation_requirement)",
            )
        )

    # Sub-Slice 20a: optional PersonaQuotaPlan aus Body. ValidationError →
    # HTTP 400 mit Pydantic-Fehlermessage; sonst wird der Plan an den
    # Service durchgereicht (Validierung post-generation, Erzwingung in 20b).
    # Sub-Slice 22 (Gemini-Followup): spezifische Exceptions statt blankem
    # ``except Exception``, damit echte 500er nicht als 400 maskiert werden.
    try:
        quota_plan = _parse_quota_plan(data)
    except (ValidationError, ValueError, TypeError) as exc:
        raise PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=f"Invalid quota_plan: {exc}",
            )
        ) from exc

    agent_language_override = (_coerce_optional_str(data.get('language')) or '').strip().lower() or None
    if agent_language_override and agent_language_override not in ('de', 'en'):
        agent_language_override = None

    return PrepareInputs(
        simulation_requirement=simulation_requirement,
        document_text=ProjectManager.get_extracted_text(state.project_id) or "",
        entity_types=data.get('entity_types'),
        use_llm_for_profiles=data.get('use_llm_for_profiles', True),
        parallel_profile_count=data.get('parallel_profile_count') or None,
        max_agents=_resolve_max_agents_with_floor(data.get("max_agents")),
        quota_plan=quota_plan,
        agent_language_override=agent_language_override,
    )
