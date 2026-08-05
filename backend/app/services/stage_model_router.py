"""
Stage Model Router.
Resolve(run_id, stage_id, runtime_cfg) -> ResolvedRoute.

Slice 7.3.3 (Teil 11): der produktive Router delegiert die Auswahl an den
kanonischen ``resolve_ai_route`` (Stage > Run > Projekt > Workspace >
Provider-Fallback) statt an das frühere ``stage_overrides or global_default``.
Capability-Mismatches bleiben hart (Fehler statt stillem Fallback); der
kanonische Snapshot trägt die echte Quelle plus Capabilities/Fallback-Grund.
"""

from collections.abc import Collection
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from ..contracts.ai_provider_contract import AiRoute, ai_route_from_stage_route
from ..contracts.llm_routing_contract import (
    RuntimeLlmRouting,
    ResolvedRoute,
    StageId,
    StageLLMRoute,
)
from .runtime_run_config import RuntimeRunConfig, _detect_default_provider_id
from .secret_resolver import SecretResolver
from .ai_route_audit import AiRouteAudit
from .ai_route_resolver import resolve_ai_route
from .llm_routing_seed import store_base_url_for_provider
from ..utils.logger import get_logger

logger = get_logger("agora.stage_model_router")


class StageModelRouter:
    """Resolves the LLM route for a given stage."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.config_service = RuntimeRunConfig(run_id)
        # Kanonischer AiRoute, den ``resolve()`` beim frischen Auflösen
        # berechnet hat — bewahrt die echten Auswahl-Inputs (project_route,
        # workspace_route, required_capabilities, resolved_at) für
        # ``lock_stage()``. Ohne diesen Cache müsste ``lock_stage()`` die
        # kanonische Route neu auflösen und würde dabei die Original-Inputs
        # verlieren (P0: Audit-Snapshot konnte von der ausgeführten Route
        # abweichen). Lebensdauer: genau ein resolve→lock-Fenster pro Stage.
        self._pending_canonical: dict[StageId, AiRoute] = {}

    def resolve(
        self,
        stage_id: StageId,
        runtime_cfg: Optional[RuntimeLlmRouting] = None,
        *,
        required_capabilities: Collection[str] = (),
        project_route: Optional[AiRoute] = None,
        workspace_route: Optional[AiRoute] = None,
    ) -> ResolvedRoute:
        """Resolve route for a stage, using a locked snapshot if it exists.

        Once no snapshot is present the canonical resolver decides between the
        real candidates. ``required_capabilities`` is enforced hard: if the
        winning candidate lacks a required capability the resolver raises
        instead of silently falling through to a weaker candidate.
        """
        # 1. Locked-for-execution snapshots win unconditionally.
        snapshot = self.config_service.load_stage_snapshot(stage_id)
        if snapshot:
            return self._resolved_from_snapshot(stage_id, snapshot)
        canonical_snapshot = self.config_service.load_ai_route_snapshot(stage_id)
        if canonical_snapshot is not None:
            return self._resolved_from_snapshot(
                stage_id, canonical_snapshot.model_dump(mode="json")
            )

        # 2. Resolve from runtime config through the canonical resolver.
        cfg = runtime_cfg or self.config_service.load_config()
        canonical = self._resolve_canonical(
            stage_id,
            cfg,
            required_capabilities=required_capabilities,
            resolved_at=datetime.now(timezone.utc),
            project_route=project_route,
            workspace_route=workspace_route,
        )
        # Bewahre den kanonischen AiRoute für das unmittelbar folgende
        # ``lock_stage()`` — die Legacy-``ResolvedRoute`` trägt keine
        # ``source``/``fallback_reason``/``validated_capabilities``, ein
        # späterer Re-Resolve mit leeren Inputs würde diese verlieren.
        self._pending_canonical[stage_id] = canonical
        return self._resolved_route_from_ai_route(stage_id, canonical, cfg.routing_version)

    def _resolve_canonical(
        self,
        stage_id: StageId,
        cfg: RuntimeLlmRouting,
        *,
        required_capabilities: Collection[str],
        resolved_at: datetime,
        project_route: Optional[AiRoute] = None,
        workspace_route: Optional[AiRoute] = None,
    ) -> AiRoute:
        """Build real candidates and delegate to the canonical resolver.

        Priority order Stage > Run > Projekt > Workspace > Provider-Fallback.
        The per-run ``RuntimeLlmRouting`` supplies the Stage- and Run-level
        candidates. Project/Workspace candidates are injected by the caller —
        there is no distinct project-level routing store yet, and the workspace
        default is already merged into the per-run config at seed time
        (``llm_routing_seed``). The provider fallback is synthesized from the
        server config so a run without any configured route still resolves
        (or, if the server config is empty, the resolver raises).
        """
        stage_candidate = self._candidate(
            cfg.stage_overrides.get(stage_id), cfg.routing_version
        )
        run_candidate = self._candidate(cfg.global_default, cfg.routing_version)
        provider_fallback = self._provider_fallback_candidate(cfg.routing_version)
        resolved = resolve_ai_route(
            stage_override=stage_candidate,
            run_override=run_candidate,
            project_route=project_route,
            workspace_route=workspace_route,
            provider_fallback=provider_fallback,
            required_capabilities=required_capabilities,
            resolved_at=resolved_at,
        )
        # The resolved route always describes *this* stage, even when the
        # winning candidate carried no stage of its own.
        return resolved.model_copy(update={"stage": stage_id})

    @staticmethod
    def _candidate(
        route: Optional[StageLLMRoute], routing_version: int
    ) -> Optional[AiRoute]:
        """Project a per-run ``StageLLMRoute`` onto a canonical candidate.

        Returns ``None`` when the route carries no usable model, so the level
        is treated as absent by the resolver (no empty-model candidates).
        """
        if route is None or not route.model:
            return None
        try:
            ai = ai_route_from_stage_route(route)
        except ValueError:
            return None
        return ai.model_copy(update={"routing_version": routing_version})

    @staticmethod
    def _provider_fallback_candidate(routing_version: int) -> Optional[AiRoute]:
        """Last-resort candidate synthesized from the server config."""
        from ..config import Config

        model = Config.LLM_MODEL_NAME
        if not model:
            return None
        base_url = Config.LLM_BASE_URL
        common = {
            "provider_connection_id": _detect_default_provider_id(base_url, model),
            "model_id": model,
            "source": "provider_fallback",
            "fallback_reason": "No configured route was available",
            "routing_version": routing_version,
        }
        if base_url:
            try:
                return AiRoute(provider_options={"base_url": base_url}, **common)
            except ValidationError:
                # Non-public base URL cannot live in the secret-free options —
                # keep the fallback usable without it.
                logger.debug("provider fallback base_url dropped from options")
        return AiRoute(**common)

    def _resolved_route_from_ai_route(
        self, stage_id: StageId, route: AiRoute, routing_version: int
    ) -> ResolvedRoute:
        """Adapt a resolved canonical ``AiRoute`` to the legacy ResolvedRoute."""
        options = dict(route.provider_options)
        legacy = options.pop("__legacy_stage_route__", None) or {}
        base_url = options.get("base_url")
        if not base_url and route.provider_connection_id:
            # workspace_llm_routing.json persistiert pro Route nur
            # provider_id + model — keine base_url (die gehoert zur
            # Connection, nicht zur Route). Ohne diese Auflösung blieb
            # ``ResolvedRoute.base_url_sanitized`` None; die zweite
            # Verteidigungslinie in ``prepare_service._resolve_llm_connection``
            # liess das durch, und ``OasisProfileGenerator`` fuellte die
            # Luecke mit ``Config.LLM_BASE_URL`` (.env-Endpoint), waehrend
            # Modell und Key aus der Route stammten (#1104). Store-Lookup
            # analog zum bereits existierenden OASIS-Subprozess-Env-Pfad in
            # ``llm_routing_seed.build_route_subprocess_env``.
            base_url = store_base_url_for_provider(route.provider_connection_id)
        provider_id = route.provider_connection_id or _detect_default_provider_id(
            base_url, route.model_id
        )
        started_at = (
            route.resolved_at.isoformat()
            if route.resolved_at
            else datetime.now(timezone.utc).isoformat()
        )
        return ResolvedRoute(
            stage=route.stage or stage_id,
            provider_id=provider_id,
            model=route.model_id or "",
            base_url_sanitized=SecretResolver().sanitize_url(base_url),
            reasoning_effort=legacy.get("reasoning_effort") or "none",
            routing_version=routing_version,
            provider_options=options,
            started_at=started_at,
        )

    def lock_stage(self, stage_id: StageId, resolved_route: ResolvedRoute) -> ResolvedRoute:
        """Lock the route for a stage by persisting the snapshot.

        The canonical snapshot for the audit is the AiRoute that ``resolve()``
        actually computed for this stage — never a re-resolved copy. A
        re-resolve would lose the original selection inputs
        (``required_capabilities``, ``project_route``, ``workspace_route``,
        the real ``resolved_at``) and could record a route whose
        ``source``/``model_id`` differ from what is executed and persisted
        in the stage snapshot (P0: Audit-Log / Snapshot-Wiederaufnahme
        divergence). If no fresh canonical is pending (snapshot-hit path,
        resume, or external caller without prior ``resolve()``), fall back
        to the already-persisted canonical snapshot; only as a last resort
        re-resolve with the same empty inputs the caller would have used.
        """
        winner = self.config_service.save_stage_snapshot(
            stage_id, resolved_route.model_dump(mode="json")
        )
        stored = ResolvedRoute.model_validate(winner)
        canonical_route = self._pending_canonical.pop(stage_id, None)
        if canonical_route is None:
            # Kein frischer Resolve vorausgegangen: die bereits persistierte
            # kanonische Route wiederverwenden (stimmt garantiert mit der
            # ausgeführten überein), statt mit leeren Inputs neu aufzulösen.
            existing = self.config_service.load_ai_route_snapshot(stage_id)
            if existing is not None:
                canonical_route = existing
            else:
                config = self.config_service.load_config()
                canonical_route = self._resolve_canonical(
                    stage_id,
                    config,
                    required_capabilities=(),
                    resolved_at=self._parse_started_at(stored.started_at),
                )
        canonical = self.config_service.save_ai_route_snapshot(stage_id, canonical_route)
        AiRouteAudit(self.run_id).record_routing_resolved(stage_id, canonical)
        return self._resolved_from_snapshot(stage_id, winner)

    @staticmethod
    def _parse_started_at(value: Optional[str]) -> datetime:
        if value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    def _resolved_from_snapshot(
        self, stage_id: StageId, snapshot: dict[str, object]
    ) -> ResolvedRoute:
        try:
            return ResolvedRoute.model_validate(snapshot)
        except ValidationError:
            route = AiRoute.model_validate(snapshot)
            options = dict(route.provider_options)
            legacy_options = options.pop("__legacy_stage_route__", None) or {}
            base_url = options.get("base_url")
            provider_id = route.provider_connection_id or _detect_default_provider_id(
                base_url, route.model_id
            )
            return ResolvedRoute(
                stage=route.stage or stage_id,
                provider_id=provider_id,
                model=route.model_id or "",
                base_url_sanitized=SecretResolver().sanitize_url(base_url),
                reasoning_effort=legacy_options.get("reasoning_effort") or "none",
                routing_version=route.routing_version,
                provider_options=options,
                started_at=(
                    route.resolved_at.isoformat() if route.resolved_at else None
                ),
            )
