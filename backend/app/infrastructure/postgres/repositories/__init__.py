"""PostgreSQL-Adapter der Repository-Ports (docs/plans/supabase.md §5, §12).

Die Ports liegen in ``app/repositories``, die Adapter bei ihrer Technik. Ein
Consumer sieht keinen von beiden — er bekommt seinen Adapter aus der Factory
des Ports.
"""

from .llm_profile_repository import PostgresLlmProfileRepository

__all__ = ["PostgresLlmProfileRepository"]
