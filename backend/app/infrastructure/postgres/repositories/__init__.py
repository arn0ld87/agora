"""PostgreSQL-Adapter der Repository-Ports (docs/plans/supabase.md §5, §12).

Die Ports liegen in ``app/repositories``, die Adapter bei ihrer Technik. Ein
Consumer sieht keinen von beiden — er bekommt seinen Adapter aus der Factory
des Ports.
"""

from .llm_profile_repository import PostgresLlmProfileRepository
from .project_repository import PostgresProjectRepository, ProjectNotStored
from .run_repository import PostgresRunRepository, RunSimulationMissing
from .simulation_repository import (
    PostgresSimulationRepository,
    SimulationProjectMissing,
)

__all__ = [
    "PostgresLlmProfileRepository",
    "PostgresProjectRepository",
    "PostgresRunRepository",
    "PostgresSimulationRepository",
    "ProjectNotStored",
    "RunSimulationMissing",
    "SimulationProjectMissing",
]
