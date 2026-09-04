"""Helpers to seed per-run LLM routing from the legacy request overrides.

Bridges the existing ``llm_model`` / ``llm_provider`` request contract to the
new ``RuntimeLlmRouting`` persistence model so runtime snapshots and stage locks
can be used without a flag day across all API surfaces.
"""

from __future__ import annotations

import os
from typing import Optional

from ..contracts.ai_provider_contract import AiModelRef, ProviderConnection
from ..contracts.llm_routing_contract import ResolvedRoute, RuntimeLlmRouting, StageId, StageLLMRoute
from ..contracts.provider_types import PROVIDER_CODEX_CLI
from ..llm.providers.registry import detect_provider
from .llm_provider_registry import LlmProviderRegistry
from .llm_provider_secrets_store import get_llm_provider_secrets_store
from .llm_profiles_store import get_llm_profiles_store
from .llm_runtime import RuntimeLlmConfig
from .profile_connection_resolver import canonical_connection_base_url, resolve_profile_connection
from .provider_connection_store import ProviderConnectionStore
from .provider_connections.service import ProviderConnectionService
from .runtime_run_config import RuntimeRunConfig
from .secret_resolver import SecretResolver, get_bound_store_api_key
from .workspace_routing_store import get_workspace_routing_store
from ..utils.logger import get_logger

logger = get_logger("agora.llm_routing_seed")

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
    # ``.env``-Fallback zu erkennen.
    PROVIDER_CODEX_CLI: PROVIDER_CODEX_CLI,
}


def map_runtime_provider_to_route_provider(provider: str) -> Optional[str]:
    return _PROVIDER_ID_MAP.get((provider or "default").strip().lower())


def _resolve_selected_connection(connection_id: str) -> ProviderConnection:
    """Resolve an explicitly selected ProviderConnection by id.

    Raises ``ValueError`` when the connection is unknown or disabled, so the
    caller can surface an HTTP 400/422 instead of silently falling back to a
    different route.
    """
    match = next(
        (c for c in ProviderConnectionStore().list_connections() if c.id == connection_id),
        None,
    )
    if match is None:
        raise ValueError(f"ProviderConnection {connection_id!r} nicht gefunden")
    if not match.enabled:
        raise ValueError(f"ProviderConnection {connection_id!r} ist deaktiviert")
    return match


def _verify_selected_model(connection: ProviderConnection, model_id: str) -> None:
    """Prüft per Live-Discovery, dass ``model_id`` tatsächlich zum Modell-Katalog
    von ``connection`` gehört (Issue #819).

    Nutzt ausschließlich den bestehenden Model-Discovery-Pfad
    (``ProviderConnectionService.probe``, denselben, den
    ``GET /provider-connections/<id>/models`` produktiv verwendet) — kein neuer
    Katalog, keine lokale Provider-Detection-Heuristik neben der Registry.

    Unterscheidet zwei Fehlerfälle bewusst mit unterschiedlicher Meldung:
    schlägt die Discovery selbst fehl (Provider nicht erreichbar, ungültige
    Credentials, Rate-Limit), ist das kein Beleg für einen Model-Mismatch —
    eine Meldung "Modell gehört nicht zur Connection" wäre hier irreführend.
    """
    service = ProviderConnectionService(
        store=ProviderConnectionStore(),
        secrets_store=get_llm_provider_secrets_store(),
    )
    try:
        result = service.probe(connection)
    except Exception as exc:  # noqa: BLE001 — Providerfehler dürfen keine Secrets propagieren
        # Bewusst ohne str(exc): der Provider-Fehlertext kann Credentials
        # tragen. Typ + connection.id reichen, um einen Discovery-Ausfall im
        # Betrieb von einem echten Model-Mismatch zu unterscheiden.
        logger.warning(
            "Model-Discovery fehlgeschlagen [connection_id=%s, error_type=%s]",
            connection.id,
            type(exc).__name__,
        )
        raise ValueError(
            f"Modell-Katalog für ProviderConnection {connection.id!r} derzeit "
            f"nicht abrufbar ({type(exc).__name__})"
        ) from None
    if result.status != "available":
        raise ValueError(
            f"Modell-Katalog für ProviderConnection {connection.id!r} derzeit "
            f"nicht abrufbar ({result.status})"
        )
    known_model_ids = {model.model_id for model in result.models}
    if model_id not in known_model_ids:
        raise ValueError(
            f"Modell {model_id!r} gehört nicht zur ProviderConnection {connection.id!r}"
        )


def _assert_connection_secret_bound(connection: ProviderConnection) -> None:
    """Prüft die Secret-Bindung, ohne Route-Options zu konfigurieren.

    Validierungspfade (Prevalidate) brauchen nur die Ablehnung ungebundener
    Cloud-Connections — nicht die Options. Der verworfene Dict-Aufruf sah nach
    totem Code aus; dieser Wrapper macht die Absicht explizit.
    """
    _bind_connection_secret(connection, {})


def _bind_connection_secret(
    connection: ProviderConnection, options: dict[str, object]
) -> None:
    """Bindet das Secret einer api_key-Connection strikt an die Route-Options.

    Cloud-Connections (``auth_mode="api_key"``) ohne gebundenes ``secret_ref``
    werden hart abgelehnt — kein ``.env``-/Server-Key-Fallback, sonst wiche die
    Secret-Quelle von der gewählten Route ab (Issue #817). Lokale No-Auth-
    Connections (``auth_mode="none"``) laufen hier nicht durch und bleiben
    unberührt. Gemeinsame SSoT für den ``ai_model_ref``- und den
    ``llm_profile_id``-Routing-Pfad, damit keiner der beiden die Bindung umgeht.
    """
    if connection.auth_mode != "api_key":
        return
    if not connection.secret_ref:
        raise ValueError(
            f"ProviderConnection {connection.id!r}: Cloud-Connection ohne "
            "gebundenes Secret — kein .env-Fallback für Report-Routen"
        )
    options["secret_ref"] = connection.secret_ref
    options["connection_only"] = True


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
    if ai_model_ref.source != "fallback":
        return ai_model_ref.fallback_reason
    reason = (ai_model_ref.fallback_reason or "").strip()
    return reason or _UNSPECIFIED_FALLBACK_REASON


def prevalidate_ai_model_ref(ai_model_ref: AiModelRef) -> ProviderConnection:
    """Günstige Vorab-Prüfung einer ``ai_model_ref`` ohne Live-Discovery.

    Löst die Connection auf und verifiziert die Secret-Bindung. Prepare- und
    Simulation-Start-Endpunkte nutzen diese Variante bewusst vor der
    Run-Erzeugung, ohne einen zusätzlichen Provider-Probe auszulösen.
    """
    connection = _resolve_selected_connection(ai_model_ref.provider_connection_id)
    _assert_connection_secret_bound(connection)
    return connection


def prevalidate_ai_model_ref_with_discovery(
    ai_model_ref: AiModelRef,
) -> ProviderConnection:
    """Vollständige AiModelRef-Prüfung inklusive bestehender Model-Discovery."""
    connection = prevalidate_ai_model_ref(ai_model_ref)
    _verify_selected_model(connection, ai_model_ref.model_id)
    return connection


def _apply_workspace_defaults(config: RuntimeLlmRouting) -> None:
    """Übernimmt Workspace-Routing-Defaults in config (mutiert config in-place)."""
    try:
        workspace_defaults = get_workspace_routing_store().load()
    except Exception:  # noqa: BLE001 — Defaults sind "best effort", kein Stopper
        workspace_defaults = None
    if workspace_defaults is not None:
        if workspace_defaults.global_default.model:
            config.global_default = workspace_defaults.global_default
        for ws_stage_id, ws_route in workspace_defaults.stage_overrides.items():
            config.stage_overrides[ws_stage_id] = ws_route


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
    if not config.stage_overrides:
        return 0
    known_provider_ids = {p.id for p in LlmProviderRegistry().get_providers()}
    try:
        connections = ProviderConnectionStore().list_connections()
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
        logger.warning(
            "seed_run_stage_routing: stale stage_override verworfen "
            "(stage=%s, provider_id=%s, base_url=%s) — Provider-Landschaft "
            "hat sich seit der letzten Persistierung geändert; "
            "Workspace-Default wird übernommen",
            stage_id,
            dropped.provider_id,
            dropped.provider_options.get("base_url"),
        )
    return len(stale)


def _apply_override(
    config: RuntimeLlmRouting,
    stage_id: StageId,
    *,
    llm_model_override: Optional[str],
    llm_runtime: Optional[RuntimeLlmConfig],
) -> None:
    """Überlagert config.stage_overrides[stage_id] mit einem expliziten Override,
    falls llm_model_override gesetzt ist oder llm_runtime.enabled ist."""
    runtime = llm_runtime or RuntimeLlmConfig()
    route_provider_id = map_runtime_provider_to_route_provider(runtime.provider)
    if llm_model_override or runtime.enabled:
        provider_options: dict[str, object] = {}
        if runtime.base_url:
            provider_options["base_url"] = runtime.base_url
        # Wenn der Request "default" als Provider schickt, mappt das Provider-ID-Dict
        # auf None. ResolvedRoute.provider_id ist Pflichtfeld; deshalb auf den
        # global_default des Runs zurückfallen statt None zu persistieren.
        effective_provider_id = route_provider_id or config.global_default.provider_id
        effective_model = llm_model_override or config.global_default.model
        config.stage_overrides[stage_id] = StageLLMRoute(
            provider_id=effective_provider_id,
            model=effective_model,
            provider_options=provider_options,
        )


def build_preview_stage_route(
    stage_id: StageId,
    *,
    llm_model_override: Optional[str],
    llm_runtime: Optional[RuntimeLlmConfig],
) -> ResolvedRoute:
    """Zustandslose Variante für Preview-Endpoints ohne persistierten Run
    (z. B. /simulation/generate-profiles). Nutzt denselben Workspace-Default-
    und Override-Resolver wie seed_run_stage_routing, schreibt aber nie auf
    Platte und versiegelt keine Stage — sicher für jeden Request."""
    from uuid import uuid4

    from .stage_model_router import StageModelRouter

    config = RuntimeLlmRouting(global_default=StageLLMRoute())
    _apply_workspace_defaults(config)
    _apply_override(config, stage_id, llm_model_override=llm_model_override, llm_runtime=llm_runtime)
    router = StageModelRouter(f"preview-{uuid4().hex}")
    return router.resolve(stage_id, runtime_cfg=config)


def seed_run_stage_routing(
    run_id: str,
    stage_id: StageId,
    *,
    llm_model_override: Optional[str],
    llm_runtime: Optional[RuntimeLlmConfig],
    llm_profile_id: Optional[str] = None,
    ai_model_ref: Optional[AiModelRef] = None,
) -> RuntimeLlmRouting:
    """
    Persist per-run routing for a stage, applying workspace defaults and request-specific overrides.
    
    Parameters:
        run_id (str): Identifier of the run whose routing configuration is updated.
        stage_id (StageId): Identifier of the stage receiving the routing configuration.
        llm_model_override (Optional[str]): Model name to use for the stage.
        llm_runtime (Optional[RuntimeLlmConfig]): Runtime provider settings to apply.
        llm_profile_id (Optional[str]): Identifier of an LLM profile to use for the stage.
    
    Returns:
        RuntimeLlmRouting: The saved per-run routing configuration.
    
    Raises:
        ValueError: If the specified LLM profile or a compatible activated provider connection is unavailable.
    """
    config_service = RuntimeRunConfig(run_id)
    has_existing_config = os.path.exists(config_service.config_path)
    config = config_service.load_config()

    # Bei frischen Runs: Workspace-Defaults als Seed übernehmen. Versiegelte Stages
    # (= bereits in den Per-Run-Snapshots vorhanden) werden NICHT überschrieben.
    if not has_existing_config:
        _apply_workspace_defaults(config)

    # Stale-Override-Prune läuft IMMER — auch bei fresh runs kann er Workspace-
    # Defaults betreffen (z. B. workspace_routing.json aus alter Umgebung mit
    # ``ollama_cloud``-override, der in der neuen Umgebung zu 401/HTML-Antworten
    # führt). Symmetrische Behandlung zu bestehender Config: geprunete Stages
    # fallen auf den aktuellen global_default zurück.
    pruned_count = _prune_stage_overrides(config)
    if pruned_count > 0 and has_existing_config:
        _apply_workspace_defaults(config)
        config.routing_version += 1

    runtime = llm_runtime or RuntimeLlmConfig()

    if ai_model_ref is not None:
        # Höchste Priorität: die vom UI explizit gewählte (Connection, Modell)-Route.
        # Die Connection ist die SSoT für Base-URL und Secret-Bindung — kein
        # ``.env``-Fallback, keine lokale Detection-Heuristik.
        connection = _resolve_selected_connection(ai_model_ref.provider_connection_id)
        _verify_selected_model(connection, ai_model_ref.model_id)
        ref_options: dict[str, object] = {}
        connection_base_url = canonical_connection_base_url(connection)
        if connection_base_url:
            ref_options["base_url"] = connection_base_url
        _bind_connection_secret(connection, ref_options)
        # Issue #901: Herkunft und ggf. Fallback-Grund wandern mit in den
        # Snapshot. Ohne sie schrieb ai_route_from_stage_route beim Auflesen
        # hart source="legacy" — eine bewusste Nutzerwahl war danach von einem
        # Provider-Fallback nicht mehr zu unterscheiden.
        config.stage_overrides[stage_id] = StageLLMRoute(
            provider_id=connection.id,
            model=ai_model_ref.model_id,
            provider_options=ref_options,
            ai_model_ref_source=ai_model_ref.source,
            fallback_reason=_fallback_reason_for(ai_model_ref),
        )
        if has_existing_config:
            config.routing_version += 1
    elif llm_model_override or runtime.enabled:
        _apply_override(
            config,
            stage_id,
            llm_model_override=llm_model_override,
            llm_runtime=llm_runtime,
        )
        if has_existing_config:
            config.routing_version += 1
    elif llm_profile_id:
        profile = get_llm_profiles_store().get(
            llm_profile_id,
            include_api_key=False,
        )
        if profile is None:
            raise ValueError(f"LLM-Profil {llm_profile_id!r} nicht gefunden")
        resolved = resolve_profile_connection(
            profile,
            ProviderConnectionStore().list_connections(),
        )
        if resolved is None:
            raise ValueError(
                f"LLM-Profil {llm_profile_id!r}: keine passende aktivierte "
                "ProviderConnection"
            )
        connection = resolved.connection
        provider_options: dict[str, object] = {"base_url": resolved.base_url}
        # Auth-Semantik der ProviderConnection ist maßgeblich (SSoT): api_key-
        # Connections werden an ihr gebundenes Secret gekoppelt und ohne Secret
        # hart abgelehnt (Issue #817) — identisch zum ai_model_ref-Pfad, damit der
        # Profilpfad die Bindung nicht umgeht. Lokale No-Auth-Connections
        # (auth_mode="none") laufen nicht durch und bleiben auf base_url beschränkt.
        _bind_connection_secret(connection, provider_options)
        config.stage_overrides[stage_id] = StageLLMRoute(
            provider_id=connection.id,
            model=profile.model_name,
            provider_options=provider_options,
        )
        if has_existing_config:
            config.routing_version += 1

    config_service.save_config(config)
    return config


def resolve_route_api_key(route: ResolvedRoute, llm_runtime: Optional[RuntimeLlmConfig] = None) -> Optional[str]:
    """Resolve the API key for a resolved route.
    
    Connection-only routes use their bound secret reference. Other routes use a
    matching request-scoped runtime key when available, then fall back to the
    server-side provider secret.
    
    Parameters:
        route (ResolvedRoute): The resolved route whose API key is needed.
        llm_runtime (Optional[RuntimeLlmConfig]): Request-scoped runtime
            configuration that may provide a matching API key.
    
    Returns:
        Optional[str]: The resolved API key, or None when no key is available.
    """
    if route.provider_options.get("connection_only") is True:
        raw_secret_ref = route.provider_options.get("secret_ref")
        secret_ref = raw_secret_ref if isinstance(raw_secret_ref, str) else ""
        return get_bound_store_api_key(
            secret_ref,
            secrets_store=get_llm_provider_secrets_store(),
        )

    runtime = llm_runtime or RuntimeLlmConfig()
    runtime_provider_id = map_runtime_provider_to_route_provider(runtime.provider)
    if runtime.enabled and runtime.api_key and runtime_provider_id == route.provider_id:
        return runtime.api_key

    registry = LlmProviderRegistry()
    provider = next((p for p in registry.get_providers() if p.id == route.provider_id), None)
    provider_type = provider.type if provider else "openai_compatible"
    return SecretResolver().get_api_key(route.provider_id, provider_type)


def build_runtime_llm_config(route: ResolvedRoute, api_key: Optional[str]) -> RuntimeLlmConfig:
    """Bridge a resolved route back into the legacy RuntimeLlmConfig contract."""
    provider = _ROUTE_TO_RUNTIME_PROVIDER.get(route.provider_id, "custom_openai")
    return RuntimeLlmConfig(
        provider=provider,
        api_key=api_key,
        base_url=route.base_url_sanitized,
    )


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
    if not provider_id:
        return None
    try:
        connections = ProviderConnectionStore().list_connections()
    except Exception:  # noqa: BLE001 — ein Store-Ausfall darf keinen Run kippen
        logger.warning(
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
    return canonical_connection_base_url(match)


def build_route_subprocess_env(
    route: ResolvedRoute,
    api_key: Optional[str],
    run_id: Optional[str] = None,
) -> dict[str, str]:
    """Translate a resolved route into the subprocess environment variables expected by OASIS.
    
    Parameters:
        route (ResolvedRoute): Resolved model, provider, and endpoint configuration.
        api_key (Optional[str]): API key to expose to the subprocess.
        run_id (Optional[str]): Run identifier to expose to the subprocess.
    
    Returns:
        dict[str, str]: Environment variables containing the model, optional run identifier,
            API key aliases, and base URL settings.
    """
    env: dict[str, str] = {"LLM_MODEL_NAME": route.model}
    if run_id:
        env["AGORA_RUN_ID"] = run_id
    provider = next(
        (p for p in LlmProviderRegistry().get_providers() if p.id == route.provider_id),
        None,
    )
    # Base-URL-Auflösung symmetrisch zur Key-Auflösung in
    # ``resolve_route_api_key``: trägt die Route keine base_url — der
    # Legacy-/Workspace-Default-Pfad ohne ``ai_model_ref`` erzeugt Routen mit
    # nackter Registry-``provider_id`` —, gilt der Registry-Endpoint DERSELBEN
    # provider_id. Ohne diese Auflösung bleibt ``LLM_BASE_URL`` hier ungesetzt,
    # der OASIS-Subprozess erbt das stale ``LLM_BASE_URL`` des Backend-Prozesses
    # (``SAFE_ENV_KEYS``-Whitelist in ``process_manager``) und schickt Modell und
    # Provider-Key an einen fremden Endpoint — Root Cause des
    # ``404 model 'MiniMax-M3' not found`` trotz #852. Kein Provider-Fallback:
    # Key und URL stammen aus derselben provider_id.
    #
    # Zwischen Route und Registry-Default liegt seit diesem Fix der Store: die
    # in der UI gepflegte Connection-Base-URL gewinnt gegen den hartkodierten
    # ``default_base_url``. Ohne diese Stufe war das UI-Feld fuer Simulationen
    # wirkungslos — siehe ``store_base_url_for_provider``.
    base_url = (
        route.base_url_sanitized
        or store_base_url_for_provider(route.provider_id)
        or (provider.base_url if provider else None)
    )
    if not base_url and route.provider_id:
        # Weder Route noch Registry kennen einen Endpoint: der Subprozess wird
        # das Parent-``LLM_BASE_URL`` erben (Alt-Verhalten, Standalone-/
        # Dev-Pfad). Sichtbar machen statt still driften.
        logger.warning(
            "build_route_subprocess_env: keine base_url für provider_id=%s "
            "auflösbar — Subprozess erbt LLM_BASE_URL aus dem Backend-Env",
            route.provider_id,
        )
    if api_key:
        env["LLM_API_KEY"] = api_key
        env["OPENAI_API_KEY"] = api_key
        if provider and provider.api_key_ref:
            env[provider.api_key_ref] = api_key
        # CAMELs GeminiModel (OASIS-Subprozess) liest ``GEMINI_API_KEY``; der
        # Google-Provider fuehrt aber ``api_key_ref="GOOGLE_API_KEY"``. Ohne
        # diesen Alias crasht der Subprozess trotz Store-Key mit
        # ``Missing required API keys: GEMINI_API_KEY``. Der Alias haelt den
        # UI-Secrets-Store als Single Source — kein ``.env`` fuer Gemini-Sims.
        if detect_provider(base_url, route.model, mode="oasis") == "google":
            env["GEMINI_API_KEY"] = api_key
    if base_url:
        env["LLM_BASE_URL"] = base_url
        env["OPENAI_BASE_URL"] = base_url
        env["OPENAI_API_BASE"] = base_url
        env["OPENAI_API_BASE_URL"] = base_url
    return env
