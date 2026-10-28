"""
Read-detail and replay helpers for Run registry API.
"""

from __future__ import annotations

from typing import Any, Optional

from ..contracts.ai_provider_contract import AiModelRef
from ..services.simulation_manager import SimulationManager


def _runs_module():
    from . import runs as _runs_mod

    return _runs_mod


def _parse_status_param(args) -> list | None:
    """Parse ?status= query param: supports multi-value and comma-separated."""
    raw_values = args.getlist("status")
    if not raw_values:
        return None
    # Flatten comma-separated entries: ?status=processing,pending
    statuses: list[str] = []
    for v in raw_values:
        for part in v.split(","):
            stripped = part.strip()
            if stripped:
                statuses.append(stripped)
    return statuses if statuses else None


def _build_run_detail(run: dict) -> dict:
    """Attach live metrics to a run manifest before serialisation.

    eta_seconds: taken from run metadata if present (populated by the runner).
    log_tail: last up-to-20 event messages — no extra I/O needed.
    metrics: subset of manifest fields as typed scalars.
    """
    _runs_mod = _runs_module()
    enriched = _runs_mod._attach_summary(run, {}, {})

    # eta_seconds from metadata (runners may store it there).
    metadata = run.get("metadata") or {}
    eta_seconds: int | None = metadata.get("eta_seconds")

    # log_tail: last 20 event messages from the embedded event log.
    events: list[dict] = run.get("events") or []
    log_tail: list[str] | None = None
    if events:
        log_tail = [
            e.get("message") or ""
            for e in events[-20:]
            if e.get("message")
        ] or None

    # metrics: phase, round counter, last_event_at from the manifest/events.
    metrics: dict | None = None
    phase = metadata.get("phase") or metadata.get("stage")
    round_num = metadata.get("round_num") or metadata.get("round")
    last_event_ts = events[-1].get("timestamp") if events else None
    if any(v is not None for v in (phase, round_num, last_event_ts)):
        metrics = {}
        if phase is not None:
            metrics["phase"] = str(phase)
        if round_num is not None:
            metrics["round_num"] = int(round_num)
        if last_event_ts is not None:
            metrics["last_event_at"] = str(last_event_ts)

    enriched["eta_seconds"] = eta_seconds
    enriched["log_tail"] = log_tail
    enriched["metrics"] = metrics

    # Budget & Verbrauch (Issue #764): Budget-Status nur wenn ein Budget
    # gesetzt ist; Verbrauch live aggregiert (Abschluss-Snapshot bevorzugt).
    # Beides bleibt bei Alt-Runs ohne Daten ehrlich None (= unknown im UI).
    try:
        from ..services.run_budget import get_run_budget_status
        from ..services.run_usage_ledger import (
            aggregate_usage,
            load_call_events_cached,
            load_usage_summary,
        )

        budget_status = get_run_budget_status(run["run_id"])
        if budget_status is not None:
            enriched["budget"] = budget_status.model_dump(mode="json")

        usage = load_usage_summary(run["run_id"])
        if usage is None:
            events = load_call_events_cached(run["run_id"])
            if events:
                usage = aggregate_usage(
                    run["run_id"],
                    events=events,
                    started_at=run.get("started_at"),
                    ended_at=run.get("completed_at"),
                )
                # Snapshot-Persist läuft nicht hier: RunRegistry.update_run
                # triggert persist_usage_summary am Lifecycle-Übergang
                # nicht-terminal → terminal (Issue #764 / Codex P2). Ein
                # zweiter Persist hier würde doppelt schreiben und den
                # idempotenten Snapshot-Pfad in run_usage_ledger unnötig
                # aufheizen.
        if usage is not None:
            enriched["usage"] = usage.model_dump(mode="json")
    except Exception:  # noqa: BLE001 — Anreicherung darf den Read nicht brechen
        _runs_mod.logger.warning("budget/usage enrichment failed for run %s", run.get("run_id"), exc_info=True)
    return enriched


def _ai_model_ref_from_manifest_route(stage_route) -> Optional[AiModelRef]:
    """Baut eine ``AiModelRef`` aus der im Manifest erfassten Original-Route
    (Issue #1686 P1) — Grundlage für ein 1:1-Replay, wenn kein expliziter
    Override gesetzt ist.

    Bevorzugt den strikten ``ai_route_snapshot`` (Issue #1274 Punkt 2), weil
    er die kanonische (Connection, Modell)-Referenz trägt; fällt auf die
    Top-Level-Felder von ``StageRoute`` zurück, wenn kein Snapshot vorliegt
    (Alt-Manifest vor #1274). ``None``, wenn beides keine vollständige
    (Connection, Modell)-Kombination liefert — dann bleibt das Verhalten
    unverändert (Workspace-Defaults).
    """
    _runs_mod = _runs_module()
    if stage_route is None:
        return None
    snapshot = stage_route.ai_route_snapshot
    provider_connection_id = (
        snapshot.provider_connection_id if snapshot is not None else None
    ) or stage_route.provider
    model_id = (snapshot.model_id if snapshot is not None else None) or stage_route.model
    if not provider_connection_id or not model_id:
        return None
    return _runs_mod.AiModelRef(provider_connection_id=provider_connection_id, model_id=model_id)


def _replay_simulation_run(run: dict, run_id: str, overrides, manifest):
    """Klont die Original-Simulation per ``create_branch`` und startet sie neu.

    ``create_branch`` liefert bereits Config+Profile-Klon inklusive
    ``llm_model``-Override auf ``READY`` — danach läuft exakt derselbe
    Start-Flow wie ``POST /api/simulation/start`` (Routing auflösen, Route
    sperren, Subprozess starten).

    ``manifest`` ist das bereits geladene ``RunManifest`` des Original-Runs
    (Issue #1274 Punkt 3): ``platform``/``max_rounds``/
    ``enable_graph_memory_update``/``memory_update_graph_id`` werden daraus
    1:1 übernommen statt auf ``platform="parallel"`` und Runner-Defaults
    zurückzufallen — übersteuerbar bleibt ausschließlich die Modell-Route.
    Fehlt ``manifest.simulation`` (Alt-Manifest vor dieser Änderung), ist ein
    ehrlicher 409 der Fehlschlag statt eines stillschweigenden Defaults, der
    als 1:1-Replay ausgegeben würde.

    Rückgabe: entweder ein dict ``{run_id, status}`` (Erfolg) oder eine
    fertige Flask-Error-Response (``json_error(...)``).
    """
    _runs_mod = _runs_module()
    simulation_id = (run.get("linked_ids") or {}).get("simulation_id")
    if not simulation_id:
        return _runs_mod.json_error("Run is missing simulation_id linkage", status=409)

    if manifest.simulation is None:
        return _runs_mod.json_error(
            f"Run {run_id} has a manifest without captured simulation "
            "parameters (platform/max_rounds/graph-memory-update) — it "
            "predates Issue #1274 and cannot be replayed 1:1.",
            status=409,
            code="manifest_missing_simulation_params",
        )

    # #1688 Runde 3: ``/simulation/start`` verweigert JWT-Principals das
    # Graph-Memory-Update (403) — ein Replay eines Runs, der es aktiv hatte,
    # darf diese Sperre nicht umgehen. Ehrlicher 403 statt stillem Abschalten,
    # das den 1:1-Replay-Versprechen widerspraeche.
    principal = _runs_mod.current_principal()
    if (
        manifest.simulation.enable_graph_memory_update
        and principal is not None
        and principal.auth_type == _runs_mod.AuthType.JWT
    ):
        return _runs_mod.json_error(
            _runs_mod.ApiErrorCode.AUTH_FORBIDDEN,
            status=403,
            message="Graph memory update is unavailable for workspace simulations",
        )

    # Finding M1 (#1688): ein Demo-JWT-Run darf die Rundenobergrenze aus
    # ``/simulation/start`` nicht per Replay eines älteren, nicht gedeckelten
    # Runs umgehen. Ein stiller Cap wäre hier zudem ein 1:1-Replay-Versprechen
    # (Manifest-Kommentar oben), das die tatsächlich gefahrenen Runden nicht
    # mehr widerspiegelt — deshalb ehrlicher 400 statt stillem Downgrade.
    #
    # Finding H4 (#1688): der Rueckgabewert wurde bisher verworfen — der
    # tatsaechliche ``start_simulation()``-Aufruf unten benutzte weiterhin
    # ``manifest.simulation.max_rounds`` UNGEDECKELT, der Call oben pruefte
    # nur die ">5"-Grenze. Ein Manifest mit ``max_rounds=None`` (unbegrenzt)
    # loeste GAR KEINE Exception aus und lief unbeschraenkt weiter. Jetzt:
    # den gedeckelten Rueckgabewert tatsaechlich verwenden, und ein
    # ``None``-Manifest in der Demo-Cap-Regime explizit als 400 ablehnen
    # statt es stillschweigend auf 5 zu setzen — das waere kein 1:1-Replay
    # mehr, sondern ein unausgesprochener anderer Lauf.
    try:
        capped_max_rounds, capped_budget_config = _runs_mod.apply_demo_run_limits(
            manifest.simulation.max_rounds, None
        )
    except _runs_mod.DemoLimitExceededError as exc:
        return _runs_mod.json_error(exc.message, status=400, code="demo_limit_exceeded")
    if manifest.simulation.max_rounds is None and capped_max_rounds is not None:
        # apply_demo_run_limits() only ever turns a None max_rounds into a
        # concrete cap while the demo/JWT regime is active (operator runs
        # and non-demo instances return max_rounds unchanged) — so this
        # condition alone identifies "demo cap would silently replace an
        # unbounded manifest", without re-deriving that check here.
        return _runs_mod.json_error(
            f"Run {run_id}'s manifest has no round limit (max_rounds=None) — "
            "a demo instance cannot replay this 1:1 without silently capping "
            "it to a different round count than the original run.",
            status=400,
            code="demo_limit_exceeded",
        )

    manager = _runs_mod.SimulationManager()
    source_state = manager.get_simulation(simulation_id)
    if not source_state:
        return _runs_mod.json_error(f"Simulation does not exist: {simulation_id}", status=404)

    original_stage_route = (manifest.routing.stages or {}).get("simulation_rounds")

    branch_overrides: dict = {}
    llm_model_override = None
    ai_model_ref = overrides.ai_model_ref if overrides is not None else None
    if ai_model_ref is not None:
        # Issue #886: volles AiModelRef durchreichen statt nur model_id —
        # create_branch leitet daraus sowohl config["ai_model_ref"] als auch
        # das Legacy-Anzeigefeld config["llm_model"] ab (siehe
        # branching_service.create_branch). Dieselbe Modell-ID kann auf
        # mehreren Provider-Connections liegen; ohne die Connection-ID wäre
        # der Branch-Config-Snapshot nicht eindeutig.
        # JSON-Form, weil create_branch die Overrides in branch_meta persistiert.
        branch_overrides["ai_model_ref"] = ai_model_ref.model_dump(mode="json")
        llm_model_override = ai_model_ref.model_id

    # Issue #1686 (P1): Ohne expliziten Override die im Original-Manifest
    # erfasste Route seeden statt der aktuellen Workspace-Defaults —
    # `seed_run_stage_routing` würde sonst auf den heutigen Defaults landen,
    # und ein "identisches" Replay liefe unbemerkt auf einem anderen Modell,
    # sobald sich Defaults/Connections seit dem Original-Run geändert haben.
    # Ist die Original-Connection nicht mehr auflösbar (z. B. gelöscht), ist
    # ein sichtbarer 409 vor jeder Branch-/Run-Erzeugung ehrlicher als ein
    # stiller Rückfall auf Defaults, der wie ein 1:1-Replay aussähe.
    route_seed_ai_model_ref = ai_model_ref
    if route_seed_ai_model_ref is None:
        route_seed_ai_model_ref = _runs_mod._ai_model_ref_from_manifest_route(original_stage_route)
        if route_seed_ai_model_ref is not None:
            try:
                _runs_mod.prevalidate_ai_model_ref(route_seed_ai_model_ref)
            except ValueError as exc:
                return _runs_mod.json_error(
                    f"Run {run_id}'s captured model route is no longer resolvable "
                    f"({exc}) — refusing to silently fall back to current workspace "
                    "defaults for what would be presented as a 1:1 replay.",
                    status=409,
                    code="manifest_route_unresolvable",
                )

    branch_state = manager.create_branch(
        simulation_id,
        f"replay-of-{run_id}",
        copy_profiles=True,
        copy_report_artifacts=False,
        overrides=branch_overrides,
    )
    new_simulation_id = branch_state.simulation_id

    with _runs_mod.RunLifecycle.begin(
        _runs_mod.run_registry,
        "simulation_run",
        new_simulation_id,
        parent_run_id=run_id,
        replayed_from_run_id=run_id,
        failure_message="Replay failed: {exc_type}",
        progress=0,
        message=f"Replay of {run_id} queued",
        linked_ids={
            "simulation_id": new_simulation_id,
            "project_id": branch_state.project_id,
        },
        artifacts=_runs_mod._simulation_artifacts(new_simulation_id),
        resume_capability={"available": True, "action": "resume", "label": "Resume run"},
        branch_label=branch_state.branch_name,
        metadata={
            **_runs_mod.workspace_credential_metadata(),
            "graph_id": branch_state.graph_id,
            "branch_name": branch_state.branch_name,
            **(
                {"replay_overrides": overrides.model_dump(exclude_none=True)}
                if overrides is not None
                else {}
            ),
        },
    ) as lifecycle:
        new_run = lifecycle.record
        new_run_id = new_run["run_id"]

        # ai_model_ref durchreichen, nicht nur model_id: dieselbe Modell-ID kann
        # auf mehreren Provider-Connections liegen. Ohne die Connection-ID
        # liefe das Replay auf einer anderen Connection als das Original.
        # route_seed_ai_model_ref ist entweder der explizite Override oder
        # (Issue #1686 P1) die aus dem Original-Manifest rekonstruierte Route.
        _runs_mod.seed_run_stage_routing(
            new_run_id,
            "simulation_rounds",
            llm_model_override=llm_model_override,
            llm_runtime=None,
            ai_model_ref=route_seed_ai_model_ref,
        )
        route_router = _runs_mod.StageModelRouter(new_run_id)
        resolved_route = route_router.resolve("simulation_rounds")
        route_router.lock_stage("simulation_rounds", resolved_route)
        resolved_api_key = _runs_mod.resolve_route_api_key(resolved_route, None)
        # Finding H2 (#1688): same fail-closed condition as
        # simulation_run._resolve_start_route — a replay must not silently
        # fall through to an operator-configured route when a workspace key
        # is missing. Raising (rather than returning) lets RunLifecycle's
        # __exit__ mark the new run "failed" instead of leaving it "pending"
        # — the same mechanism already relied on below when start_simulation()
        # itself fails. handle_api_errors turns ValueError into a 400.
        if _runs_mod._reject_if_route_api_key_missing(resolved_route, resolved_api_key) is not None:
            raise ValueError(
                f"provider_override: kein api_key im Payload und kein Key in der Settings-DB "
                f"für Provider '{resolved_route.provider_id}'. "
                "Bitte in Einstellungen → LLM-Anbieter einen Schlüssel speichern "
                "oder im Sitzungsfeld eingeben."
            )

        # Issue #1686 (P2): Draft-Manifest VOR dem Subprozess-Start schreiben,
        # nicht danach. Der Monitor-Thread finalisiert das Manifest, sobald er
        # das Ende der Simulation erkennt — bei einem sofort beendeten
        # Subprozess konnte er das VOR dem bisherigen Draft-Write hier
        # erreichen und fand keinen Draft (capture_final wirft dann
        # FileNotFoundError, best-effort geschluckt); der Run blieb dauerhaft
        # im Status "draft" hängen.
        _runs_mod._capture_replay_manifest_draft(
            original_run_id=run_id,
            new_run_id=new_run_id,
            new_simulation_id=new_simulation_id,
            manifest=manifest,
            resolved_route=resolved_route,
            original_stage_route=original_stage_route,
            manager=manager,
            max_rounds=capped_max_rounds,
        )

        # Finding H4 (#1688): apply the same (possibly demo-capped) budget
        # to the replay's subprocess artifacts as a fresh start does — the
        # capped_max_rounds computed above only bounds the round count;
        # without this the demo LLM-call/duration hardcap never reached the
        # replayed run at all.
        from ..services.run_budget import set_run_budget_config as _set_run_budget_config
        from .simulation_run import _apply_budget_to_simulation

        _apply_budget_to_simulation(
            new_simulation_id, new_run_id, capped_budget_config, _set_run_budget_config
        )

        try:
            _runs_mod.SimulationRunner.start_simulation(
                simulation_id=new_simulation_id,
                platform=manifest.simulation.platform,
                max_rounds=capped_max_rounds,
                enable_graph_memory_update=manifest.simulation.enable_graph_memory_update,
                graph_id=manifest.simulation.memory_update_graph_id,
                runtime_env=_runs_mod.build_route_subprocess_env(
                    resolved_route, resolved_api_key, new_run_id
                ),
            )
        except Exception:
            # Der Draft wurde bereits geschrieben (s.o.) — scheitert der
            # Start jetzt doch, darf kein Manifest für einen Run zurück-
            # bleiben, der nie lief. Analog zum normalen Startpfad, der seit
            # #1686 denselben Helper für dieselbe Situation nutzt
            # (simulation_run.py::start_simulation).
            from ..services.manifest_capture import ManifestCapture

            ManifestCapture.discard_draft_best_effort(
                run_id=new_run_id, run_dir=_runs_mod.ArtifactLocator.run_dir(new_run_id)
            )
            raise

        manager._set_status(branch_state, _runs_mod.SimulationStatus.RUNNING)
        lifecycle.succeed(status="processing", message=f"Replay of {run_id} started")

    return {"run_id": new_run["run_id"], "status": "processing"}


def _capture_replay_manifest_draft(
    *,
    original_run_id: str,
    new_run_id: str,
    new_simulation_id: str,
    manifest,
    resolved_route,
    original_stage_route,
    manager: SimulationManager,
    max_rounds: "int | None" = None,
) -> None:
    """Draft-Manifest für einen Replay-Run schreiben (Issue #1274 Punkt 3).

    Best-effort, analog zu ``simulation_run._capture_start_manifest_draft``:
    ein Manifest-Fehler darf weder den Replay-Start (Aufrufer läuft VOR
    ``SimulationRunner.start_simulation``, Issue #1686 P2) noch einen bereits
    laufenden Replay gefährden. Übernimmt Eingaben und Simulationsparameter
    1:1 aus dem Original-Manifest und dokumentiert eine etwaige
    Modell-Route-Abweichung (die einzige überschreibbare Größe) über
    ``deviations``.

    Issue #1686 (P1): die aufgelöste Replay-Route wird IMMER mit der im
    Original-Manifest erfassten Route verglichen — unabhängig davon, ob ein
    expliziter Override oder die aus dem Manifest rekonstruierte Route
    geseedet wurde. Ohne diesen Vergleich blieb ``deviations`` leer, sobald
    kein Override gesetzt war, obwohl sich Defaults/Connections seit dem
    Original-Run geändert haben konnten.
    """
    _runs_mod = _runs_module()
    try:
        from .. import __version__
        from ..contracts.run_manifest_contract import ai_route_snapshot_from_ai_route
        from ..services.manifest_capture import ManifestCapture
        from ..services.runtime_run_config import RuntimeRunConfig

        # Issue #1686 (P2): den Hash der tatsächlich verwendeten
        # Branch-Konfiguration berechnen, nicht den des Originals kopieren.
        # ``create_branch`` hat die Konfiguration bereits umgeschrieben (neue
        # simulation_id, branch_metadata, ggf. ai_model_ref-Override) — der
        # kopierte Original-Hash würde diese Änderungen verschleiern.
        # Gemeinsamer Helper mit dem normalen Startpfad
        # (``simulation_run.py::_capture_start_manifest_draft``), damit beide
        # Pfade nicht unabhängig voneinander driften können.
        branch_config = manager.get_simulation_config(new_simulation_id)
        branch_config_hash = ManifestCapture.simulation_config_hash(branch_config)

        deviations: list[dict[str, Any]] = []
        if original_stage_route is not None:
            original_model = original_stage_route.model
            original_provider = original_stage_route.provider
            if original_model != resolved_route.model:
                deviations.append(
                    {"field": "model_id", "original": original_model, "replay": resolved_route.model}
                )
            if original_provider != resolved_route.provider_id:
                deviations.append(
                    {
                        "field": "provider_connection_id",
                        "original": original_provider,
                        "replay": resolved_route.provider_id,
                    }
                )

        canonical_route = RuntimeRunConfig(new_run_id).load_ai_route_snapshot("simulation_rounds")
        ai_route_snapshot = (
            ai_route_snapshot_from_ai_route(canonical_route).model_dump(mode="json")
            if canonical_route is not None
            else None
        )

        ManifestCapture.capture_draft_best_effort(
            run_id=new_run_id,
            run_dir=_runs_mod.ArtifactLocator.run_dir(new_run_id),
            seed_document_hash=manifest.inputs.seed_document_hash,
            seed_document_filename=manifest.inputs.seed_document_filename,
            simulation_config_hash=branch_config_hash,
            graph_id=manifest.inputs.graph_id,
            agora_version=__version__,
            schema_version="1.0.0",
            random_seed=None,
            simulation_id_seed=new_simulation_id,
            routing={
                "simulation_rounds": {
                    "model": resolved_route.model,
                    "provider": resolved_route.provider_id,
                    "base_url": resolved_route.base_url_sanitized or "",
                    "ai_route_snapshot": ai_route_snapshot,
                }
            },
            prompts=ManifestCapture.oasis_prompt_snapshots(),
            platform=manifest.simulation.platform,
            # Finding H4 (#1688): record the ACTUALLY applied max_rounds
            # (possibly demo-capped) here, not the original manifest's value
            # — otherwise the replay's own manifest would claim a round
            # count it never ran with.
            max_rounds=(
                max_rounds if max_rounds is not None else manifest.simulation.max_rounds
            ),
            enable_graph_memory_update=manifest.simulation.enable_graph_memory_update,
            memory_update_graph_id=manifest.simulation.memory_update_graph_id,
            replayed_from_run_id=original_run_id,
            deviations=deviations,
        )
    except Exception:  # noqa: BLE001 — best-effort, siehe Docstring
        _runs_mod.logger.warning(
            "Replay-Draft-Manifest für run_id=%s konnte nicht geschrieben werden",
            new_run_id,
            exc_info=True,
        )
