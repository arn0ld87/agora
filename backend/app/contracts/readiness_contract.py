"""Vertrag für den PostgreSQL-Check von `/readyz` (Issue #1581, docs/plans/supabase.md §29).

`/readyz` (`backend/app/readiness.py`) liefert seit Beginn pro Abhängigkeit
einen Eintrag der Form ``{"ok": bool, "detail": str}`` — dieser Vertrag ändert
sich mit diesem Issue nicht und hat deshalb (noch) kein eigenes Pydantic-Modell.

Der neue ``postgres``-Check trägt zusätzlich ein maschinenlesbares ``state``:

* ``disabled``     — kein ``AGORA_*_BACKEND`` steht auf ``postgres``. Es wird
  keine Verbindung aufgebaut; `/readyz` wird dadurch NICHT rot (``ok=True``).
* ``ok``           — mindestens ein Backend ist aktiv, `SELECT 1` gelingt.
* ``unavailable``  — mindestens ein Backend ist aktiv, die Probe schlägt fehl.
  `/readyz` wird dadurch rot (``ok=False`` → HTTP 503).

``detail`` ist in jedem Zweig generisch: psycopg-Fehlertexte tragen häufig
Host, Port, User oder Datenbanknamen im Klartext — das gehört ins Log
(`backend/app/readiness.py::_check_postgres`), nie in die Antwort.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .embedding_contract import EmbeddingLegacyDivergence


class PostgresReadinessCheck(BaseModel):
    """Ein Eintrag im ``postgres``-Schlüssel der `/readyz`-Antwort."""

    model_config = ConfigDict(extra='forbid')

    ok: bool
    detail: str
    state: Literal['ok', 'unavailable', 'disabled']


class EmbeddingConfigReadinessCheck(BaseModel):
    """Ein Eintrag im ``embedding_config``-Schlüssel der `/readyz`-Antwort (#1417).

    Ergänzt das bisherige ``{ok, detail}``-Format (weiterhin in Kraft für die
    übrigen Checks) um ein maschinenlesbares ``state`` und — im Konfliktfall —
    beide Vergleichswerte:

    * ``ok``            — ``EMBEDDING_MODEL``/``VECTOR_DIM`` sind intern
      konsistent, UND falls eine aktive Store-Konfiguration existiert,
      stimmt sie mit ihnen überein. ``store``/``env`` bleiben ``None``.
    * ``misconfigured``  — ``EMBEDDING_MODEL``/``VECTOR_DIM`` fehlen oder
      sind bereits intern inkonsistent (unabhängig vom Store).
    * ``degraded``       — eine aktive Store-Konfiguration existiert und
      weicht in Provider, Modell oder Dimension von ``Config.EMBEDDING_*``
      ab. Maintainer-Entscheidung (2026-09): der Konflikt wird gemeldet,
      nichts wird automatisch übernommen — der Store bleibt die Wahrheit.
      ``store``/``env`` tragen beide Werte.
    """

    model_config = ConfigDict(extra='forbid')

    ok: bool
    detail: str
    state: Literal['ok', 'misconfigured', 'degraded']
    store: EmbeddingLegacyDivergence | None = None
    env: EmbeddingLegacyDivergence | None = None
