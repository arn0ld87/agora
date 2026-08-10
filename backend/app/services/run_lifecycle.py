"""Run-Lifecycle — zentrale Zustandsführung für RunRegistry-Runs.

Invariante: ein Run, der als ``pending`` angelegt wurde, verlässt jeden
Ausgang des Anlage-Fensters auf einem Endzustand. Kein Abbruchpfad darf
einen Phantom-Run hinterlassen, der dauerhaft ``pending`` in der Liste
steht (#841, #1094, #1176/#1183 — drei Anläufe am selben Symptom, weil
das Muster an mehreren Stellen handgeschrieben war).

Gekapselte Semantik:

* **#841 — Task-Reihenfolge:** ist ein Task an den Run gekoppelt, läuft
  ``fail_task()`` zuerst (setzt per ``sync_task()`` eine generische
  Meldung auf den Run zurück) und der detaillierte ``update_run()``-Aufruf
  zuletzt, sonst überschreibt ``sync_task()`` die Meldung.
* **#844 — Persistenz ist prüfbar:** ``update_run()`` liefert ``None``,
  wenn das Run-Manifest verschwunden ist, oder wirft eine I/O-Exception.
  Beide Fälle dürfen nicht wie eine erfolgreich persistierte Markierung
  aussehen — sie werden als :class:`RunPersistenceError` sichtbar.
* **#1183 — BaseException-Netz:** ein Worker-Timeout erreicht den Handler
  als Signal-Ableitung (``SystemExit``); ``except Exception`` ließe genau
  den Fall durch, der die Phantom-Runs erzeugt hat.

Der Kontextmanager markiert und **re-raist immer** — er schluckt keine
Exception und baut keine HTTP-Antworten. Antwortbau (``json_error``,
Rejection-Objekte) bleibt Sache der API-Schicht.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: Exceptions können unter diesem Attribut eine sprechende failed-Meldung
#: für den Run mitführen (z. B. Rejection-Klassen der API-Schicht). Fehlt
#: es, greift das ``failure_message``-Template von :meth:`RunLifecycle.begin`.
FAILURE_MESSAGE_ATTR = "run_failure_message"


class RunPersistenceError(RuntimeError):
    """Ein Statusübergang wurde NICHT persistiert (Issue #844).

    Wird geworfen, wenn ``update_run()`` ``None`` liefert (Run-Manifest
    verschwunden) oder eine Exception wirft. Der Aufrufer darf den Vorgang
    dann nicht als sauber abgeschlossen behandeln — typischerweise wird
    daraus eine 500-Antwort statt der regulären Ablehnung.
    """

    def __init__(self, run_id: str, cause: Optional[BaseException] = None):
        self.run_id = run_id
        self.cause = cause
        # Bewusst ohne Ursachen-Detail: die Meldung kann über generische
        # API-Fehlerpfade beim Client landen — Pfade/IO-Details gehören ins
        # Log (siehe Aufrufstellen), nicht in die Response.
        super().__init__(f"Statusübergang für Run {run_id} wurde nicht persistiert")


class RunLifecycle:
    """Kontextmanager um das Anlage-Fenster eines RunRegistry-Runs.

    ::

        with RunLifecycle.begin(run_registry, "simulation_run", sim_id,
                                failure_message="Simulation start failed: {exc_type}",
                                linked_ids={...}, metadata={...}) as run:
            task_id = task_manager.create_task(...)
            run.attach_task(task_manager, task_id)
            ...  # alles, was den Run verwaisen lassen könnte
            run.succeed(status="processing", message="Simulation run started")

    * Eintritt: legt den Run mit ``status="pending"`` an.
    * Sauberes Blockende ohne :meth:`succeed`: der Run bleibt ``pending``
      (Übergabe an einen Worker, der die Terminalzustände besitzt).
    * Jede ``BaseException`` im Block: Run wird ``failed`` markiert
      (strikt, #844) und die Exception unverändert re-raist.
    """

    def __init__(
        self,
        registry: Any,
        run_type: str,
        entity_id: str,
        *,
        failure_message: Optional[str] = None,
        **create_kwargs: Any,
    ) -> None:
        self._registry = registry
        self._run_type = run_type
        self._entity_id = entity_id
        self._failure_message = failure_message
        self._create_kwargs = create_kwargs
        self._task_manager: Any = None
        self._task_id: Optional[str] = None
        self.record: dict[str, Any] = {}
        self.run_id: str = ""

    @classmethod
    def begin(
        cls,
        registry: Any,
        run_type: str,
        entity_id: str,
        *,
        failure_message: Optional[str] = None,
        **create_kwargs: Any,
    ) -> "RunLifecycle":
        """Lifecycle für einen neuen Run bauen (``status`` wird immer ``pending``)."""
        create_kwargs.pop("status", None)
        return cls(
            registry,
            run_type,
            entity_id,
            failure_message=failure_message,
            **create_kwargs,
        )

    def __enter__(self) -> "RunLifecycle":
        self.record = self._registry.create_run(
            self._run_type,
            self._entity_id,
            status="pending",
            **self._create_kwargs,
        )
        self.run_id = self.record["run_id"]
        return self

    def attach_task(self, task_manager: Any, task_id: str) -> None:
        """Task an den Run koppeln — bei Fehlern gilt die #841-Reihenfolge."""
        self._task_manager = task_manager
        self._task_id = task_id

    def succeed(self, *, status: str = "processing", **updates: Any) -> dict[str, Any]:
        """Erfolgs-Übergang, strikt persistiert (#844) — wirft :class:`RunPersistenceError`."""
        return self._strict_update(status=status, **updates)

    def _strict_update(self, **updates: Any) -> dict[str, Any]:
        try:
            updated = self._registry.update_run(self.run_id, **updates)
        except Exception as exc:  # noqa: BLE001 — Persistenzfehler wird typisiert weitergereicht
            logger.error(
                "Persistenzfehler beim Statusübergang von run_id=%s: %s", self.run_id, exc
            )
            raise RunPersistenceError(self.run_id, exc) from exc
        if updated is None:
            logger.error(
                "Persistenzfehler beim Statusübergang von run_id=%s: %s",
                self.run_id,
                "update_run() lieferte None (Run-Manifest existiert nicht mehr)",
            )
            raise RunPersistenceError(self.run_id)
        return updated

    def _failure_text(self, exc: BaseException) -> str:
        attr_message = getattr(exc, FAILURE_MESSAGE_ATTR, None)
        if attr_message:
            return str(attr_message)
        template = self._failure_message or "{run_type} failed: {exc_type}"
        return template.format(run_type=self._run_type, exc_type=type(exc).__name__)

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is None:
            return False

        if isinstance(exc, RunPersistenceError) and exc.run_id == self.run_id:
            # Bereits ein Persistenzproblem dieses Runs (z. B. aus succeed()) —
            # ein weiterer Markierungsversuch würde nur denselben Fehler doppeln.
            return False

        message = self._failure_text(exc)

        if self._task_manager is not None and self._task_id is not None:
            try:
                self._task_manager.fail_task(self._task_id, message)
            except Exception:  # noqa: BLE001 — Task-Markierung ist best-effort (#841)
                logger.warning(
                    "fail_task(%s) schlug beim failed-Markieren von Run %s fehl",
                    self._task_id,
                    self.run_id,
                    exc_info=True,
                )

        try:
            updated = self._registry.update_run(
                self.run_id, status="failed", message=message, error=message
            )
        except Exception as persist_exc:  # noqa: BLE001 — siehe #844
            logger.error(
                "Persistenzfehler beim Markieren von run_id=%s als failed: %s",
                self.run_id,
                persist_exc,
            )
            raise RunPersistenceError(self.run_id, persist_exc) from exc
        if updated is None:
            logger.error(
                "Persistenzfehler beim Markieren von run_id=%s als failed: %s",
                self.run_id,
                "update_run() lieferte None (Run-Manifest existiert nicht mehr)",
            )
            raise RunPersistenceError(self.run_id) from exc

        return False
