"""Pagination-Utilities für API-Endpunkte.

Stellt clamp_int() und Standard-Konstanten für Limit/Offset-Parameter bereit,
um inkonsistente Request-Werte sicher auf einen gültigen Bereich zu begrenzen.
"""
from __future__ import annotations

DEFAULT_LIMIT: int = 100
MAX_LIMIT: int = 500


def clamp_int(
    value: int | None,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Begrenzt einen Integer-Wert auf [minimum, maximum].

    Gibt ``default`` zurück, wenn ``value`` None ist.

    Args:
        value:   Eingabewert (z. B. aus ``request.args.get(..., type=int)``).
        default: Rückgabewert, wenn ``value`` None ist.
        minimum: Untere Schranke (inklusive).
        maximum: Obere Schranke (inklusive).

    Returns:
        Geclampter Integer im Bereich [minimum, maximum].
    """
    if value is None:
        return default
    return max(minimum, min(value, maximum))
