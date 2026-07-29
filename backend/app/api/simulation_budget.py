"""
Budget- und Preflight-Routen für Simulationen (Issue #764).

POST /api/simulation/preflight-estimate — ehrlich gekennzeichnete Schätzung
von Tokens, Kosten und Laufzeit vor dem Run-Start.
"""
from __future__ import annotations

from flask import request

from . import simulation_bp
from ..contracts.run_budget_contract import PreflightModelRef
from ..services.pricing_registry import get_pricing_registry
from ..services.run_budget_preflight import estimate_run
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.validation import validate_simulation_id
from .simulation_common import get_artifact_store, logger


def _quote_cost_status(quote_status: str) -> str:
    """Pricing-Status auf Contract-CostStatus mappen (Schätzung bleibt Schätzung)."""
    return {"priced": "estimated", "free": "free"}.get(quote_status, "unknown")


def _resolve_preflight_models(data: dict, config: dict | None) -> list[PreflightModelRef]:
    """Modelle für die Schätzung auflösen: ai_model_ref > simulation_config.

    Liefert [] wenn nichts auflösbar ist — der Schätzservice kennzeichnet
    das ehrlich als unknown statt Modelle zu erfinden.
    """
    pricing = get_pricing_registry()

    raw_ref = data.get("ai_model_ref")
    if raw_ref is not None:

        from ..contracts.ai_provider_contract import AiModelRef

        ref = AiModelRef.model_validate(raw_ref)  # ValidationError → 400 am Endpoint
        provider_kind = "unknown"
        base_url = None
        try:
            from ..services.provider_connection_store import ProviderConnectionStore

            connections = ProviderConnectionStore().list_connections()
            connection = next(
                (c for c in connections if c.id == ref.provider_connection_id), None
            )
            if connection is not None:
                provider_kind = connection.provider_kind
                base_url = connection.base_url
        except Exception as exc:  # noqa: BLE001 — Auflösung ist best-effort
            logger.warning("preflight: connection lookup failed: %s", exc)
        quote = pricing.resolve(provider_kind, ref.model_id, base_url)
        return [
            PreflightModelRef(
                stage="simulation_rounds",
                provider_id=provider_kind,
                model_id=ref.model_id,
                base_url_sanitized=base_url,
                cost_status=_quote_cost_status(quote.status),  # type: ignore[arg-type]
            )
        ]

    if config and config.get("llm_model"):
        from ..llm.providers.registry import detect_provider

        model = str(config["llm_model"])
        base_url = config.get("llm_base_url")
        provider = detect_provider(base_url, model)
        quote = pricing.resolve(provider, model, base_url)
        return [
            PreflightModelRef(
                stage="simulation_rounds",
                provider_id=provider,
                model_id=model,
                base_url_sanitized=base_url,
                cost_status=_quote_cost_status(quote.status),  # type: ignore[arg-type]
            )
        ]
    return []


@simulation_bp.route("/preflight-estimate", methods=["POST"])
@handle_api_errors(logger=logger, log_prefix="Failed to compute preflight estimate")
def preflight_estimate():
    """Preflight-Schätzung für einen geplanten Simulations-Run.

    Body:
      simulation_id (optional): liest Agenten/Runden/Modell aus der
        prepared simulation_config.json, wenn nicht explizit überschrieben.
      num_agents / max_rounds (optional): explizite Überschreibung.
      ai_model_ref (optional): explizite Modellwahl (AiModelRef).

    Antwort: PreflightEstimate (Contract, schema_version=1). Alle Werte sind
    Schätzbereiche; unbekannte Kosten werden als unknown ausgewiesen.
    """
    from pydantic import ValidationError

    # Issue #764 (Codex P1): silent=True, damit fehlendes/fehlerhaftes
    # JSON weiter unten durch die bestehende Validation fliesst (kein 400
    # aus dem Body-Parser, aber dennoch json_error bei strukturellen
    # Problemen).
    data = request.get_json(silent=True) or {}

    simulation_id = data.get("simulation_id")
    config = None
    if simulation_id:
        if not validate_simulation_id(simulation_id):
            return json_error(ApiErrorCode.INVALID_ID, message="Invalid simulation_id format")
        config = get_artifact_store().read_json(
            simulation_id, "simulation_config", default=None
        )

    num_agents = data.get("num_agents")
    if num_agents is None and config:
        agent_configs = config.get("agent_configs") or []
        num_agents = len(agent_configs) or None

    max_rounds = data.get("max_rounds")
    if max_rounds is None and config:
        time_config = config.get("time_config") or {}
        try:
            hours = int(time_config.get("total_simulation_hours", 72))
            minutes_per_round = int(time_config.get("minutes_per_round", 30)) or 30
        except (TypeError, ValueError):
            # Issue #764 (Codex P1): kaputte time_config-Werte duerfen
            # nicht in einem 500 enden — bestehende Validation greift
            # unten und liefert 400 mit klarer Meldung.
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message="time_config enthaelt ungueltige Werte (total_simulation_hours/minutes_per_round)",
            )
        max_rounds = (hours * 60) // minutes_per_round

    try:
        num_agents = int(num_agents)
        max_rounds = int(max_rounds)
    except (TypeError, ValueError):
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=(
                "num_agents und max_rounds werden benötigt (direkt oder via "
                "simulation_id mit vorbereiteter simulation_config)"
            ),
        )
    if num_agents < 0 or max_rounds < 0:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="num_agents und max_rounds müssen >= 0 sein",
        )

    try:
        models = _resolve_preflight_models(data, config)
    except ValidationError:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="ai_model_ref ist ungültig",
        )

    estimate = estimate_run(
        num_agents=num_agents,
        max_rounds=max_rounds,
        models=models,
    )
    return json_success(estimate.model_dump(mode="json"))
