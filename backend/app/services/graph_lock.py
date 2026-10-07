"""Abgeleitete Sperre für Graphen (Issue #1808, ADR-0022 §6).

Ein Graph ist gesperrt, sobald eine Simulation sein Projekt **oder** seine
``graph_id`` verwendet. Die Sperre ist kein Feld, sondern wird bei jeder
Abfrage aus dem Bestand abgeleitet: ein zweiter Zustand könnte vom
tatsächlichen Gebrauch abweichen, ein abgeleiteter kann das nicht.

Kosten: Die Ermittlung scannt die Projekte (um die Projekte zu finden, die
den Graphen tragen) und alle Simulationsdatensätze (ein ``list()``-Aufruf des
Repository-Ports, kein Aufruf je Projekt). Beides sind Metadaten, keine
Artefakte; bei einem Einzelnutzer-Bestand ist das billig. Wer das Projekt
schon kennt (die Projekt-Endpunkte), reicht es zusätzlich über
``project_ids`` herein; es zählt dann auch, wenn sein ``graph_id``-Eintrag
bereits zurückgesetzt wurde.

Lässt sich der Bestand nicht lesen, wird der Fehler **nicht** verschluckt:
eine Sperre, die bei einem Lesefehler still „frei“ meldet, wäre keine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Iterable, Optional

from ..contracts.graph_edit_contract import GraphLockState, GraphLockUser
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..contracts.project_contract import Project
    from ..contracts.simulation_record_contract import SimulationRecord
    from ..repositories.simulation_repository import SimulationRepository

logger = get_logger("agora.graph_lock")

# Obergrenze für den Projekt-Scan. ``ProjectManager.list_projects`` kennt
# nur ein Limit, kein „alle“.
_PROJECT_SCAN_LIMIT = 100_000


class GraphLockedError(Exception):
    """Der Graph wird von mindestens einer Simulation verwendet."""

    def __init__(self, state: GraphLockState) -> None:
        super().__init__(f"Graph {state.graph_id} ist gesperrt")
        self.state = state


def _default_repository() -> "SimulationRepository":
    from ..repositories.simulation_repository import get_simulation_repository
    from .simulation_manager import SimulationManager

    # Derselbe Ablageort wie beim Schreibpfad (``SimulationManager``): ohne
    # ``simulations_dir`` zaehlt der Dateiadapter nur seine instanzlokalen
    # ``_known_ids`` — eine frische Instanz sieht dann niemanden und die
    # abgeleitete Sperre meldet still „frei“ (#1808).
    return get_simulation_repository(
        simulations_dir=SimulationManager.SIMULATION_DATA_DIR,
    )


def _default_project_lister() -> list["Project"]:
    from ..models.project import ProjectManager

    return ProjectManager.list_projects(limit=_PROJECT_SCAN_LIMIT)


def _to_user(record: "SimulationRecord") -> GraphLockUser:
    return GraphLockUser(
        simulation_id=record.simulation_id,
        status=record.status or "",
        project_id=record.project_id or "",
        branch_name=record.branch_name,
    )


def get_graph_lock_state(
    graph_id: str,
    *,
    project_ids: Iterable[str] = (),
    repository: Optional["SimulationRepository"] = None,
    project_lister: Optional[Callable[[], Iterable["Project"]]] = None,
) -> GraphLockState:
    """Sperrzustand für ``graph_id`` (und die angegebenen Projekte).

    ``project_ids`` sind zusätzliche Projekte, die als Träger des Graphen
    gelten (die Projekt-Endpunkte kennen ihr Projekt). Die Projekte, deren
    ``graph_id`` dem Graphen entspricht, werden zusätzlich selbst ermittelt.
    """
    carrier_projects = {pid for pid in project_ids if pid}
    lister = project_lister or _default_project_lister
    for project in lister() if graph_id else ():
        if getattr(project, "graph_id", None) == graph_id and project.project_id:
            carrier_projects.add(project.project_id)

    repo = repository or _default_repository()
    users = [
        _to_user(record)
        for record in repo.list()
        if (graph_id and record.graph_id == graph_id)
        or (record.project_id and record.project_id in carrier_projects)
    ]
    users.sort(key=lambda user: user.simulation_id)
    return GraphLockState(graph_id=graph_id, locked=bool(users), used_by=users)


def ensure_graph_unlocked(
    graph_id: str,
    *,
    project_ids: Iterable[str] = (),
    repository: Optional["SimulationRepository"] = None,
    project_lister: Optional[Callable[[], Iterable["Project"]]] = None,
) -> None:
    """Wirft ``GraphLockedError``, wenn eine Simulation den Graphen verwendet."""
    state = get_graph_lock_state(
        graph_id,
        project_ids=project_ids,
        repository=repository,
        project_lister=project_lister,
    )
    if state.locked:
        logger.info(
            "Schreibzugriff auf gesperrten Graphen abgelehnt (graph=%s, simulationen=%d)",
            graph_id,
            len(state.used_by),
        )
        raise GraphLockedError(state)


__all__ = ["GraphLockedError", "get_graph_lock_state", "ensure_graph_unlocked"]
