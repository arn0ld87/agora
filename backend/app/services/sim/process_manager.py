"""
Subprocess lifecycle management for OASIS simulations.

Extracted from ``simulation_runner.py`` (M11 Phase 5 PR 5).
``simulation_runner.py`` keeps thin delegation class-methods for backward-compat.

Design constraints:
- No import of ``simulation_runner.py`` (avoids circular import).
- Mutable class-level dicts are passed by reference as keyword arguments.
  Python dicts are passed by reference, so mutations are visible to the caller.
- ``save_state`` is a callable so state can be persisted without importing
  ``SimulationRunner``.
- atexit / signal handler registration is self-contained; the cleanup action
  is injected as ``cleanup_callable`` to decouple from the class.

Security — Subprozess-Env-Whitelist (Code-Review 2026-05-17 §1.6):
    ``os.environ.copy()`` würde das vollständige Prozess-Environment an den
    OASIS-Subprozess vererben — damit auch Secrets wie ``SECRET_KEY``,
    ``AGORA_AUTH_TOKEN``, ``NEO4J_PASSWORD``, ``LLM_API_KEY`` und
    ``AGORA_FERNET_KEY``. Stattdessen wird nur die explizite Whitelist
    ``SAFE_ENV_KEYS`` übernommen. LLM-Credentials werden ausschließlich
    via ``runtime_env`` (Parameter von ``start_simulation``) übergeben,
    da die OASIS-Skripte diese aus dem Env lesen müssen.
"""

from __future__ import annotations

import atexit
import os
import re
import signal
import subprocess
import sys
import threading
from datetime import datetime
from queue import Queue
from typing import Any, Callable, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from ...observability import sim_active_gauge, sim_counter
from ...utils.logger import get_logger
from .run_state_store import RunnerStatus, SimulationRunState
from .process_cancel import (
    CANCEL_ABORT_FILENAME as CANCEL_ABORT_FILENAME,
    _clear_cancel_abort as _clear_cancel_abort,
    _read_cancel_abort as _read_cancel_abort,
    _write_cancel_abort as _write_cancel_abort,
)
from .process_environment import (
    SAFE_ENV_KEYS as SAFE_ENV_KEYS,
    _build_subprocess_env as _build_subprocess_env,
    _compute_oasis_db_path as _compute_oasis_db_path,
    _inject_oasis_db_env as _inject_oasis_db_env,
    _resolve_child_path as _resolve_child_path,
)
from .process_termination import (
    IS_WINDOWS as IS_WINDOWS,
    cleanup_all_simulations as cleanup_all_simulations,
    stop_simulation as stop_simulation,
    terminate_process as terminate_process,
    terminate_run as terminate_run,
)


_tracer = trace.get_tracer(__name__)

logger = get_logger("agora.process_manager")

_SAFE_SIMULATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _validate_simulation_id(simulation_id: str) -> None:
    if not _SAFE_SIMULATION_ID_RE.fullmatch(simulation_id):
        raise ValueError("Invalid simulation_id")


# ---------------------------------------------------------------------------
# Finding A (Codex-Review 2026-09-08, PR #1476) — Start-Serialisierung.
#
# Zwei ueberlappende Start-Anfragen fuer dieselbe simulation_id treffen sich
# sonst in genau dem Fenster zwischen dem Persistieren von STARTING (noch
# ohne process_pid, siehe start_simulation weiter unten) und dem
# tatsaechlichen subprocess.Popen-Aufruf: eine zweite Anfrage haelt den
# gerade laufenden ersten Start faelschlich fuer verwaist
# (is_process_alive(None) ist immer False) und spawnt einen zweiten
# Subprozess. Unter dem konfigurierten gevent-Worker (wsgi.py,
# gevent.monkey.patch_all()) ist das real erreichbar, sobald der erste
# Request waehrend des Starts an einem I/O-Punkt yieldet.
#
# _start_locks serialisiert pro simulation_id. threading.Lock ist unter
# gevent bereits durch das Monkeypatching kooperativ (dasselbe Muster nutzt
# dieser Codebase schon fuer ThreadPoolExecutor unter patch_all): ein
# Greenlet, das den Lock haelt und an einem I/O-Punkt yieldet, blockiert nur
# sich selbst, andere Greenlets warten kooperativ statt den Event-Loop zu
# blockieren. _start_locks_guard schuetzt nur die Lock-Erzeugung selbst
# (dict.setdefault) — eine sehr kurze, rein synchrone Kritische Sektion ohne
# I/O, damit zwei gleichzeitige Erstanfragen fuer eine noch nie gesehene
# simulation_id nicht zwei verschiedene Lock-Objekte anlegen.
_start_locks: Dict[str, threading.Lock] = {}
_start_locks_guard = threading.Lock()

#: Solange ein PID-loser STARTING-Zustand juenger als dieses Zeitfenster
#: ist, gilt er als legitim laufender Start (noch vor dem Popen-Aufruf),
#: nicht als verwaist — auch als Verteidigungslinie hinter dem Lock (z. B.
#: falls start_simulation je ohne den Lock-Wrapper aufgerufen wird). Ein
#: wirklich haengengebliebener PID-loser Zustand (z. B. nach einem
#: Container-Restart waehrend dieses Fensters) bleibt nach Ablauf des
#: Fensters weiterhin korrigierbar.
_STARTING_GRACE_PERIOD_SECONDS = 30


def _get_start_lock(simulation_id: str) -> threading.Lock:
    with _start_locks_guard:
        return _start_locks.setdefault(simulation_id, threading.Lock())


def _is_starting_state_fresh(state: "SimulationRunState") -> bool:
    """True wenn ``state`` (STARTING, ohne process_pid) juenger als
    ``_STARTING_GRACE_PERIOD_SECONDS`` ist."""
    if not state.started_at:
        return False
    try:
        started = datetime.fromisoformat(state.started_at)
    except ValueError:
        return False
    age_seconds = (datetime.now() - started).total_seconds()
    return age_seconds < _STARTING_GRACE_PERIOD_SECONDS


def is_process_alive(pid: Optional[int]) -> bool:
    """True wenn ``pid`` einen (noch) existierenden Prozess bezeichnet.

    Liveness-Muster wie ``SimulationIPCClient.check_env_alive``
    (``simulation_ipc.py``): ``os.kill(pid, 0)`` sendet kein Signal, prüft
    nur Existenz/Berechtigung.

    ``pid`` fehlend/``None``/``<= 0`` → tot (konservativ: kein PID heißt kein
    verifizierbarer laufender Prozess). ``ProcessLookupError`` → tot.
    ``PermissionError`` → Prozess existiert, gehört aber jemand anderem —
    im Container unwahrscheinlich, wird konservativ als lebend behandelt
    (Tech-Review 2026-09-07 Slice B1, Fix-Punkt 1/3).
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True











# ---------------------------------------------------------------------------
# Subprozess-Env-Whitelist (Code-Review 2026-05-17 §1.6)
# ---------------------------------------------------------------------------
# Nur diese Keys werden aus os.environ in den OASIS-Subprozess vererbt.
# Secrets (SECRET_KEY, AGORA_AUTH_TOKEN, NEO4J_PASSWORD, LLM_API_KEY,
# AGORA_FERNET_KEY) werden bewusst NICHT weitergegeben. LLM-Credentials
# kommen ausschließlich über den ``runtime_env``-Parameter.
#
# Optionale Connection-Keys:
# - ``REDIS_URL``: enthaelt potenziell ein Passwort (Format
#   ``redis://:pw@host:port/db``). Wir lassen es bewusst zu, weil die
#   Redis-IPC-Bridge (``scripts/subprocess_redis_bridge.py``) sonst im
#   Subprozess inaktiv bleibt. Wer das nicht will, leert REDIS_URL vor
#   dem ``start_simulation``-Call.
# - ``HF_TOKEN``: Hugging-Face-Authentifizierung fuer private/Gated
#   Models (z.B. ``Twitter/twhin-bert-base`` ist zwar public, aber
#   Custom-Mirrors koennen Auth verlangen). Public Models funktionieren
#   ohne Token.
# - ``AGORA_CODEX_CLI_BIN`` / ``AGORA_CODEX_CLI_TIMEOUT_SECONDS``: Pfad und
#   Timeout der Codex-CLI (Issue #1423). Kein Secret — die CLI
#   authentifiziert ueber die lokale ``codex login``-Session, nicht ueber
#   einen Key. Ohne diese Keys faellt der Subprozess auf ``codex`` im PATH
#   und 180 s zurueck, was fuer den Regelfall stimmt.



# Flag whether cleanup function is registered
_cleanup_registered = False

# Platform detection

# Sub-Slice 21 — OASIS-DB-Pfad pro Sim, damit OASIS keine DB ins
# read-only Site-Packages-Verzeichnis schreibt.








def start_simulation(
    simulation_id: str,
    platform: str,
    *,
    run_state_dir: str,
    scripts_dir: str,
    processes: Dict[str, subprocess.Popen],  # type: ignore[type-arg]
    action_queues: Dict[str, Queue],  # type: ignore[type-arg]
    monitor_threads: Dict[str, threading.Thread],
    stdout_files: Dict[str, Any],
    stderr_files: Dict[str, Any],
    graph_memory_enabled: Dict[str, bool],
    get_run_state: Callable[[str], Optional[SimulationRunState]],
    save_state: Callable[[SimulationRunState], None],
    on_monitor_start: Callable[[str], None],
    write_control_state: Callable[..., None],
    get_config: Callable[[str], Optional[Dict[str, Any]]],
    config_exists: Callable[[str], bool],
    setup_graph_memory: Callable[[str], None],
    max_rounds: Optional[int] = None,
    runtime_env: Optional[Dict[str, str]] = None,
    correct_stale_run: Optional[Callable[[SimulationRunState, Optional[str]], None]] = None,
    requested_run_id: Optional[str] = None,
) -> SimulationRunState:
    """Public entrypoint — serialisiert pro ``simulation_id`` (Finding A,
    Codex-Review 2026-09-08, PR #1476).

    Delegiert an :func:`_start_simulation_impl`, gehalten unter dem
    ``simulation_id``-spezifischen Lock aus :func:`_get_start_lock`. Siehe
    dessen Docstring-Kommentar oben im Modul für die Race-Begründung.
    """
    lock = _get_start_lock(simulation_id)
    with lock:
        return _start_simulation_impl(
            simulation_id,
            platform,
            run_state_dir=run_state_dir,
            scripts_dir=scripts_dir,
            processes=processes,
            action_queues=action_queues,
            monitor_threads=monitor_threads,
            stdout_files=stdout_files,
            stderr_files=stderr_files,
            graph_memory_enabled=graph_memory_enabled,
            get_run_state=get_run_state,
            save_state=save_state,
            on_monitor_start=on_monitor_start,
            write_control_state=write_control_state,
            get_config=get_config,
            config_exists=config_exists,
            setup_graph_memory=setup_graph_memory,
            max_rounds=max_rounds,
            runtime_env=runtime_env,
            correct_stale_run=correct_stale_run,
            requested_run_id=requested_run_id,
        )


def _start_simulation_impl(
    simulation_id: str,
    platform: str,
    *,
    run_state_dir: str,
    scripts_dir: str,
    processes: Dict[str, subprocess.Popen],  # type: ignore[type-arg]
    action_queues: Dict[str, Queue],  # type: ignore[type-arg]
    monitor_threads: Dict[str, threading.Thread],
    stdout_files: Dict[str, Any],
    stderr_files: Dict[str, Any],
    graph_memory_enabled: Dict[str, bool],
    get_run_state: Callable[[str], Optional[SimulationRunState]],
    save_state: Callable[[SimulationRunState], None],
    on_monitor_start: Callable[[str], None],
    write_control_state: Callable[..., None],
    get_config: Callable[[str], Optional[Dict[str, Any]]],
    config_exists: Callable[[str], bool],
    setup_graph_memory: Callable[[str], None],
    max_rounds: Optional[int] = None,
    runtime_env: Optional[Dict[str, str]] = None,
    correct_stale_run: Optional[Callable[[SimulationRunState, Optional[str]], None]] = None,
    requested_run_id: Optional[str] = None,
) -> SimulationRunState:
    """Start an OASIS simulation: validate, init state, launch subprocess, start monitor.

    All mutable class-level dicts from ``SimulationRunner`` are passed by
    reference — mutations here are visible to the caller.

    Args:
        simulation_id:          Simulation ID.
        platform:               ``twitter`` / ``reddit`` / ``parallel``.
        run_state_dir:          ``SimulationRunner.RUN_STATE_DIR``.
        scripts_dir:            ``SimulationRunner.SCRIPTS_DIR``.
        processes:              ``SimulationRunner._processes`` (mutated).
        action_queues:          ``SimulationRunner._action_queues`` (mutated).
        monitor_threads:        ``SimulationRunner._monitor_threads`` (mutated).
        stdout_files:           ``SimulationRunner._stdout_files`` (mutated).
        stderr_files:           ``SimulationRunner._stderr_files`` (mutated).
        graph_memory_enabled:   ``SimulationRunner._graph_memory_enabled``.
        get_run_state:          Callable to load current run state.
        save_state:             Callable to persist run state.
        on_monitor_start:       Callable(simulation_id) to spawn monitor thread.
        write_control_state:    Callable to reset control_state.json.
        get_config:             Callable(simulation_id) → config dict or None.
        config_exists:          Callable(simulation_id) → bool.
        setup_graph_memory:     Callable(simulation_id) that configures graph
                                memory and mutates ``graph_memory_enabled``.
        max_rounds:             Optional round cap (passed to script CLI).
        correct_stale_run:      Optional callable(state, requested_run_id),
                                invoked instead of ``save_state`` when a stale
                                RUNNING/STARTING run is corrected to FAILED
                                (Finding B, Codex-Review 2026-09-08, PR
                                #1476) — needed because a plain
                                ``save_state`` in this branch would sync the
                                run-registry entry via "latest manifest for
                                this simulation_id", which on the
                                resume/restart path is already the freshly
                                created REPLACEMENT manifest
                                (``RunLifecycle.begin`` runs before this
                                function), not the actually orphaned run.
                                Falls back to ``save_state`` when ``None``.
        requested_run_id:       Run-registry ``run_id`` of the run the caller
                                actually asked to resume/restart (Finding F1,
                                Codex-Review Runde 3, PR #1476) — passed
                                through to ``correct_stale_run`` so it targets
                                exactly that manifest instead of guessing
                                among several "processing" manifests for the
                                same ``simulation_id``. ``None`` when the
                                caller has no specific run in mind (plain
                                start / replay onto a brand-new
                                ``simulation_id``).

    Returns:
        Updated ``SimulationRunState`` (status RUNNING).

    Raises:
        ValueError: if already running, config missing, or script not found.
    """
    _validate_simulation_id(simulation_id)

    # Check if already running. Ein persistierter RUNNING/STARTING-Status
    # allein ist kein Beweis: nach einem Container-Restart existiert der
    # Subprozess nicht mehr, aber run_state.json wurde nie aktualisiert
    # (Tech-Review 2026-09-07 Slice B1). Deshalb per PID-Liveness prüfen,
    # bevor der Start verweigert wird.
    existing = get_run_state(simulation_id)
    if existing and existing.runner_status in [RunnerStatus.RUNNING, RunnerStatus.STARTING]:
        if is_process_alive(existing.process_pid):
            raise ValueError(f"Simulation already running: {simulation_id}")

        # Finding A (Codex-Review 2026-09-08, PR #1476): ein PID-loser
        # STARTING-Zustand ist nicht automatisch verwaist — er ist auch das
        # Bild eines GERADE laufenden Starts, bevor Popen die process_pid
        # gesetzt hat (siehe unten). Der Lock in start_simulation() macht
        # diese Rennsituation innerhalb desselben Worker-Prozesses bereits
        # unmoeglich; dieser Freshness-Check ist die zweite Verteidigungslinie
        # (z. B. falls start_simulation() je ohne den Lock-Wrapper erreicht
        # wird) und verhindert zugleich, dass ein wirklich haengengebliebener
        # PID-loser Zustand (nach Ablauf des Zeitfensters) dauerhaft blockiert.
        if existing.process_pid is None and _is_starting_state_fresh(existing):
            raise ValueError(f"Simulation already running: {simulation_id}")

        logger.warning(
            "Stale %s state for %s: process_pid=%s is not alive — correcting state and allowing restart",
            existing.runner_status.value, simulation_id, existing.process_pid,
        )
        existing.runner_status = RunnerStatus.FAILED
        existing.error = "Prozess-Neustart während des Runs"
        if correct_stale_run is not None:
            correct_stale_run(existing, requested_run_id)
        else:
            save_state(existing)

    if not config_exists(simulation_id):
        raise ValueError("Simulation config does not exist, call /prepare endpoint first")

    # Reset control_state.json so a previous paused/stop_requested flag does not
    # silently freeze the new subprocess on round 0.
    try:
        write_control_state(simulation_id, paused=False, stop_requested=False)
    except Exception as ctrl_err:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(f"Could not reset control_state.json before start: {ctrl_err}")

    config = get_config(simulation_id)
    if not config:
        raise ValueError("Simulation config is unreadable")

    # Derive total rounds from time config
    time_config = config.get("time_config", {})
    total_hours = time_config.get("total_simulation_hours", 72)
    minutes_per_round = time_config.get("minutes_per_round", 30)
    total_rounds = int(total_hours * 60 / minutes_per_round)

    if max_rounds is not None and max_rounds > 0:
        original_rounds = total_rounds
        total_rounds = min(total_rounds, max_rounds)
        if total_rounds < original_rounds:
            logger.info(
                f"Rounds truncated: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})"
            )

    state = SimulationRunState(
        simulation_id=simulation_id,
        runner_status=RunnerStatus.STARTING,
        total_rounds=total_rounds,
        total_simulation_hours=total_hours,
        started_at=datetime.now().isoformat(),
    )

    save_state(state)

    # Configure graph memory via injected callback
    setup_graph_memory(simulation_id)

    sim_dir = _resolve_child_path(run_state_dir, simulation_id, kind="simulation")

    # Codex-Review PR #1474: stale cancel_abort.json aus einem frueheren
    # Nutzer-Stop entfernen, BEVOR der neue Subprozess gespawnt wird — sonst
    # liest der neue Monitor den alten Marker und klassifiziert einen
    # sauberen Exit-0-Lauf faelschlich als stopped/user_stop.
    _clear_cancel_abort(str(sim_dir))

    # Determine which script to run
    if platform == "twitter":
        script_name = "run_twitter_simulation.py"
        state.twitter_running = True
    elif platform == "reddit":
        script_name = "run_reddit_simulation.py"
        state.reddit_running = True
    else:
        script_name = "run_parallel_simulation.py"
        state.twitter_running = True
        state.reddit_running = True

    script_path = _resolve_child_path(scripts_dir, script_name, kind="script")

    if not script_path.is_file():
        raise ValueError(f"Script does not exist: {script_path}")

    # Create action queue
    action_queue: Queue = Queue()  # type: ignore[type-arg]
    action_queues[simulation_id] = action_queue

    try:
        # Build run command
        config_path = sim_dir / "simulation_config.json"
        cmd = [sys.executable, str(script_path), "--config", str(config_path)]

        if max_rounds is not None and max_rounds > 0:
            cmd.extend(["--max-rounds", str(max_rounds)])

        # Create main log file
        main_log_path = sim_dir / "simulation.log"
        main_log_file = open(main_log_path, "w", encoding="utf-8")

        env = _build_subprocess_env(runtime_env, sim_dir)

        # Slice 1c: Trace-Context via W3C-traceparent in den Subprozess propagieren.
        with _tracer.start_as_current_span("agora.subprocess.spawn") as span:
            span.set_attribute("agora.simulation.id", simulation_id)
            span.set_attribute("agora.subprocess.cmd", " ".join(cmd))
            carrier: dict[str, str] = {}
            TraceContextTextMapPropagator().inject(carrier)
            traceparent = carrier.get("traceparent", "")
            if traceparent:
                env["TRACEPARENT"] = traceparent

            process = subprocess.Popen(
                cmd,
                cwd=str(sim_dir),
                stdout=main_log_file,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=env,
                start_new_session=True,
            )

        stdout_files[simulation_id] = main_log_file
        stderr_files[simulation_id] = None

        state.process_pid = process.pid
        state.runner_status = RunnerStatus.RUNNING
        processes[simulation_id] = process
        # Slice 2b: Sim-Lifecycle-Metric — PENDING → RUNNING
        sim_active_gauge().add(1)
        sim_counter().add(1, {"status": "started"})
        save_state(state)

        # Start monitoring thread via injected callback
        on_monitor_start(simulation_id)

        logger.info(
            f"Simulation started successfully: {simulation_id}, pid={process.pid}, platform={platform}",
            extra={"simulation_id": simulation_id},
        )

    except Exception as e:
        state.runner_status = RunnerStatus.FAILED
        state.error = str(e)
        save_state(state)
        raise

    return state






def register_cleanup(*, cleanup_callable: Callable[[], None]) -> None:
    """Register atexit and signal handlers to clean up simulation processes.

    Called when Flask app starts. The actual cleanup action is injected as
    ``cleanup_callable`` so this module remains independent of
    ``SimulationRunner``.

    Reloader-Child-Guard: In Flask debug mode, only register in the reloader
    child process (``WERKZEUG_RUN_MAIN=true``). In non-debug mode, always
    register.

    Args:
        cleanup_callable: Zero-argument callable (typically
                          ``SimulationRunner.cleanup_all_simulations``).
    """
    global _cleanup_registered

    if _cleanup_registered:
        return

    # env-only: werkzeug/subprocess intern, kein settings_layer-Kandidat
    is_reloader_process = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    is_debug_mode = (
        os.environ.get("FLASK_DEBUG") == "1"  # env-only: werkzeug/subprocess intern
        or os.environ.get("WERKZEUG_RUN_MAIN") is not None  # env-only: werkzeug/subprocess intern
    )

    # In debug mode, only register in reloader child process;
    # always register in non-debug mode.
    if is_debug_mode and not is_reloader_process:
        _cleanup_registered = True
        return

    # Save original signal handlers
    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    original_sighup = None
    has_sighup = hasattr(signal, "SIGHUP")
    if has_sighup:
        original_sighup = signal.getsignal(signal.SIGHUP)

    def cleanup_handler(signum: Any = None, frame: Any = None) -> None:
        """Signal handler: clean up simulation processes first, then forward."""
        logger.info(f"Received signal {signum}, starting cleanup...")
        cleanup_callable()

        if signum == signal.SIGINT and callable(original_sigint):
            original_sigint(signum, frame)
        elif signum == signal.SIGTERM and callable(original_sigterm):
            original_sigterm(signum, frame)
        elif has_sighup and signum == signal.SIGHUP:
            if callable(original_sighup):
                original_sighup(signum, frame)  # type: ignore[misc]
            else:
                sys.exit(0)
        else:
            raise KeyboardInterrupt

    # Register atexit handler (as fallback)
    atexit.register(cleanup_callable)

    # Register signal handler (only in main thread)
    try:
        signal.signal(signal.SIGTERM, cleanup_handler)
        signal.signal(signal.SIGINT, cleanup_handler)
        if has_sighup:
            signal.signal(signal.SIGHUP, cleanup_handler)
    except ValueError:
        logger.warning(
            "Cannot register signal handler (not in main thread), only using atexit"
        )

    _cleanup_registered = True




def get_running_simulations(
    *,
    processes: Dict[str, subprocess.Popen],  # type: ignore[type-arg]
) -> List[str]:
    """Return list of simulation IDs whose subprocesses are still running.

    Args:
        processes: ``SimulationRunner._processes``.

    Returns:
        List of simulation IDs with ``process.poll() is None``.
    """
    return [sim_id for sim_id, proc in processes.items() if proc.poll() is None]
