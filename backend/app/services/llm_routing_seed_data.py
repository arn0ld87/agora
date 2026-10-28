"""Data definitions, credential scope helpers, and provider connection utilities for LLM routing seed.

Extracted from ``llm_routing_seed.py`` while keeping all symbols re-exported
from ``app.services.llm_routing_seed`` for full backwards and monkeypatch compatibility.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Mapping, NamedTuple, Optional, cast
from uuid import UUID

from ..contracts.ai_provider_contract import AiModelRef, ProviderConnection
from ..contracts.auth_contract import AuthType
from ..contracts.llm_routing_contract import (
    ResolvedRoute,
    RuntimeLlmRouting,
    StageId,
    StageLLMRoute,
)
from ..contracts.provider_types import (
    ANTHROPIC_CHAT_TRANSPORT_UNSUPPORTED,
    PROVIDER_ANTHROPIC,
    PROVIDER_CLAUDE_CLI,
    PROVIDER_CODEX_CLI,
)
from .llm_runtime import RuntimeLlmConfig

_credential_workspace: ContextVar["UUID | object | None"] = ContextVar(
    "agora_credential_workspace", default=None
)

# Finding H3 (Security-Review 2026-09-26, #1688): an operator job binds its
# resolved scope (``None``) to ``_credential_workspace`` exactly like an
# unbound context's own default value — a nested
# ``workspace_credential_id_for_run(None)`` call inside that job's thread
# could then not tell "explicitly bound: operator" apart from "never bound
# at all" and re-derived a scope from scratch, hitting the demo-mode
# default-deny raise even for a legitimate operator run. This sentinel is
# bound instead of ``None`` so the fast path recognises an explicit
# operator scope without re-deriving anything, while a thread that never
# entered :func:`workspace_credential_context_for_run` still sees the
# unbound default and keeps raising in demo mode.
_OPERATOR_SENTINEL = object()

# Finding B1 (#1688): private marker key ``build_route_subprocess_env`` uses
# to smuggle a workspace-owned secret payload (JSON) past the plain env dict
# it otherwise returns. Not a real subprocess env var — ``_build_subprocess_env``
# (``process_environment.py``) pops it out and turns it into a pipe FD
# instead of ever writing it into the child's OS environment block.
WORKSPACE_SECRET_ENV_MARKER = "__AGORA_WORKSPACE_SECRET_PAYLOAD__"  # noqa: S105 -- env key name, not a credential

# Finding H5 (Security-Review 2026-09-26, #1688): non-secret signal set on
# EVERY workspace-scoped run's subprocess env, independent of whether a
# workspace key actually resolved. ``_sim_common.py`` (child) uses its mere
# presence — not the presence/absence of a secret payload — to refuse
# ``.env``/acceleration-provider ("boost") fallback and to treat a missing
# or key-less pipe payload as a hard failure instead of a silent no-op.
CREDENTIAL_SCOPE_ENV_KEY = "AGORA_CREDENTIAL_SCOPE"  # noqa: S105
WORKSPACE_CREDENTIAL_SCOPE_VALUE = "workspace"  # noqa: S105

_PROVIDER_ID_MAP = {
    "default": None,
    "openai": "openai",
    "google": "google",
    "custom_openai": "openai_compatible",
    "github_copilot": "github_copilot",
}

_ROUTE_TO_RUNTIME_PROVIDER = {
    "openai": "openai",
    "google": "google",
    "openai_compatible": "custom_openai",
    "ollama_cloud": "custom_openai",
    "github_copilot": "custom_openai",
    # Issue #1418: alle anderen Provider fallen auf den generischen
    # "custom_openai"-Bucket — unschaedlich, weil ``base_url`` als String
    # genug Information fuer die spaetere Provider-Erkennung traegt
    # (``detect_provider`` mustert auf URL-Muster). codex_cli hat aber gar
    # keine ``base_url`` (transport="cli", #1405) — ohne eigenen Eintrag
    # verschwindet in ``build_runtime_llm_config`` die einzige Information,
    # die ``_resolve_llm_connection`` braeuchte, um ein fehlendes
    # ``base_url`` als Normalfall statt als Ausloeser fuer den
    # ``.env``-Fallback zu erkennen. claude_cli (transport="cli") hat dieselbe
    # Eigenschaft — kein ``base_url`` — deshalb derselbe Selbst-Eintrag.
    PROVIDER_CODEX_CLI: PROVIDER_CODEX_CLI,
    PROVIDER_CLAUDE_CLI: PROVIDER_CLAUDE_CLI,
}


def map_runtime_provider_to_route_provider(provider: str) -> Optional[str]:
    from . import llm_routing_seed as _seed

    return _seed._PROVIDER_ID_MAP.get((provider or "default").strip().lower())


def _reject_anthropic_connection(connection: ProviderConnection) -> None:
    """Faellt laut aus, wenn ``connection`` eine Anthropic-Connection ist (#1284).

    Gemeinsames Gate fuer beide Connection-Aufloesungspfade in diesem Modul
    (``ai_model_ref`` ueber :func:`_resolve_selected_connection` und
    ``llm_profile_id`` ueber ``resolve_profile_connection``) — kein nativer
    Anthropic-Chat-Transport, Discovery/CRUD der Connection bleiben
    unberuehrt. Siehe Modul-Konstante ``ANTHROPIC_CHAT_TRANSPORT_UNSUPPORTED``.
    """
    if connection.provider_kind == PROVIDER_ANTHROPIC:
        raise ValueError(ANTHROPIC_CHAT_TRANSPORT_UNSUPPORTED)


# Issue #901: Ersatzgrund, wenn das UI source="fallback" ohne Begruendung
# schickt. Der Wert ist bewusst maschinenlesbar und als Luecke erkennbar —
# nicht als echter Grund getarnt.
_UNSPECIFIED_FALLBACK_REASON = "unspecified_fallback"


def _fallback_reason_for(ai_model_ref: AiModelRef) -> Optional[str]:
    """Fallback-Grund fuer die Stage-Route bestimmen.

    ``AiModelRef.fallback_reason`` ist optional, ``source="fallback"`` bildet
    aber auf ``RouteSource="provider_fallback"`` ab, dessen Validator einen
    nicht-leeren Grund verlangt. Diese Kombination ist ueber die UI real
    erreichbar: ``AiModelPicker`` setzt bei einer unbekannten Item-ID
    ``source="fallback"``, ohne einen Grund ableiten zu koennen.

    Der Seed darf daran nicht scheitern. ``seed_run_stage_routing`` laeuft in
    ``simulation_run.py`` **nach** ``run_registry.create_run`` und ist dort
    nicht in ein ``try/except`` gefasst — eine Exception hinterliesse einen
    verwaisten ``pending``-Run und antwortete mit 500. Statt den Aufrufpfad
    umzubauen, fuellt der Seed die Luecke deterministisch auf; die Information
    "Fallback ohne angegebenen Grund" bleibt dabei erhalten und ist im Audit
    von einem echten Grund unterscheidbar.
    """
    from . import llm_routing_seed as _seed

    if ai_model_ref.source != "fallback":
        return ai_model_ref.fallback_reason
    reason = (ai_model_ref.fallback_reason or "").strip()
    return reason or _seed._UNSPECIFIED_FALLBACK_REASON


def _prune_stage_overrides(config: RuntimeLlmRouting) -> int:
    """Verwirft persistierte ``stage_overrides``, deren Provider-ID in der
    aktuellen ``LlmProviderRegistry`` unbekannt ist oder deren ``base_url``
    zu keiner aktivierten ``ProviderConnection`` mehr passt.

    Stale-Override = Symptom eines Env-Wechsels (``LLM_BASE_URL``,
    ``LLM_MODEL_NAME`` oder die ProviderConnection-Landschaft hat sich seit
    dem letzten ``save_config`` geändert). Ohne Pruning würde der
    Stage-Router den alten Endpoint aufrufen und dort z. B. HTML
    (``<title>Ollama</title>``) statt JSON erhalten — NER loggt
    ``NER done: 0 entities, 0 relations`` ohne Fehler, Graph-Build läuft
    mit leerem Modell. Mutiert ``config.stage_overrides`` in-place und
    liefert die Anzahl der verworfenen Einträge.
    """
    from . import llm_routing_seed as _seed

    if not config.stage_overrides:
        return 0
    known_provider_ids = {p.id for p in _seed.LlmProviderRegistry().get_providers()}
    try:
        connections = _seed.ProviderConnectionStore().list_connections()
    except Exception:  # noqa: BLE001 — defensiv, Heuristik darf nicht hart fehlschlagen
        connections = []
    enabled_connections = [c for c in connections if c.enabled]
    enabled_base_urls = {
        c.base_url.rstrip("/").removesuffix("/v1")
        for c in enabled_connections
        if c.base_url
    }
    # ``provider_id`` → welche Connection-Typen sind erlaubt? Wenn ein Ollama-
    # Cloud-Override persistiert wurde, aber keine aktivierte Ollama/Ollama-
    # Cloud-Connection existiert, ist der Override mit Sicherheit stale —
    # unabhängig davon, ob eine ``base_url`` mitgeschrieben wurde.
    _OLLAMA_PROVIDER_IDS = {"ollama", "ollama_cloud", "cloud"}
    has_active_ollama_connection = any(
        getattr(c, "provider_kind", None) in _OLLAMA_PROVIDER_IDS
        for c in enabled_connections
    )
    stale: list[StageId] = []
    for stage_id, override in config.stage_overrides.items():
        if not override.provider_id:
            continue
        if override.provider_id not in known_provider_ids:
            stale.append(stage_id)
            continue
        persisted_base_url = override.provider_options.get("base_url")
        if persisted_base_url and enabled_base_urls:
            normalized = persisted_base_url.rstrip("/").removesuffix("/v1")
            if normalized not in enabled_base_urls:
                stale.append(stage_id)
                continue
        # Kein ``base_url`` (oder keine aktiven Connections zum Abgleich):
        # Provider-Typ-spezifischer Sanity-Check. Wenn der Provider-ID-Typ zu
        # keiner aktivierten Connection passt, ist die Persistierung garantiert
        # aus einer früheren Umgebung (z. B. Ollama-Cloud-Proxy in der Vor-
        # MiniMax-Ära, der später auf eine andere LLM-Backend umgestellt wurde).
        if (
            override.provider_id in _OLLAMA_PROVIDER_IDS
            and not has_active_ollama_connection
        ):
            stale.append(stage_id)
            continue
    for stage_id in stale:
        dropped = config.stage_overrides.pop(stage_id)
        _seed.logger.warning(
            "seed_run_stage_routing: stale stage_override verworfen "
            "(stage=%s, provider_id=%s, base_url=%s) — Provider-Landschaft "
            "hat sich seit der letzten Persistierung geändert; "
            "Workspace-Default wird übernommen",
            stage_id,
            dropped.provider_id,
            dropped.provider_options.get("base_url"),
        )
    return len(stale)


def _apply_workspace_defaults(config: RuntimeLlmRouting) -> None:
    """Übernimmt Workspace-Routing-Defaults in config (mutiert config in-place)."""
    from . import llm_routing_seed as _seed

    try:
        workspace_defaults = _seed.get_workspace_routing_store().load()
    except Exception:  # noqa: BLE001 — Defaults sind "best effort", kein Stopper
        workspace_defaults = None
    if workspace_defaults is not None:
        if workspace_defaults.global_default.model:
            config.global_default = workspace_defaults.global_default
        for ws_stage_id, ws_route in workspace_defaults.stage_overrides.items():
            config.stage_overrides[ws_stage_id] = ws_route


def _apply_override(
    config: RuntimeLlmRouting,
    stage_id: StageId,
    *,
    llm_model_override: Optional[str],
    llm_runtime: Optional[RuntimeLlmConfig],
) -> None:
    """Überlagert config.stage_overrides[stage_id] mit einem expliziten Override,
    falls llm_model_override gesetzt ist oder llm_runtime.enabled ist."""
    from . import llm_routing_seed as _seed

    runtime = llm_runtime or RuntimeLlmConfig()
    route_provider_id = _seed.map_runtime_provider_to_route_provider(runtime.provider)
    if llm_model_override or runtime.enabled:
        provider_options: dict[str, object] = {}
        if runtime.base_url:
            provider_options["base_url"] = runtime.base_url
        # Wenn der Request "default" als Provider schickt, mappt das Provider-ID-Dict
        # auf None. ResolvedRoute.provider_id ist Pflichtfeld; deshalb auf den
        # global_default des Runs zurückfallen statt None zu persistieren.
        effective_provider_id = route_provider_id or config.global_default.provider_id
        effective_model = llm_model_override or config.global_default.model
        # Issue #1284 Codex-Finding: dieser Legacy-Override-Pfad (z. B.
        # ``llm_provider={"provider": "custom_openai", "base_url": "https://
        # api.anthropic.com"}``) laeuft NIE ueber eine ProviderConnection —
        # weder ``_resolve_selected_connection`` noch
        # ``resolve_profile_connection`` sehen ihn. Fuer OASIS-Simulationen
        # geht die Route zudem direkt in ``build_route_subprocess_env``, ohne
        # je einen ``LLMClient`` (und damit den dortigen Transport-Guard) zu
        # durchlaufen. Zentrale ``detect_provider``-Erkennung, keine zweite
        # Heuristik.
        if _seed.detect_provider(runtime.base_url, effective_model, mode="http") == "anthropic":
            raise ValueError(ANTHROPIC_CHAT_TRANSPORT_UNSUPPORTED)
        config.stage_overrides[stage_id] = StageLLMRoute(
            provider_id=effective_provider_id,
            model=effective_model,
            provider_options=provider_options,
        )


def build_runtime_llm_config(route: ResolvedRoute, api_key: Optional[str]) -> RuntimeLlmConfig:
    """Bridge a resolved route back into the legacy RuntimeLlmConfig contract."""
    from . import llm_routing_seed as _seed

    provider = _seed._ROUTE_TO_RUNTIME_PROVIDER.get(route.provider_id, "custom_openai")
    return RuntimeLlmConfig(
        provider=provider,
        api_key=api_key,
        base_url=route.base_url_sanitized,
    )


def demo_mode_enabled() -> bool:
    """``AGORA_DEMO_MODE`` gate for the public demo instance (Finding H1/M1).

    Delegates to :func:`app.config.is_demo_mode` so the startup guard and the
    request-time gates can never disagree on the same env value.
    """
    from ..config import is_demo_mode

    return is_demo_mode()


def workspace_credential_metadata() -> dict[str, str]:
    """Persist this run's credential scope — operator or workspace — before
    work leaves the request.

    Finding H1 (Security-Review 2026-09-26, #1688): an *absent*
    ``credential_scope`` used to mean "operator" implicitly, indistinguishable
    from a run creation path that simply forgot to attach it. Persisting
    ``"operator"`` explicitly here lets :func:`workspace_credential_id_for_run`
    tell "deliberately operator-scoped" apart from "no scope was ever
    recorded" and default-deny the latter on a demo instance instead of
    silently granting operator credentials.
    """
    from . import llm_routing_seed as _seed

    if not _seed.has_request_context():
        return {}
    from ..security.principal_context import current_principal

    principal = current_principal()
    if principal is None or principal.auth_type != AuthType.JWT:
        return {"credential_scope": "operator"}
    return {
        "credential_scope": "workspace",
        "credential_workspace_id": str(principal.workspace_id),
    }


class _RunCredentialScope(NamedTuple):
    """Resolved ``credential_scope`` of a run — ``explicit`` distinguishes a
    deliberately recorded scope (operator or workspace) from a run whose
    creation path never attached one (Finding H1)."""

    workspace_id: UUID | None
    explicit: bool


_UNSCOPED = _RunCredentialScope(None, False)


def _workspace_id_from_run_metadata(metadata: Mapping[str, object]) -> _RunCredentialScope:
    scope = metadata.get("credential_scope")
    raw_id = metadata.get("credential_workspace_id")
    if scope == "workspace":
        if not isinstance(raw_id, str):
            raise ValueError("Workspace credential scope has no workspace ID")
        try:
            return _RunCredentialScope(UUID(raw_id), True)
        except ValueError as exc:
            raise ValueError("Invalid workspace credential scope") from exc
    if scope == "operator":
        if raw_id is not None:
            raise ValueError("Invalid workspace credential scope")
        return _RunCredentialScope(None, True)
    if scope is not None or raw_id is not None:
        raise ValueError("Invalid workspace credential scope")
    return _UNSCOPED


def _assert_run_workspace_owner(run_id: str, workspace_id: UUID, message: str) -> None:
    from ..infrastructure.postgres.workspace_scope import REFERENCE_OWN, reference_state

    if reference_state("run_id", run_id, workspace_id) != REFERENCE_OWN:
        raise ValueError(message)


def _persisted_workspace_for_run(run_id: str | None) -> tuple[bool, _RunCredentialScope]:
    from . import llm_routing_seed as _seed

    if not run_id:
        return False, _UNSCOPED
    from ..repositories.run_repository import get_run_repository
    from .run_registry import RunRegistry

    record = get_run_repository(registry_dir=RunRegistry.REGISTRY_DIR).get(run_id)
    if record is None:
        return False, _UNSCOPED
    scope = _seed._workspace_id_from_run_metadata(record.to_manifest().get("metadata") or {})
    if scope.workspace_id is not None:
        _seed._assert_run_workspace_owner(
            run_id, scope.workspace_id, "Run workspace credential scope does not match persisted owner"
        )
    return True, scope


def _request_workspace_for_run(
    run_id: str | None, run_exists: bool, persisted: _RunCredentialScope
) -> _RunCredentialScope:
    from . import llm_routing_seed as _seed

    if not _seed.has_request_context():
        return persisted
    from ..security.principal_context import current_principal

    principal = current_principal()
    if principal is None or principal.auth_type != AuthType.JWT:
        # A live request without a JWT principal is an operator/legacy
        # request (master token or open/no-auth mode) — an explicit signal,
        # not a missing one.
        return _RunCredentialScope(persisted.workspace_id, True)
    if run_id and not run_exists:
        raise ValueError("Run credential scope cannot be validated")
    if persisted.workspace_id is not None and persisted.workspace_id != principal.workspace_id:
        raise ValueError("Run workspace credential scope does not match principal")
    if run_id and run_exists:
        _seed._assert_run_workspace_owner(
            run_id, principal.workspace_id, "Run does not belong to principal workspace"
        )
    return _RunCredentialScope(principal.workspace_id, True)


def workspace_credential_id_for_run(run_id: str | None) -> UUID | None:
    """Return a JWT run's validated workspace, including in background jobs.

    Finding H1: a bound context (:func:`workspace_credential_context_for_run`,
    used by background job threads) is now consulted regardless of whether
    ``run_id`` is given — the previous code only checked it when ``run_id``
    was ``None``, so a background job that (correctly) passed its own
    ``run_id`` through never saw its own bound scope and could fail open to
    ``None`` (operator) whenever the persisted/request lookup came up empty.
    A resolved scope that contradicts the bound one raises. When neither the
    bound context nor the persisted/request lookup ever recorded an explicit
    scope, this defaults to operator (unchanged legacy behaviour) — unless
    ``AGORA_DEMO_MODE`` is enabled, where a missing scope is default-deny.
    """
    from . import llm_routing_seed as _seed

    bound_raw = _seed._credential_workspace.get()
    bound_is_set = bound_raw is not None
    # Finding H3: an operator job binds ``_OPERATOR_SENTINEL``, not ``None``
    # — the sentinel is what makes ``bound_is_set`` True for an explicitly
    # bound operator scope, distinct from a thread that never bound
    # anything (still the plain ``None`` ContextVar default).
    bound_workspace: Optional[UUID] = (
        None if bound_raw is _seed._OPERATOR_SENTINEL else cast(Optional[UUID], bound_raw)
    )

    if bound_is_set and run_id is None:
        # Fast path, unchanged since before Finding H1: a background job
        # already bound its validated scope for this thread/context — no
        # need to re-derive it from persisted/request state.
        return bound_workspace

    run_exists, persisted = _seed._persisted_workspace_for_run(run_id)
    resolved = _seed._request_workspace_for_run(run_id, run_exists, persisted)

    if bound_is_set:
        # Finding H1: this branch (``run_id`` given) previously never
        # consulted the bound value at all — a background job that
        # (correctly) passed its own ``run_id`` through could fail open to
        # ``None`` (operator) whenever the persisted/request lookup came up
        # empty. A resolved scope that contradicts the bound one raises
        # instead of silently overriding it.
        if resolved.workspace_id is not None and resolved.workspace_id != bound_workspace:
            raise ValueError(
                "Bound workspace credential scope does not match resolved run workspace"
            )
        return bound_workspace

    if resolved.workspace_id is None and not resolved.explicit and _seed.demo_mode_enabled():
        raise ValueError(
            "Run has no persisted credential scope — refusing the implicit "
            "operator fallback on a demo instance"
        )
    return resolved.workspace_id


@contextmanager
def operator_credential_context() -> Iterator[None]:
    """Bind the explicit operator scope for process-level work without a run.

    Used by the startup embedding probe: it is operator work by definition
    (operator endpoint, operator key) and has no run whose persisted scope
    could be resolved. Without this binding a demo instance refuses the
    implicit operator fallback and the backend never starts.
    """
    from . import llm_routing_seed as _seed

    token = _seed._credential_workspace.set(_seed._OPERATOR_SENTINEL)
    try:
        yield
    finally:
        _seed._credential_workspace.reset(token)


@contextmanager
def workspace_credential_context_for_run(run_id: str) -> Iterator[UUID | None]:
    """Bind a persisted run's validated credential scope to its job thread."""
    from . import llm_routing_seed as _seed

    workspace_id = _seed.workspace_credential_id_for_run(run_id)
    token = _seed._credential_workspace.set(
        workspace_id if workspace_id is not None else _seed._OPERATOR_SENTINEL
    )
    try:
        yield workspace_id
    finally:
        _seed._credential_workspace.reset(token)


def validate_workspace_route(route: ResolvedRoute) -> None:
    """Prevent a tenant credential from being sent to an arbitrary endpoint.

    Finding M3 (Security-Review 2026-09-26, #1688): a workspace key may only
    reach a connection whose ``base_url`` is still the provider's registry
    default — the same gate ``workspaces.py::list_workspace_available_models``
    already applies when it surfaces routable connections. Without it, an
    operator-edited (or -compromised) custom ``base_url`` on an otherwise
    ordinary ``api_key`` connection would exfiltrate every workspace's key
    that routes through it to an arbitrary endpoint.
    """
    from . import llm_routing_seed as _seed

    connection = next(
        (c for c in _seed.ProviderConnectionStore().list_connections() if c.id == route.provider_id),
        None,
    )
    if (
        connection is None
        or not connection.enabled
        or connection.transport != "http"
        or connection.auth_mode != "api_key"
    ):
        raise ValueError("Workspace provider route is unavailable")
    definition = _seed.LlmProviderRegistry.connection_definition(connection.provider_kind)
    if (
        definition is None
        or definition.default_base_url is None
        or connection.base_url != definition.default_base_url
    ):
        raise ValueError("Workspace provider route endpoint does not match connection")
    expected_url = _seed.canonical_connection_base_url(connection)
    actual_url = route.base_url_sanitized
    if not expected_url or _seed.normalize_endpoint_url(actual_url) != _seed.normalize_endpoint_url(expected_url):
        raise ValueError("Workspace provider route endpoint does not match connection")


def store_base_url_for_provider(provider_id: Optional[str]) -> Optional[str]:
    """Liefert die im Store gepflegte Base-URL einer aktivierten Connection.

    ``LlmProviderRegistry.get_providers()`` ist laut eigenem Docstring eine
    Quelle *statischer, secret-freier* Metadaten: sie liefert ausschliesslich
    ``definition.default_base_url`` und liest den Store nie. Wer in der UI unter
    "LLM-Anbieter" eine abweichende Base-URL pflegt, schreibt sie damit zwar
    nach ``provider_connections.json`` — fuer den OASIS-Subprozess blieb sie
    aber wirkungslos, weil ``build_route_subprocess_env`` direkt auf den
    hartkodierten Default zurueckfiel. Ergebnis: eine in der UI korrigierte URL
    aendert am Simulationslauf nichts, das Eingabefeld wirkt kaputt.

    Diese Funktion schliesst genau diese Luecke und laesst die Registry
    unangetastet. ``canonical_connection_base_url`` faellt selbst auf den
    Registry-Default zurueck, wenn die Connection keine eigene URL traegt — die
    Praezedenz bleibt also Store > Default.
    """
    from . import llm_routing_seed as _seed

    if not provider_id:
        return None
    try:
        connections = _seed.ProviderConnectionStore().list_connections()
    except Exception:  # noqa: BLE001 — ein Store-Ausfall darf keinen Run kippen
        _seed.logger.warning(
            "store_base_url_for_provider: Store nicht lesbar für provider_id=%s "
            "— Registry-Default gilt",
            provider_id,
        )
        return None
    match = next(
        (
            c
            for c in connections
            if c.enabled
            and (getattr(c, "provider_kind", None) == provider_id or c.id == provider_id)
        ),
        None,
    )
    if match is None:
        return None
    return _seed.canonical_connection_base_url(match)
