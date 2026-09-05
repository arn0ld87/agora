"""
Preparation-related simulation API routes split from the main module.
"""

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterator, Optional

from flask import request
from pydantic import ValidationError

from . import simulation_bp
from ..config import Config
from ..contracts import PersonaQuotaPlan
from ..models.project import ProjectManager
from ..services.degradation_collector import DegradationCollector
from ..services.entity_reader import EntityReader
from ..services.llm_routing_seed import (
    build_runtime_llm_config,
    resolve_route_api_key,
    seed_run_stage_routing,
)
from ..services.llm_runtime import parse_runtime_llm_config
from ..services.persona_eligibility import filter_eligible_entities
from ..services.prepare_service import compute_persona_target
from ..services.report_agent import MIN_SIMULATION_AGENTS
from ..services.run_lifecycle import RunLifecycle, RunPersistenceError
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.stage_model_router import StageModelRouter
from ..utils.validation import validate_simulation_id, validate_task_id
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_success, json_error
from ..utils.artifact_locator import ArtifactLocator
from .simulation_common import (
    get_artifact_store,
    get_simulation_storage,
    logger,
    run_registry,
    simulation_run_artifacts as _simulation_run_artifacts,
)


from ..utils.endpoints import LOCAL_NO_AUTH_API_KEY, is_local_endpoint

if TYPE_CHECKING:  # pragma: no cover — nur für Typprüfung
    from ..contracts.ai_provider_contract import AiModelRef
    from ..contracts.run_budget_contract import RunBudgetConfig
    from ..services.llm_runtime import RuntimeLlmConfig


@dataclass
class _PrepareStartLockEntry:
    lock: threading.Lock
    users: int = 0


_prepare_start_locks: dict[str, _PrepareStartLockEntry] = {}
_prepare_start_locks_guard = threading.Lock()
_active_prepare_jobs: set[str] = set()


@contextmanager
def _prepare_start_lock(simulation_id: str) -> Iterator[None]:
    with _prepare_start_locks_guard:
        entry = _prepare_start_locks.setdefault(
            simulation_id,
            _PrepareStartLockEntry(lock=threading.Lock()),
        )
        entry.users += 1
    try:
        with entry.lock:
            yield
    finally:
        with _prepare_start_locks_guard:
            entry.users -= 1
            if entry.users == 0 and _prepare_start_locks.get(simulation_id) is entry:
                del _prepare_start_locks[simulation_id]


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


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """
    Check whether a simulation already has all preparation artifacts.
    """
    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(simulation_dir):
        return False, {"reason": "Simulation directory does not exist"}

    store = get_artifact_store()

    # JSON-Artefakte gehen über den Store; CSV (twitter_profiles) bleibt FS-direkt
    # (out of scope für Issue #13).
    json_artifacts = {
        "state.json": ("state", lambda: store.exists(simulation_id, "state")),
        "simulation_config.json": (
            "simulation_config",
            lambda: store.exists(simulation_id, "simulation_config"),
        ),
        "reddit_profiles.json": (
            "reddit_profiles",
            lambda: store.exists(simulation_id, "reddit_profiles"),
        ),
    }

    existing_files = []
    missing_files = []
    for filename, (_, exists_fn) in json_artifacts.items():
        if exists_fn():
            existing_files.append(filename)
        else:
            missing_files.append(filename)

    twitter_csv = os.path.join(simulation_dir, "twitter_profiles.csv")
    if os.path.exists(twitter_csv):
        existing_files.append("twitter_profiles.csv")
    else:
        missing_files.append("twitter_profiles.csv")

    if missing_files:
        return False, {
            "reason": "Missing required files",
            "missing_files": missing_files,
            "existing_files": existing_files,
        }

    try:
        state_data = store.read_json(simulation_id, "state", default=None)
        if not state_data:
            return False, {"reason": "State file is unreadable or temporarily incomplete"}

        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)
        logger.debug(
            f"Detect simulation preparation status: {simulation_id}, status={status}, config_generated={config_generated}"
        )

        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
        if status in prepared_statuses and config_generated:
            profiles_data = store.read_json(simulation_id, "reddit_profiles", default=[]) or []
            profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0

            if status == "preparing":
                try:
                    from datetime import datetime

                    state_data["status"] = "ready"
                    state_data["updated_at"] = datetime.now().isoformat()
                    store.write_json(simulation_id, "state", state_data)
                    logger.info(f"Auto update simulation status: {simulation_id} preparing -> ready")
                    status = "ready"
                except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
                    logger.warning(f"Failed to auto update status: {exc}")

            logger.info(
                f"Simulation {simulation_id} Detection result: HasPreparation complete (status={status}, config_generated={config_generated})"
            )
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files,
            }

        logger.warning(
            f"Simulation {simulation_id} Detection result: Has notPreparation complete (status={status}, config_generated={config_generated})"
        )
        return False, {
            "reason": (
                "Status not in prepared list or config_generated is false: "
                f"status={status}, config_generated={config_generated}"
            ),
            "status": status,
            "config_generated": config_generated,
        }

    except Exception as exc:  # noqa: BLE001 — exc used in response payload
        return False, {"reason": f"Failed to read state file: {str(exc)}"}


class _PrepareRejected(Exception):
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


def _ensure_prepare_startable(
    state: Any,
    simulation_id: str,
) -> None:
    """Verhindert zwei schreibende Prepare-Jobs fuer dieselbe Simulation."""
    if state.status != SimulationStatus.PREPARING:
        return
    with _prepare_start_locks_guard:
        active_job_exists = simulation_id in _active_prepare_jobs
    if not active_job_exists:
        return
    raise _PrepareRejected(
        json_error(
            ApiErrorCode.SIMULATION_PREPARE_IN_PROGRESS,
            status=409,
            message="Simulation preparation is already in progress",
        )
    )


@dataclass(frozen=True)
class _PrepareRequest:
    """Validierte Eingaben eines ``POST /api/simulation/prepare``.

    Interner Parameter-Container zwischen den Prepare-Phasen, **kein**
    API-Vertrag: die Wire-Validierung bleibt feldweise in den Parse-Phasen.
    """

    simulation_id: str
    ai_model_ref: "AiModelRef | None"
    budget_config: "RunBudgetConfig | None"
    force_regenerate: bool


@dataclass(frozen=True)
class _PrepareRouting:
    """Ergebnis der Routing-Auflösung (Profil, Modell-Override, Runtime)."""

    llm_model_override: "str | None"
    llm_runtime: "RuntimeLlmConfig"
    routed_profile_id: "str | None"
    client_requested_override: bool


@dataclass(frozen=True)
class _PrepareInputs:
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
        raise _PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message="Please provide simulation_id",
            )
        )

    if not validate_simulation_id(simulation_id):
        raise _PrepareRejected(
            json_error(
                ApiErrorCode.INVALID_ID,
                status=400,
                message="Invalid simulation_id format",
            )
        )

    raw_ai_model_ref = data.get("ai_model_ref")
    if raw_ai_model_ref is None:
        return simulation_id, None

    from ..contracts.ai_provider_contract import AiModelRef

    try:
        ai_model_ref = AiModelRef.model_validate(raw_ai_model_ref)
    except ValidationError:
        raise _PrepareRejected(
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
        raise _PrepareRejected(
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

    from ..contracts.run_budget_contract import RunBudgetConfig

    try:
        return RunBudgetConfig.model_validate(raw_budget)
    except ValidationError:
        raise _PrepareRejected(
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
        raise _PrepareRejected(
            json_error(
                ApiErrorCode.NOT_FOUND,
                status=404,
                message=f"Project does not exist: {state.project_id}",
            )
        )
    return project


@dataclass(frozen=True)
class _ClientChoice:
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


def _read_client_choice(data: "dict[str, Any]", project) -> _ClientChoice:
    """Explizite Client-Wahl aus Body und Projekt lesen.

    `default` ist die UI-Platzhalterwahl (`useEnvForm.effectiveModel()` liefert
    dafür `null`) und zählt deshalb nicht als explizite Modellwahl.
    """
    data_profile = (data.get('llm_profile_id') or '').strip() or None
    project_profile = (getattr(project, 'llm_profile_id', None) or '').strip() or None
    data_model = (data.get('llm_model') or '').strip() or None
    return _ClientChoice(
        data_profile=data_profile,
        project_profile=project_profile,
        explicit_model_override=bool(data_model and data_model.lower() != 'default'),
        explicit_runtime_request=bool(data.get('llm_provider')),
    )


def _resolve_prepare_routing(
    data: "dict[str, Any]", project, ai_model_ref: "AiModelRef | None"
) -> _PrepareRouting:
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
            raise _PrepareRejected(
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
    return _PrepareRouting(
        llm_model_override=llm_model_override,
        llm_runtime=llm_runtime,
        routed_profile_id=routed_profile_id,
        client_requested_override=client_requested_override,
    )


def _already_prepared_response(simulation_id: str):
    """Phase 3 — Kurzschluss, wenn alle Vorbereitungs-Artefakte schon liegen.

    Gibt ``None`` zurück, wenn regulär vorbereitet werden muss.
    """
    logger.debug(f"Check simulation {simulation_id} Is preparation complete...")
    is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
    logger.debug(f"Check result: is_prepared={is_prepared}, prepare_info={prepare_info}")
    if not is_prepared:
        logger.info(f"Simulation {simulation_id} has no preparation complete, preparing now")
        return None

    logger.info(f"Simulation {simulation_id} has preparation complete, no need to regenerate")
    return json_success({
        "simulation_id": simulation_id,
        "status": "ready",
        "message": "Preparation already completed, no need to regenerate",
        "already_prepared": True,
        "prepare_info": prepare_info,
    })


def _collect_prepare_inputs(data: "dict[str, Any]", project, state) -> _PrepareInputs:
    """Phase 4 — fachliche Eingaben des Laufs einsammeln und validieren."""
    simulation_requirement = project.simulation_requirement or ""
    if not simulation_requirement:
        raise _PrepareRejected(
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
        raise _PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=f"Invalid quota_plan: {exc}",
            )
        ) from exc

    agent_language_override = (data.get('language') or '').strip().lower() or None
    if agent_language_override and agent_language_override not in ('de', 'en'):
        agent_language_override = None

    return _PrepareInputs(
        simulation_requirement=simulation_requirement,
        document_text=ProjectManager.get_extracted_text(state.project_id) or "",
        entity_types=data.get('entity_types'),
        use_llm_for_profiles=data.get('use_llm_for_profiles', True),
        parallel_profile_count=data.get('parallel_profile_count') or None,
        max_agents=_resolve_max_agents_with_floor(data.get("max_agents")),
        quota_plan=quota_plan,
        agent_language_override=agent_language_override,
    )


def _preview_entity_counts(state, storage, inputs: _PrepareInputs) -> None:
    """Phase 5 — Entitätenzahl für die Antwort vorab schätzen (best effort).

    Fehler sind hier bewusst nicht fatal: der Hintergrund-Task liest dieselbe
    Menge erneut.
    """
    try:
        logger.info(f"Synchronously get entity count: graph_id={state.graph_id}")
        reader = EntityReader(storage)
        filtered_preview = reader.filter_defined_entities(
            graph_id=state.graph_id,
            defined_entity_types=inputs.entity_types,
            enrich_with_edges=False,
        )
        # Issue #1034: derselbe Eignungsfilter wie im Laufpfad
        # (_phase_read_entities) — sonst zeigt der Preview-Nenner eine
        # Menge, die die eigentliche Generierung so nie erzeugt.
        # Bewusst ohne Sammler: diese Vorschau hat kein Task-Ergebnis, in
        # das ein Befund fließen könnte. Gemeldet wird im Laufpfad, der
        # dieselbe Menge erneut filtert. Ein Sammler an dieser Stelle
        # sähe nach Absicherung aus und wäre folgenlos.
        eligibility_preview = filter_eligible_entities(
            filtered_preview.entities,
            degradations=None,
        )
        if eligibility_preview.exclusions:
            filtered_preview.entities = eligibility_preview.eligible
            filtered_preview.filtered_count = len(filtered_preview.entities)
            filtered_preview.entity_types = {
                entity.get_entity_type() or "Entity"
                for entity in filtered_preview.entities
            }
        # Issue #1177: derselbe Dedup wie im Laufpfad. Ohne ihn zeigte die
        # Vorschau die Zahl vor der Bereinigung und damit mehr Personas, als
        # die Generierung anschliessend erzeugt — der Nutzer saehe eine Zahl,
        # die nie eintritt. Der Kommentar oben nennt genau diese Gefahr
        # bereits fuer den Eignungsfilter.
        from ..services.prepare_service import _dedupe_entities

        deduped_preview, duplicate_count = _dedupe_entities(filtered_preview.entities)
        if duplicate_count:
            filtered_preview.entities = deduped_preview
            filtered_preview.filtered_count = len(deduped_preview)
            filtered_preview.entity_types = {
                entity.get_entity_type() or "Entity" for entity in deduped_preview
            }

        preview_count = filtered_preview.filtered_count
        if inputs.max_agents is not None and inputs.max_agents > 0:
            preview_count = min(preview_count, inputs.max_agents)
        state.entities_count = preview_count
        state.entity_types = list(filtered_preview.entity_types)
        logger.info(
            "Expected entity count: %s, entity types: %s",
            filtered_preview.filtered_count,
            filtered_preview.entity_types,
        )
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(
            "Synchronous entity count failed (will retry in the background task): %s", exc
        )


def _precheck_prepare_ai_model_ref(ai_model_ref: "AiModelRef | None") -> None:
    """Phase 6a — Connection der expliziten ``AiModelRef`` vorab prüfen."""
    if ai_model_ref is None:
        return

    from ..services.llm_routing_seed import prevalidate_ai_model_ref

    try:
        prevalidate_ai_model_ref(ai_model_ref)
    except ValueError as exc:
        raise _PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=str(exc),
            )
        ) from exc


def _begin_prepare_run(
    req: _PrepareRequest, state, routing: _PrepareRouting
) -> RunLifecycle:
    """Phase 6b — Lifecycle für den Run-Record des Vorbereitungslaufs bauen."""
    return RunLifecycle.begin(
        run_registry,
        "simulation_prepare",
        req.simulation_id,
        failure_message="Simulation preparation failed: {exc_type}",
        progress=0,
        message="Simulation preparation queued",
        linked_ids={
            "simulation_id": req.simulation_id,
            "project_id": state.project_id,
        },
        artifacts=_simulation_run_artifacts(req.simulation_id),
        resume_capability={"available": True, "action": "restart", "label": "Restart preparation"},
        branch_label=state.branch_name,
        metadata={
            "project_id": state.project_id,
            "graph_id": state.graph_id,
            "source_simulation_id": state.source_simulation_id,
            "root_simulation_id": state.root_simulation_id,
            "branch_name": state.branch_name,
            "branch_depth": state.branch_depth,
            "llm_model": routing.llm_model_override,
            "llm_provider": routing.llm_runtime.redacted_metadata() or None,
            # Budget-Config (Issue #764) — nur Limits, keine Secrets
            **({"budget": req.budget_config.model_dump(mode="json")} if req.budget_config else {}),
        },
    )


def _seed_prepare_routing(
    run_record: "dict[str, Any]",
    routing: _PrepareRouting,
    ai_model_ref: "AiModelRef | None",
) -> None:
    """Phase 7 — Stage-Routing für ``persona_generation`` seeden."""
    if ai_model_ref is None:
        seed_run_stage_routing(
            run_record["run_id"],
            "persona_generation",
            llm_model_override=routing.llm_model_override,
            llm_runtime=routing.llm_runtime,
            llm_profile_id=routing.routed_profile_id,
        )
        return

    try:
        seed_run_stage_routing(
            run_record["run_id"],
            "persona_generation",
            llm_model_override=routing.llm_model_override,
            llm_runtime=routing.llm_runtime,
            llm_profile_id=routing.routed_profile_id,
            ai_model_ref=ai_model_ref,
        )
    except ValueError as exc:
        raise _PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=str(exc),
            ),
            run_failure_message=str(exc),
        ) from exc


def _resolve_prepare_route(run_record: "dict[str, Any]", llm_runtime):
    """Phase 8 — Stage-Route auflösen, sperren und den API-Key bestimmen."""
    route_router = StageModelRouter(run_record["run_id"])
    resolved_route = route_router.resolve("persona_generation")
    route_router.lock_stage("persona_generation", resolved_route)
    resolved_api_key = resolve_route_api_key(resolved_route, llm_runtime)

    if resolved_api_key is None and not is_local_endpoint(resolved_route.base_url_sanitized):
        guard_message = (
            f"provider_override: kein api_key im Payload und kein Key in der Settings-DB "
            f"für Provider '{resolved_route.provider_id}'. "
            "Bitte in Einstellungen → LLM-Anbieter einen Schlüssel speichern "
            "oder im Sitzungsfeld eingeben."
        )
        raise _PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=422,
                message=guard_message,
            ),
            run_failure_message=guard_message,
        )

    if resolved_api_key is None and is_local_endpoint(resolved_route.base_url_sanitized):
        # Lokaler Endpoint ohne Key ist explizit freigegeben (siehe Guard oben) —
        # der Platzhalter ersetzt `None`, damit der Generator-Vertrag aus #778
        # (Key und Base-URL aus derselben Quelle) nicht faelschlich einen
        # ValueError wirft.
        resolved_api_key = LOCAL_NO_AUTH_API_KEY

    return resolved_route, resolved_api_key


def _build_progress_callback(task_manager, task_id: str) -> "Callable[..., None]":
    """Fortschritts-Callback über die vier Vorbereitungs-Stages."""
    stage_details: "dict[str, dict[str, Any]]" = {}

    def progress_callback(stage, progress, message, **kwargs):
        stage_weights = {
            "reading": (0, 20),
            "generating_profiles": (20, 70),
            "generating_config": (70, 90),
            "copying_scripts": (90, 100),
        }

        start, end = stage_weights.get(stage, (0, 100))
        current_progress = int(start + (end - start) * progress / 100)

        stage_names = {
            "reading": "Read knowledge graph entities",
            "generating_profiles": "GenerateAgentpersona",
            "generating_config": "Generate simulation configuration",
            "copying_scripts": "Prepare simulation scripts",
        }

        stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
        total_stages = len(stage_weights)

        stage_details[stage] = {
            "stage_name": stage_names.get(stage, stage),
            "stage_progress": progress,
            "current": kwargs.get("current", 0),
            "total": kwargs.get("total", 0),
            "item_name": kwargs.get("item_name", ""),
        }

        detail = stage_details[stage]
        progress_detail_data = {
            "current_stage": stage,
            "current_stage_name": stage_names.get(stage, stage),
            "stage_index": stage_index,
            "total_stages": total_stages,
            "stage_progress": progress,
            "current_item": detail["current"],
            "total_items": detail["total"],
            "item_description": message,
        }

        if detail["total"] > 0:
            detailed_message = (
                f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: "
                f"{detail['current']}/{detail['total']} - {message}"
            )
        else:
            detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {message}"

        task_manager.update_task(
            task_id,
            progress=current_progress,
            message=detailed_message,
            progress_detail=progress_detail_data,
        )

    return progress_callback


def _finish_cancelled_prepare_run(run_id: str, *, simulation_id: str) -> None:
    """Setzt den Abbruch-Endzustand eines per ``/cancel`` gestoppten Prepare-Laufs.

    Issue B2. Spiegelt bewusst ``services/report_generation.py::finish_cancelled_run``:
    ``stopped`` + ``termination_reason="user_cancel"``, Teilergebnisse bleiben
    als Artefakt erhalten. Anders als beim Report gibt es hier kein separates
    ``report_id`` — die einzigen Prepare-Artefakte hängen an ``simulation_id``
    (u. a. die Profildatei, die ``_phase_generate_profiles`` laufend speichert,
    nicht erst am Phasenende). Das Flag wird danach gelöscht, damit ein
    erneuter Prepare-Versuch (neue ``run_id``) nicht sofort wieder abbricht.
    """
    from ..services.sim.cancel_flag import clear_cancel

    run_registry.update_run(
        run_id,
        status="stopped",
        termination_reason="user_cancel",
        message=(
            "Vom Nutzer abgebrochen — bereits generierte Personas bleiben "
            "als Teilergebnis erhalten"
        ),
        event_type="user_cancel",
        artifacts=ArtifactLocator.existing_paths({
            "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
        }),
        resume_capability={
            "available": True,
            "action": "restart",
            "label": "Restart simulation preparation",
        },
    )
    clear_cancel(run_id)


def _make_prepare_job(
    *,
    manager,
    task_manager,
    task_id: str,
    simulation_id: str,
    inputs: _PrepareInputs,
    storage,
    llm_model: str,
    effective_llm_runtime,
    run_record: "dict[str, Any]",
) -> "Callable[[], None]":
    """Phase 9 — den Hintergrund-Job bauen, der die Vorbereitung ausführt."""
    from ..models.task import TaskStatus
    from ..services.prepare_service import PrepareCancelledError
    from ..services.run_budget import BudgetExceededError, mark_budget_abort

    def run_prepare() -> None:
        # Issue #1034: Der Collector gehört dem Task, nicht dem Service —
        # gleiches Muster wie im Graph-Build (``services/graph_build.py``).
        # Nur so überlebt ein stiller Teilausfall bis ins Task-Ergebnis;
        # ein im Service erzeugter Sammler wäre nach der Rückkehr weg.
        degradations = DegradationCollector()
        try:
            task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=0,
                message="Start preparing simulation environment...",
            )

            result_state = manager.prepare_simulation(
                simulation_id=simulation_id,
                simulation_requirement=inputs.simulation_requirement,
                document_text=inputs.document_text,
                defined_entity_types=inputs.entity_types,
                use_llm_for_profiles=inputs.use_llm_for_profiles,
                progress_callback=_build_progress_callback(task_manager, task_id),
                parallel_profile_count=inputs.parallel_profile_count,
                storage=storage,
                llm_model=llm_model,
                llm_runtime=effective_llm_runtime,
                language=inputs.agent_language_override,
                max_agents=inputs.max_agents,
                quota_plan=inputs.quota_plan,
                # Budget-Enforcement (#984): dieselbe persistierte run_id wie
                # der Prepare-Run — Persona- und Config-Generierung bauen ihre
                # LLM-Clients damit run-gebunden statt budgetfrei.
                run_id=run_record["run_id"],
                degradations=degradations,
            )

            task_manager.complete_task(
                task_id,
                result={
                    **result_state.to_simple_dict(),
                    # Leere Liste heißt „nichts ist still ausgefallen“.
                    "degradations": degradations.report().model_dump(mode="json"),
                },
            )

        except PrepareCancelledError:
            # Issue B2: Nutzerabbruch über POST /api/runs/<id>/cancel.
            # Reihenfolge bindend (gleiche Falle wie #978/#841): complete_task()
            # zuerst — sync_task() setzt sonst generisch "completed" — dann der
            # detaillierte Run-Update mit status="stopped" zuletzt, sonst
            # überschreibt sync_task() ihn wieder.
            logger.info(
                "Simulation prepare cancelled by user (run_id=%s, simulation_id=%s)",
                run_record["run_id"], simulation_id,
            )
            task_manager.complete_task(
                task_id,
                result={
                    "simulation_id": simulation_id,
                    "status": "cancelled",
                    "cancelled": True,
                    "degradations": degradations.report().model_dump(mode="json"),
                },
            )
            _finish_cancelled_prepare_run(
                run_record["run_id"],
                simulation_id=simulation_id,
            )
        except BudgetExceededError as exc:
            # Budgetabbruch (#984): Teilresultate bleiben erhalten, der Run
            # endet "stopped" + termination_reason statt technischem "failed".
            # Reihenfolge bindend (#978/#841): fail_task() zuerst — sync_task
            # setzt generisch "failed" —, mark_budget_abort() zuletzt.
            logger.warning(
                "Simulation prepare budget-aborted (run_id=%s, simulation_id=%s): %s",
                run_record["run_id"], simulation_id, exc,
            )
            task_manager.fail_task(task_id, str(exc))
            task_manager.update_task(
                task_id,
                result={"degradations": degradations.report().model_dump(mode="json")},
            )
            mark_budget_abort(
                run_record["run_id"], exc.dimension, exc.observed, exc.threshold
            )
            failed_state = manager.get_simulation(simulation_id)
            if failed_state:
                failed_state.error = str(exc)
                manager._set_status(failed_state, SimulationStatus.FAILED)
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.error(f"Failed to prepare simulation: {str(exc)}")
            task_manager.fail_task(task_id, str(exc))
            # Auch der Fehlerfall trägt die Befunde: sie nennen oft die
            # Ursache, die die Exception-Message selbst nicht mehr kennt
            # (etwa "alle Entitäten waren ungeeignet" statt "kein Graph").
            task_manager.update_task(
                task_id,
                result={"degradations": degradations.report().model_dump(mode="json")},
            )

            failed_state = manager.get_simulation(simulation_id)
            if failed_state:
                failed_state.error = str(exc)
                manager._set_status(failed_state, SimulationStatus.FAILED)
        finally:
            # Review-Finding (PR #1371, Befund 7): ohne diesen finally-Block
            # räumte nur der PrepareCancelledError-Zweig das Flag über
            # _finish_cancelled_prepare_run auf. Kommt die Cancel-Anfrage
            # NACH dem letzten Checkpoint (z. B. während _phase_generate_config,
            # die keinen eigenen Check hat), läuft der Job normal zu Ende —
            # die Nachricht springt für den Nutzer von "Cancel requested —
            # finishing current stage" auf "completed", und das
            # threading.Event bliebe für die restliche Prozesslaufzeit im
            # globalen Dict von cancel_flag.py liegen (kleines, aber echtes
            # Leck über viele Läufe). ``clear_cancel`` ist idempotent, ein
            # zweiter Aufruf im Cancel-Zweig oben ist folgenlos.
            from ..services.sim.cancel_flag import clear_cancel, is_cancel_requested

            if is_cancel_requested(run_record["run_id"]):
                logger.info(
                    "Simulation prepare: Cancel-Flag war gesetzt, aber der "
                    "letzte Checkpoint war bereits passiert (run_id=%s, "
                    "simulation_id=%s) — Abbruch kam zu spät, Endzustand "
                    "bleibt wie oben bestimmt.",
                    run_record["run_id"], simulation_id,
                )
            clear_cancel(run_record["run_id"])

    return run_prepare


def _track_active_prepare_job(
    simulation_id: str,
    target: "Callable[[], None]",
) -> "Callable[[], None]":
    with _prepare_start_locks_guard:
        _active_prepare_jobs.add(simulation_id)

    def tracked() -> None:
        try:
            target()
        finally:
            with _prepare_start_locks_guard:
                _active_prepare_jobs.discard(simulation_id)

    return tracked


def _discard_active_prepare_job(simulation_id: str) -> None:
    with _prepare_start_locks_guard:
        _active_prepare_jobs.discard(simulation_id)


def _build_prepare_response(
    simulation_id: str,
    task_id: str,
    run_record: "dict[str, Any]",
    state,
    inputs: _PrepareInputs,
) -> "dict[str, Any]":
    """Phase 10 — Antwort-Payload des angestoßenen Vorbereitungslaufs."""
    return {
        "simulation_id": simulation_id,
        "task_id": task_id,
        "run_id": run_record["run_id"],
        "status": "preparing",
        "message": "Preparation task started; query progress via /api/simulation/prepare/status",
        "already_prepared": False,
        "expected_entities_count": state.entities_count,
        "entity_types": state.entity_types,
        # Issue #1034: Der Fortschrittszähler zählt Personas, nicht
        # Entitäten. `expected_entities_count` bleibt die Entitätenzahl;
        # den Nenner liefert `persona_target` aus derselben Funktion, die
        # auch `_phase_generate_profiles` im Laufpfad verwendet.
        "persona_target": compute_persona_target(
            state.entities_count,
            max_agents=inputs.max_agents,
            quota_plan=inputs.quota_plan,
        ).model_dump(mode="json"),
    }


def _prepare_simulation_under_start_lock(
    data: "dict[str, Any]",
    simulation_id: str,
    ai_model_ref: "AiModelRef | None",
):
    """Prüft und startet Prepare innerhalb des simulationsbezogenen Locks."""
    from ..models.task import TaskManager

    try:
        manager = SimulationManager()
        task_manager = TaskManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            raise _PrepareRejected(
                json_error(
                    ApiErrorCode.NOT_FOUND,
                    status=404,
                    message=f"Simulation does not exist: {simulation_id}",
                )
            )

        _ensure_prepare_startable(state, simulation_id)

        req = _PrepareRequest(
            simulation_id=simulation_id,
            ai_model_ref=ai_model_ref,
            budget_config=_parse_prepare_budget(data),
            force_regenerate=data.get('force_regenerate', False),
        )
        project = _load_prepare_project(state)
        routing = _resolve_prepare_routing(data, project, ai_model_ref)

        logger.info(
            f"Start processing /prepare Request: simulation_id={simulation_id}, "
            f"force_regenerate={req.force_regenerate}",
            extra={'simulation_id': simulation_id},
        )

        if not req.force_regenerate and not routing.client_requested_override:
            already_prepared = _already_prepared_response(simulation_id)
            if already_prepared is not None:
                return already_prepared

        inputs = _collect_prepare_inputs(data, project, state)
        storage = get_simulation_storage()
        _preview_entity_counts(state, storage, inputs)

        _precheck_prepare_ai_model_ref(ai_model_ref)
    except _PrepareRejected as rejected:
        # Vor der Run-Registrierung — es gibt noch keinen Record, der
        # verwaisen könnte.
        return rejected.response

    # Issue #841/#1183: Ab der Registrierung existiert ein Run-Record mit
    # status="pending". Task-Kopplung (#841-Reihenfolge), BaseException-Netz
    # und strikte Persistenzsemantik (#844) liegen im RunLifecycle. Auch
    # Statuswechsel und Enqueue laufen innerhalb des Fensters — ihr Scheitern
    # hinterließ vorher einen pending-Phantom.
    try:
        with _begin_prepare_run(req, state, routing) as run:
            run_record = run.record
            task_id = task_manager.create_task(
                task_type="simulation_prepare",
                metadata={
                    "simulation_id": req.simulation_id,
                    "project_id": state.project_id,
                    "run_id": run_record["run_id"],
                },
            )
            run.attach_task(task_manager, task_id)
            _seed_prepare_routing(run_record, routing, ai_model_ref)
            resolved_route, resolved_api_key = _resolve_prepare_route(
                run_record, routing.llm_runtime
            )

            effective_llm_runtime = build_runtime_llm_config(resolved_route, resolved_api_key)

            manager._set_status(state, SimulationStatus.PREPARING)

            # TODO(P0-queue): migrate to Redis-Queue (RQ) in Wave 2 — see app/jobs/__init__.py
            from ..jobs import enqueue
            tracked_job = _track_active_prepare_job(
                simulation_id,
                _make_prepare_job(
                    manager=manager,
                    task_manager=task_manager,
                    task_id=task_id,
                    simulation_id=simulation_id,
                    inputs=inputs,
                    storage=storage,
                    llm_model=resolved_route.model,
                    effective_llm_runtime=effective_llm_runtime,
                    run_record=run_record,
                ),
            )
            try:
                enqueue("simulation_prepare", tracked_job)
            except BaseException:
                _discard_active_prepare_job(simulation_id)
                raise
    except RunPersistenceError:
        # #844: Die failed-Markierung wurde nicht persistiert — das darf nicht
        # wie eine sauber abgeschlossene Ablehnung aussehen.
        return json_error(
            ApiErrorCode.INTERNAL_ERROR,
            status=500,
            message=(
                "Interner Fehler beim Markieren des Runs als fehlgeschlagen. "
                "Bitte erneut versuchen."
            ),
        )
    except _PrepareRejected as rejected:
        return rejected.response

    return json_success(_build_prepare_response(simulation_id, task_id, run_record, state, inputs))


@simulation_bp.route('/prepare', methods=['POST'])
@handle_api_errors(log_prefix="Failed to start preparation task")
def prepare_simulation():
    """Prepare a simulation environment as an async task."""
    data = request.get_json() or {}
    try:
        simulation_id, ai_model_ref = _parse_prepare_identity(data)
    except _PrepareRejected as rejected:
        return rejected.response

    with _prepare_start_lock(simulation_id):
        return _prepare_simulation_under_start_lock(data, simulation_id, ai_model_ref)


@simulation_bp.route('/prepare/status', methods=['POST'])
@handle_api_errors(log_prefix="Failed to query task status")
def get_prepare_status():
    """Query preparation progress by task_id or simulation_id."""
    from ..models.task import TaskManager

    data = request.get_json() or {}
    task_id = data.get('task_id')
    simulation_id = data.get('simulation_id')

    if task_id and not validate_task_id(task_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid task_id format",
        )
    if simulation_id and not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    if simulation_id:
        is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
        if is_prepared:
            return json_success({
                "simulation_id": simulation_id,
                "status": "ready",
                "progress": 100,
                "message": "Preparation already completed",
                "already_prepared": True,
                "prepare_info": prepare_info,
            })

    if not task_id:
        if simulation_id:
            return json_success({
                "simulation_id": simulation_id,
                "status": "not_started",
                "progress": 0,
                "message": "Preparation not started yet, please call /api/simulation/prepare",
                "already_prepared": False,
            })
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="Please provide task_id or simulation_id",
        )

    task_manager = TaskManager()
    task = task_manager.get_task(task_id)
    if not task:
        if simulation_id:
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            if is_prepared:
                return json_success({
                    "simulation_id": simulation_id,
                    "task_id": task_id,
                    "status": "ready",
                    "progress": 100,
                    "message": "Task complete (PrepareWork already exists)",
                    "already_prepared": True,
                    "prepare_info": prepare_info,
                })

        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Task does not exist: {task_id}",
        )

    task_dict = task.to_dict()
    task_dict["already_prepared"] = False
    return json_success(task_dict)
