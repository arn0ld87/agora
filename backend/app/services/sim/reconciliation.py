"""Startup-Reconciliation für verwaiste ``simulation_run``-Runs.

Tech-Review 2026-09-07, Slice B1. Fixes für Codex-Review-Findings A+B,
2026-09-08 (siehe PR #1476).

Problem: ``RunRegistry``-Einträge (``uploads/run_registry/*.json``) und
``run_state.json`` kennen den Status eines Simulation-Runs nur so lange, wie
der zugehörige OASIS-Subprozess selbst ihn aktualisiert. Nach einem
Container-Restart existiert dieser Subprozess nicht mehr — die Dateien
bleiben aber auf ``pending``/``processing`` (Registry) bzw.
``STARTING``/``RUNNING`` (``run_state.json``) stehen und werden dem
Frontend fälschlich als „läuft noch" angezeigt, für immer, weil nichts
mehr existiert, das den Zustand jemals wieder ändert.

``reconcile_stale_runs`` korrigiert genau diese verwaisten Runs anhand der
in ``run_state.json`` persistierten ``process_pid``: existiert der Prozess
nicht (mehr) UND ist ``run_state.json`` noch in einem unklaren Zustand
(``RUNNING``/``STARTING`` oder gar nicht vorhanden), wird der Run als
``failed``/``process_restart`` markiert. Existiert der Prozess noch (z. B.
weil nur ein Worker-Prozess neu gestartet wurde, der Subprozess aber
überlebt hat), bleibt er unangetastet. Ist ``run_state.json`` dagegen
bereits terminal mit ``COMPLETED`` oder ``STOPPED`` — der Prozess also tot,
weil er regulär beendet wurde, nicht weil er verwaist ist —, wird der Run
NICHT mit ``process_restart`` überschrieben, aber der Endzustand auch NICHT
auf die Registry propagiert (F2, Codex-Review Runde 3, PR #1476):
``run_state.json`` trägt keine RunRegistry-``run_id``, nur die
``simulation_id`` — bei mehreren Registry-Manifesten für dieselbe
Simulation (z. B. Alt-Run + Ersatzlauf nach einem Resume, siehe Finding F1)
ist nicht feststellbar, zu welchem der terminale Zustand gehört. Der Run
bleibt in diesem Fall unangetastet, nur geloggt (ursprünglich Finding B —
dessen Propagation wurde in Runde 3 wegen genau dieser Fehlzuordnungsgefahr
wieder entfernt).

``run_state.json`` auf ``FAILED`` ist davon bewusst ausgenommen (F1,
Codex-Review Runde 5, PR #1476): ein toter Prozess bei bereits
persistiertem ``FAILED`` trägt keine neue, potenziell falsche
Erfolgsaussage in sich — der Verwaist-Zweig würde ein noch stale Manifest
ohnehin auf genau diesen Zustand (``failed``/``process_restart``) setzen.
Ein solches Manifest wird deshalb wie ein verwaister Run behandelt statt
übersprungen, siehe ``_TERMINAL_RUNNER_STATUSES`` unten.

Aufrufer: ``run_startup_reconciliation`` bündelt Config-Flag-Check und
Best-effort-Fehlerbehandlung für zwei Einhängepunkte — ``app/__init__.py::
create_app`` (Entwicklungs-/Testbetrieb ohne gunicorn, einziger
Startup-Hook) und ``gunicorn.conf.py::post_fork`` (Produktion; unter
``preload_app=True`` + ``workers=1`` läuft ``create_app`` nur einmal im
Master VOR dem Fork — nur ``post_fork`` feuert deterministisch bei jedem
Worker-Start, auch nach Timeout/Crash/Replacement des einzigen Workers,
Finding A). Der doppelte Aufruf beim allerersten Boot (Master via
``create_app`` vor dem ersten Fork, dann erneut im frisch geforkten Worker
via ``post_fork``) ist harmlos: der zweite Durchlauf findet keine weiteren
``pending``/``processing``-Runs mehr und ist ein No-op.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol

from pydantic import BaseModel, ConfigDict

from ...jobs.identity import owns_run
from ...utils.logger import get_logger
from .process_manager import is_process_alive
from .run_state_store import RunnerStatus, load_run_state, save_run_state

logger = get_logger("agora.sim.reconciliation")

#: Registry-Status, die nach einem Neustart nicht mehr vertrauenswürdig
#: sind — es gibt keinen Prozess mehr, der sie aktiv hält.
#:
#: F1 (Codex-Review Runde 4, PR #1476): ``paused`` gehört dazu.
#: ``pause_simulation`` (``simulation_run.py``) setzt nur ein kooperatives
#: IPC-Flag — der OASIS-Subprozess läuft weiter und pausiert sich selbst nach
#: der laufenden Runde; die PID bleibt bis dahin gültig. Stirbt der Prozess
#: durch einen Container-/Worker-Neustart, ist ein ``paused``-Eintrag genauso
#: verwaist wie ein ``processing``-Eintrag — nur dass hier zusätzlich der
#: direkte Resume-Endpunkt (``simulation_run.py::resume_simulation``) das
#: Control-Flag blind zurücksetzt und die Registry ungeprüft auf
#: ``processing`` schaltet, ohne einen Ersatzprozess zu starten. Ohne diese
#: Ergänzung bliebe ein solcher Run für immer ein Phantom-Run.
#:
#: Entscheidung (bewusst NICHT ``resume_simulation`` selbst ändern): diese
#: Reconciliation läuft als Startup-Hook (``post_fork`` in
#: ``gunicorn.conf.py``, siehe Modul-Docstring/Finding A) VOR dem ersten von
#: gunicorn angenommenen Request. Ein verwaister ``paused``-Run wird also
#: bereits hier — vor jeder möglichen ``/resume``-Anfrage an diesen Worker —
#: auf ``failed``/``process_restart`` korrigiert; ``run_state.json`` steht
#: dabei auf ``RunnerStatus.PAUSED`` (kein Eintrag in
#: ``_TERMINAL_RUNNER_STATUSES``), fällt also regulär in den
#: "verwaist"-Zweig unten. Der Resume-Endpunkt sieht in diesem Fall den
#: bereits korrigierten ``failed``-Status und keinen echten Phantom-Run mehr.
#: ``resume_simulation`` bliebe weiterhin unsicher, wenn der Subprozess aus
#: einem ANDEREN Grund als einem Worker-Neustart stirbt (z. B. Absturz
#: während der Pause, ohne dass gunicorn neu forkt) — das ist ein separates,
#: vorbestehendes Problem des Endpunkts selbst (keine eigene Liveness-Prüfung
#: vor dem Statuswechsel) und außerhalb dieses Reconciliation-Slices.
_STALE_STATUSES = ["pending", "processing", "paused"]

#: Nur ``simulation_run`` hat eine ``process_pid`` in ``run_state.json`` und
#: damit eine verifizierbare Liveness. Andere Run-Typen (``report_generate``,
#: ``graph_build``, ...) laufen als In-Process-Threads ohne dieses Muster —
#: sie bleiben bewusst außerhalb dieses Slices (siehe Abschlussbericht).
_RUN_TYPE = "simulation_run"

#: Run-Typen, die als ``threading.Thread(daemon=True)`` IM Webprozess laufen
#: (``app/jobs/__init__.py``) und deshalb keine eigene ``process_pid`` haben.
#: Ihre Liveness haengt am Webprozess selbst — siehe ``reconcile_stale_jobs``.
_IN_PROCESS_RUN_TYPES = (
    "simulation_prepare",
    "report_generate",
    "graph_build",
    "ontology_generate",
)

_TERMINATION_REASON = "process_restart"
_ERROR_MESSAGE = "Prozess-Neustart während des Runs"

#: Terminale ``run_state.json``-Status, die NICHT wie ein verwaister Run
#: behandelt werden (Finding B / F2): ein toter Prozess ist hier kein
#: Hinweis auf einen verwaisten Run, sondern schlicht der Beweis, dass der
#: Run bereits regulär beendet wurde (``COMPLETED``) oder vom Nutzer
#: gestoppt wurde (``STOPPED``) — die RunRegistry-Sync danach ist nur (noch)
#: nicht angekommen. Eine Propagation wäre hier eine echte Falschaussage
#: (ein fremder Erfolgs-/Stop-Zustand auf einem in Wahrheit verwaisten
#: Alt-Manifest), siehe Kommentar im verwaisten-Zweig unten.
#:
#: ``RunnerStatus.FAILED`` gehört bewusst NICHT in diese Menge (F1,
#: Codex-Review Runde 5, PR #1476): anders als bei COMPLETED/STOPPED gibt es
#: hier keine Falschaussage zu vermeiden — der Verwaist-Zweig würde ein noch
#: stale Manifest ohnehin auf ``failed``/``process_restart`` setzen, also
#: exakt den Zustand, den ``run_state.json`` schon trägt. FAILED fällt
#: deshalb durch diesen Filter und wird unten wie ein verwaister Run
#: verarbeitet. Das schließt die Lücke aus PR #1476 Runde 5, Finding F1: eine
#: halb geschriebene Korrektur (Registry bereits ``failed``, aber
#: ``save_run_state`` schlägt fehl, oder umgekehrt) blieb bisher für immer
#: unangetastet, weil ``failed`` weder in ``_STALE_STATUSES`` (Registry-Seite)
#: noch — nach dem ersten halben Schritt — im verwaisten Zweig (State-Seite)
#: erneut aufgegriffen wurde.
_TERMINAL_RUNNER_STATUSES = {
    RunnerStatus.COMPLETED,
    RunnerStatus.STOPPED,
}


class ReconciliationResult(BaseModel):
    """Ergebnis eines ``reconcile_stale_runs``-Laufs."""

    model_config = ConfigDict(extra="forbid")

    reconciled_run_ids: List[str] = []
    skipped_run_ids: List[str] = []
    #: Bleibt aktuell immer leer (F2, Codex-Review Runde 3, PR #1476): ein
    #: bereits terminaler ``run_state.json``-Status wird NICHT mehr auf die
    #: Registry propagiert, weil ``run_state.json`` keine RunRegistry-
    #: ``run_id`` trägt und die Zuordnung damit nicht verifizierbar ist —
    #: solche Runs landen stattdessen in ``skipped_run_ids``. Feld bleibt im
    #: Contract, bis eine echte Run-ID-Verknüpfung existiert (Folgearbeit).
    synced_terminal_run_ids: List[str] = []


class _RunRegistryProtocol(Protocol):
    """Minimale Schnittstelle, die ``reconcile_stale_runs`` von der Registry
    braucht — erlaubt Tests, eine leichte Stub-Registry statt der echten
    dateibasierten ``RunRegistry`` zu injizieren."""

    def list_runs(self, *, statuses: List[str], run_type: str, limit: int) -> List[dict]: ...

    def update_run(self, run_id: str, **updates: Any) -> Optional[dict]: ...


def reconcile_stale_runs(
    registry: _RunRegistryProtocol,
    run_state_dir: str,
    *,
    is_pid_alive: Callable[[Optional[int]], bool] = is_process_alive,
    enabled: bool = True,
) -> ReconciliationResult:
    """Markiert verwaiste ``simulation_run``-Runs als ``failed``/``process_restart``.

    Args:
        registry: ``RunRegistry``-Instanz (oder Test-Stub mit ``list_runs``/
            ``update_run``).
        run_state_dir: Basisverzeichnis für ``run_state.json``
            (``SimulationRunner.RUN_STATE_DIR``).
        is_pid_alive: Liveness-Prüfung, Default ``process_manager.is_process_alive``
            (``os.kill(pid, 0)``-Muster). Injizierbar für Tests.
        enabled: Schaltet die Reconciliation komplett ab, wenn ``False``
            (``AGORA_STARTUP_RECONCILIATION=false``) — dann bleibt jeder
            Run unangetastet.

    Returns:
        ``ReconciliationResult`` mit den Run-IDs, die als tot markiert
        (``reconciled_run_ids``) bzw. als noch lebend übersprungen wurden
        (``skipped_run_ids``).
    """
    if not enabled:
        return ReconciliationResult()

    reconciled: List[str] = []
    skipped: List[str] = []
    synced_terminal: List[str] = []

    stale_runs = registry.list_runs(
        statuses=_STALE_STATUSES, run_type=_RUN_TYPE, limit=100_000
    )

    # F2 (Codex-Review Runde 4, PR #1476): mehrere RunRegistry-Manifeste
    # koennen dieselbe ``simulation_id`` teilen (z. B. ein verwaister Alt-Run
    # neben einem laengst abgeschlossenen Ersatzlauf, siehe Finding F1).
    # ``run_state.json`` ist ausschliesslich pro ``simulation_id`` persistiert
    # (nicht pro Registry-Manifest) — die urspruengliche Implementierung lud
    # und aktualisierte diesen Zustand PRO MANIFEST innerhalb derselben
    # Schleife: die erste Iteration schrieb ``run_state.json`` bereits auf
    # FAILED, die zweite Iteration derselben ``simulation_id`` las diesen
    # (nun terminalen) Zustand erneut und wurde vom Terminal-Zweig
    # uebersprungen, statt ebenfalls als verwaist erkannt zu werden.
    #
    # Fix: Manifeste nach ``simulation_id`` gruppieren und ``run_state.json``
    # pro Simulation genau EINMAL lesen und (falls verwaist) genau EINMAL
    # schreiben — die getroffene Entscheidung (lebend / terminal / verwaist)
    # gilt dann fuer alle Manifeste dieser Gruppe gleichermassen. Das
    # verursacht weniger Zustandsverflechtung als die Alternative (State-
    # Write zurueckstellen, bis alle Manifeste "gesehen" wurden), weil kein
    # Zwischenspeicher fuer aufgeschobene Writes noetig ist und die
    # Kernschleife weiterhin einen einzigen linearen Durchlauf macht.
    groups: Dict[Optional[str], List[dict]] = {}
    for run in stale_runs:
        run_id = run.get("run_id")
        if not run_id:
            continue
        simulation_id = (run.get("linked_ids") or {}).get("simulation_id") or run.get(
            "entity_id"
        )
        groups.setdefault(simulation_id, []).append(run)

    for simulation_id, runs in groups.items():
        state = load_run_state(simulation_id, run_state_dir) if simulation_id else None
        pid = state.process_pid if state is not None else None

        if is_pid_alive(pid):
            # Finding C (Codex-Review 2026-09-08, bewusst NICHT behoben): eine
            # lebende PID heißt nur, dass der OASIS-Subprozess überlebt hat
            # (``start_new_session=True``) — nicht, dass DIESER (frisch
            # gestartete) Worker-Prozess ihn noch verwaltet. Sein ``Popen``-
            # Objekt und sein Monitor-Thread gehörten dem alten Worker und
            # existieren hier nicht; der Run bleibt "processing", ist aber
            # nicht mehr über die API steuerbar (kein Stop/Cancel-Pfad
            # erreicht ihn). Ein automatisches Terminieren wäre riskant
            # (siehe Abschlussbericht) — daher nur lautes Logging statt
            # Prozess-Kill.
            for run in runs:
                run_id = run["run_id"]
                logger.warning(
                    "reconcile_stale_runs: run=%s sim=%s pid=%s lebt noch, wird aber "
                    "von diesem (neu gestarteten) Worker nicht mehr verwaltet — "
                    "kein Popen-Handle, kein Monitor-Thread; Run bleibt 'processing' "
                    "und ist nicht mehr über die API steuerbar",
                    run_id, simulation_id, pid,
                )
                skipped.append(run_id)
            continue

        # Finding B (Codex-Review 2026-09-08) / F2 (Codex-Review Runde 3,
        # PR #1476): ein toter Prozess heißt nicht zwangsläufig "verwaist" —
        # ``run_state.json`` kann bereits einen autoritativen ERFOLGS- oder
        # STOP-Endzustand tragen (``COMPLETED``/``STOPPED``), weil der Run
        # regulär fertig wurde oder der Nutzer ihn stoppte, und nur die
        # anschließende RunRegistry-Sync nie ankam (Prozess starb
        # dazwischen). Nur für DIESE beiden Zustände gilt die
        # Propagationssperre unten — ``FAILED`` ist seit Runde 5 (F1)
        # bewusst NICHT mehr Teil von ``_TERMINAL_RUNNER_STATUSES`` und
        # erreicht diesen Zweig gar nicht mehr (siehe Kommentar an der
        # Konstante).
        #
        # ABER: ``run_state.json``/``SimulationRunState`` ist ausschließlich
        # pro ``simulation_id`` gespeichert (siehe ``run_state_store.py``)
        # und trägt KEINE RunRegistry-``run_id``. Existieren mehrere
        # RunRegistry-Manifeste für dieselbe ``simulation_id`` — z. B. ein
        # verwaister Alt-Run neben einem längst abgeschlossenen Ersatzlauf
        # nach einem Resume (siehe Finding F1) —, ist NICHT feststellbar, zu
        # welchem der beiden Manifeste dieser eine terminale Zustand
        # tatsächlich gehört. Propagieren wäre dann stille Datenkorruption:
        # ein fremder Endzustand (z. B. COMPLETED des Ersatzlaufs) landet auf
        # dem in Wahrheit verwaisten/gescheiterten Alt-Run. Bei ``FAILED``
        # besteht dieses Korruptionsrisiko nicht — ein fremdes ``failed``
        # sagt nichts aus, was der Verwaist-Zweig für ein stale Manifest
        # nicht ohnehin selbst schreiben würde.
        #
        # Ohne verifizierbare Run-ID-Verknüpfung (aktuell nicht herstellbar)
        # wird deshalb bei COMPLETED/STOPPED NICHT propagiert — nur geloggt.
        # Der Run bleibt unangetastet (weder "completed" noch fälschlich
        # "failed"), bis eine echte Run-ID-Verknüpfung existiert
        # (Folgearbeit).
        if state is not None and state.runner_status in _TERMINAL_RUNNER_STATUSES:
            for run in runs:
                run_id = run["run_id"]
                logger.warning(
                    "reconcile_stale_runs: run=%s sim=%s pid=%s run_state.json "
                    "bereits terminal (runner_status=%s), aber ohne verifizierbare "
                    "Run-ID-Verknuepfung zu diesem Manifest (run_state.json kennt "
                    "nur simulation_id) — keine Propagation, Run bleibt "
                    "unveraendert",
                    run_id, simulation_id, pid, state.runner_status.value,
                )
                skipped.append(run_id)
            continue

        # F1 (Codex-Review Runde 5, PR #1476): ``save_run_state`` zuerst,
        # ``registry.update_run`` danach — nicht umgekehrt. Ein verwaister
        # Run wird als „korrigiert" behandelt, sobald er auch nur EINE der
        # beiden Persistenzen erreicht hat; ohne die richtige Reihenfolge
        # entstand eine Halb-Korrektur, die für immer stehen blieb:
        #
        # - Registry zuerst, dann ``save_run_state`` (alte Reihenfolge):
        #   schlägt der State-Write fehl, steht die Registry bereits auf
        #   ``failed`` (nicht mehr in ``_STALE_STATUSES``) — der Run wird nie
        #   wieder von ``list_runs`` gefunden, ``run_state.json`` bleibt aber
        #   für immer auf ``RUNNING``/``STARTING`` stehen.
        # - ``save_run_state`` zuerst (neue Reihenfolge): schlägt dieser
        #   Schritt fehl, wird ``registry.update_run`` gar nicht erst
        #   aufgerufen — die Registry bleibt unverändert auf einem
        #   ``_STALE_STATUSES``-Wert und der Run wird beim nächsten Start
        #   erneut aufgegriffen. Schlägt umgekehrt ``registry.update_run``
        #   fehl, NACHDEM ``run_state.json`` bereits FAILED trägt, greift der
        #   oben verschärfte Terminal-Zweig: ein stale Manifest mit
        #   ``FAILED``+toter PID fällt durch ``_TERMINAL_RUNNER_STATUSES``
        #   und wird beim nächsten Durchlauf erneut als verwaist erkannt und
        #   auf die Registry propagiert.
        if state is not None:
            state.runner_status = RunnerStatus.FAILED
            state.error = _ERROR_MESSAGE
            save_run_state(state, run_state_dir)

        for run in runs:
            run_id = run["run_id"]
            logger.warning(
                "reconcile_stale_runs: run=%s sim=%s pid=%s verwaist — markiere failed/%s",
                run_id, simulation_id, pid, _TERMINATION_REASON,
            )
            registry.update_run(
                run_id,
                status="failed",
                termination_reason=_TERMINATION_REASON,
                error=_ERROR_MESSAGE,
            )
            reconciled.append(run_id)

    return ReconciliationResult(
        reconciled_run_ids=reconciled,
        skipped_run_ids=skipped,
        synced_terminal_run_ids=synced_terminal,
    )



def _default_fail_simulation_state(simulation_id: str, error: str) -> None:
    """Schiebt einen auf ``PREPARING`` haengengebliebenen State nach ``FAILED``.

    Lazy importiert, damit dieses Modul von beiden Startup-Hooks aus ohne
    Flask-App-Kontext importierbar bleibt (siehe ``run_startup_reconciliation``).
    """
    from ..simulation_manager import SimulationManager, SimulationStatus

    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if state is None or state.status != SimulationStatus.PREPARING:
        return
    state.error = error
    manager._set_status(state, SimulationStatus.FAILED)


def reconcile_stale_jobs(
    registry: _RunRegistryProtocol,
    *,
    enabled: bool = True,
    owns: Callable[[Optional[Dict[str, Any]]], bool] = owns_run,
    fail_simulation_state: Optional[Callable[[str, str], None]] = None,
) -> ReconciliationResult:
    """Markiert verwaiste In-Process-Jobs als ``failed``/``process_restart``.

    Gegenstueck zu :func:`reconcile_stale_runs` fuer die Run-Typen aus
    ``_IN_PROCESS_RUN_TYPES``. Deren Slice-Grenze war bisher ausdruecklich
    gezogen (siehe Kommentar an ``_RUN_TYPE``): sie haben keine
    ``process_pid``, also gab es keine verifizierbare Liveness — und damit
    blieb ein per SIGTERM abgeschnittener Prepare-, Report- oder
    Graph-Build-Job fuer immer auf ``processing`` stehen (Issue #1472).

    Die Liveness kommt hier aus der Prozess-Identitaet im Manifest
    (``app/jobs/identity.py``): ``enqueue`` stempelt PID und ein pro Prozess
    einmaliges Token in ``metadata``, bevor der Thread startet. Traegt ein
    Manifest das Token *dieses* Prozesses, laeuft der Job noch und bleibt
    unangetastet; traegt es ein fremdes oder gar keines, ist sein Eigentuemer
    weg.

    Bewusst eine eigene Funktion statt eines weiteren Zweigs in
    ``reconcile_stale_runs``: die beiden Liveness-Modelle haben nichts
    gemeinsam — dort eine fremde Subprozess-PID, hier die Identitaet des
    eigenen Prozesses —, und die dortigen Invarianten (Gruppierung nach
    ``simulation_id``, Terminal-Propagationssperre, Schreibreihenfolge) haengen
    alle am ``run_state.json``, das es hier gar nicht gibt.

    Kein neuer Statuswert: ``failed``/``process_restart`` ist derselbe
    Endzustand, den ``reconcile_stale_runs`` fuer denselben Sachverhalt
    schreibt, und ``PREPARING -> FAILED`` ist im FSM bereits erlaubt. Ein
    eigener ``interrupted``-Status haette Frontend, FSM und jeden Consumer
    beruehrt, ohne mehr auszusagen als der Grund es schon tut.

    Args:
        registry: ``RunRegistry``-Instanz (oder Stub mit ``list_runs``/``update_run``).
        enabled: ``False`` laesst jeden Run unangetastet
            (``AGORA_STARTUP_RECONCILIATION=false``).
        owns: Liveness-Pruefung gegen die Manifest-Metadaten, injizierbar.
        fail_simulation_state: Wird fuer ``simulation_prepare`` mit
            ``(simulation_id, error)`` gerufen, damit auch der
            ``SimulationState`` aus ``preparing`` herauskommt. ``None``
            verwendet die Default-Implementierung.
    """
    if not enabled:
        return ReconciliationResult()

    on_state = (
        _default_fail_simulation_state
        if fail_simulation_state is None
        else fail_simulation_state
    )
    reconciled: List[str] = []
    skipped: List[str] = []

    for run_type in _IN_PROCESS_RUN_TYPES:
        for run in registry.list_runs(
            statuses=_STALE_STATUSES, run_type=run_type, limit=100_000
        ):
            run_id = run.get("run_id")
            if not run_id:
                continue
            if owns(run.get("metadata") or {}):
                logger.debug(
                    "reconcile_stale_jobs: run=%s (%s) laeuft in diesem Prozess",
                    run_id, run_type,
                )
                skipped.append(run_id)
                continue

            logger.warning(
                "reconcile_stale_jobs: run=%s (%s) verwaist — markiere failed/%s",
                run_id, run_type, _TERMINATION_REASON,
            )
            registry.update_run(
                run_id,
                status="failed",
                termination_reason=_TERMINATION_REASON,
                error=_ERROR_MESSAGE,
            )
            reconciled.append(run_id)

            if run_type != "simulation_prepare":
                continue
            simulation_id = (run.get("linked_ids") or {}).get("simulation_id") or run.get(
                "entity_id"
            )
            if not simulation_id:
                continue
            try:
                on_state(simulation_id, _ERROR_MESSAGE)
            except Exception:  # noqa: BLE001 — das Manifest ist bereits korrigiert
                logger.error(
                    "reconcile_stale_jobs: SimulationState fuer %s nicht "
                    "korrigierbar — Manifest %s steht bereits auf failed",
                    simulation_id, run_id, exc_info=True,
                )

    return ReconciliationResult(reconciled_run_ids=reconciled, skipped_run_ids=skipped)


def run_startup_reconciliation(
    *, enabled: bool = True, should_log_startup: bool = True
) -> ReconciliationResult:
    """Best-effort-Trigger für :func:`reconcile_stale_runs`.

    Gemeinsamer Einhängepunkt für ``app/__init__.py::create_app`` (einziger
    Startup-Hook in Entwicklungs-/Testbetrieb ohne gunicorn) und
    ``gunicorn.conf.py::post_fork`` (kanonischer Einhängepunkt in
    Produktion, siehe Modul-Docstring / Finding A). Löst Config-Flag-Check
    und Fehlerbehandlung aus dem alten ``create_app``-Inline-Block heraus,
    damit beide Aufrufer exakt dasselbe Verhalten bekommen: ein Fehler in
    der Reconciliation darf weder den App-Start noch den Worker-Start
    verhindern.

    Args:
        enabled: Resultat der ``AGORA_STARTUP_RECONCILIATION``-Prüfung des
            Aufrufers (``app.config.get(...)`` bzw. ``Config.
            AGORA_STARTUP_RECONCILIATION`` — dieses Modul importiert keine
            Flask-/Config-Objekte, um von beiden Aufrufern unabhängig zu
            bleiben).
        should_log_startup: Unterdrückt das Zusammenfassungs-Log (deckt sich
            mit dem bisherigen ``should_log_startup``-Gate in ``create_app``,
            z. B. für Worker-Prozesse mit reduzierter Log-Verbosity).

    Returns:
        ``ReconciliationResult()`` (leer) wenn deaktiviert oder wenn die
        Reconciliation selbst fehlschlägt — der Fehler ist dann bereits
        geloggt.
    """
    if not enabled:
        return ReconciliationResult()

    try:
        from ..run_registry import RunRegistry
        from ..simulation_runner import SimulationRunner

        registry = RunRegistry()
        result = reconcile_stale_runs(registry, SimulationRunner.RUN_STATE_DIR)
        # Issue #1472: dieselbe Runde fuer die In-Process-Jobs. Eigener
        # Aufruf statt eines Zweigs in reconcile_stale_runs — die
        # Liveness-Modelle haben nichts gemeinsam (dort eine fremde
        # Subprozess-PID, hier die Identitaet dieses Prozesses).
        job_result = reconcile_stale_jobs(registry)
        result = ReconciliationResult(
            reconciled_run_ids=[*result.reconciled_run_ids, *job_result.reconciled_run_ids],
            skipped_run_ids=[*result.skipped_run_ids, *job_result.skipped_run_ids],
            synced_terminal_run_ids=result.synced_terminal_run_ids,
        )
        if should_log_startup:
            logger.info(
                "Startup-Reconciliation: %d Run(s) als process_restart markiert "
                "(davon %d In-Process-Jobs), %d terminal synchronisiert, "
                "%d unveraendert",
                len(result.reconciled_run_ids),
                len(job_result.reconciled_run_ids),
                len(result.synced_terminal_run_ids),
                len(result.skipped_run_ids),
            )
        return result
    except Exception:  # noqa: BLE001 — App-/Worker-Start darf nie an der Reconciliation scheitern
        logger.error(
            "Startup-Reconciliation fehlgeschlagen — Start läuft trotzdem weiter",
            exc_info=True,
        )
        return ReconciliationResult()
