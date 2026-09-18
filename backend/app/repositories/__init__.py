"""Repository-Ports (docs/plans/supabase.md §12).

Ein Port je Domaene, als ``Protocol``. Die Anwendung spricht gegen den Port,
die Adapter liegen bei ihrer Technik: der SQLite-Adapter neben dem bestehenden
Store unter ``app/services``, der PostgreSQL-Adapter spaeter unter
``app/infrastructure/postgres/repositories`` (§5).

Der Sinn ist nicht die Abstraktion an sich, sondern der Umstiegspfad: solange
nur ein Adapter existiert, ist ein Port eine Zeile Zusatzarbeit; sobald ein
zweiter dazukommt, ist er die Stelle, an der sich beide gegeneinander
austauschen lassen, ohne dass ein Consumer davon erfaehrt.
"""

from .llm_profile_repository import (
    LlmProfileBackendUnavailable,
    LlmProfileRepository,
    get_llm_profile_repository,
)

__all__ = [
    "LlmProfileBackendUnavailable",
    "LlmProfileRepository",
    "get_llm_profile_repository",
]
