"""Kennzahlen "Simulation lebt" (Epic #1713 Slice S0).

Kein API-Endpoint, kein Zod-Spiegel: ``backend/scripts/sim_liveness_metrics.py``
ist ein Operator-CLI-Skript (Aufruf via ``docker exec`` auf einem
Simulations-Run-Verzeichnis, siehe ``docs/runbooks/simulation-liveness.md``)
und gibt dieses Modell als JSON auf stdout aus. Das JSON-Schema wird trotzdem
via ``dump_schemas`` gerendert (Contracts-first-Konvention, Diff-Nachweis bei
Feldaenderungen), aber es gibt keinen Frontend-Konsumenten, der einen
TypeScript/Zod-Spiegel bräuchte.

Alle L1-L10-Kennzahlen sind ``float | int | None``: ``None`` bedeutet "aus
den vorliegenden Logs nicht bestimmbar" (z. B. kein ``--seed`` fuer L7, keine
Runden fuer L2) — niemals stillschweigend 0. Der Grund landet in
``data_quality_notes``.

Diese Kennzahlen belegen **Diskursaktivität** in der Simulation (wird
ueberhaupt reagiert, repostet, widersprochen?), keine Verhaltensvorhersage
und keine Aussage ueber reale Stakeholder — siehe ADR-0002 / CONTEXT.md.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class PlatformLiveness(BaseModel):
    """Kennzahlen fuer eine einzelne Plattform (``twitter``/``reddit``) oder
    die ueber alle Plattformen aggregierte Sicht (``platform="gesamt"``).

    Definitionen (siehe ``docs/runbooks/simulation-liveness.md`` fuer
    Zielwerte und Herleitung):

    - L1 ``actions_per_agent_round``: reale Aktionen (ohne Startposts aus
      Runde 0, ``DO_NOTHING``, ``REFRESH``, ``SIGN_UP``) geteilt durch
      (Agentenzahl * abgeschlossene Runden).
    - L2 ``active_agent_share_median``: Median je Runde von
      (aktive Agenten in dieser Runde / Agentenzahl). "Aktiv" = mindestens
      eine geloggte Aktion (inkl. ``DO_NOTHING``) in dieser Runde.
    - L3 ``own_post_share``: (``CREATE_POST`` + ``QUOTE_POST``, ohne
      Startposts) / (``CREATE_POST`` + ``CREATE_COMMENT`` + ``QUOTE_POST`` +
      ``REPOST``, ohne Startposts).
    - L4 ``mutual_pair_share``: gerichteter Akteur-Reaktionsgraph (Kante
      Akteur -> Zielautor, Ziel ueber
      ``post_id``/``comment_id``/``quoted_id``/``reposted_id`` aufgeloest).
      Paare mit Kanten in beide Richtungen / Paare mit mindestens einer
      Kante. ``max_chain_length``: laengste Beitrags-Antwortkette (nicht der
      Agentengraph) — jeder inhaltliche Beitrag (``CREATE_POST``/
      ``CREATE_COMMENT``/``QUOTE_POST``/``REPOST``) referenziert hoechstens
      einen frueheren Beitrag ueber
      ``post_id``/``comment_id``/``quoted_id``/``reposted_id`` bzw.
      ``original_post_id``; Kantenzahl der laengsten Kette in diesem
      Wald/DAG.
    - L5 ``rejection_share``: ``DISLIKE_POST`` + ``DISLIKE_COMMENT`` /
      alle Like-/Dislike-Aktionen. ``contra_reply_share`` bleibt in diesem
      Slice ``None`` (braeuchte Stance-/Sentiment-Klassifikation, out of
      scope) — immer mit Note.
    - L7 ``seed_echo_share``: Anteil eigener Post-/Quote-Aktionen (ohne
      Startposts), deren Inhalt eine Zahl aus dem Seed-Dokument woertlich
      oder eine woertliche Tokenfolge von mindestens 8 Woertern aus dem Seed
      enthaelt. Nur mit ``--seed``, sonst ``None``.
    - L8 ``duplicate_log_lines`` / ``round_fill_share``: Byte-identische
      Log-Zeilen (Altlauf-Indikator, siehe #1713 Slice S1) bzw. Anteil der
      Runden 1..max mit vollstaendigem ``round_start``/``round_end``-Paar.
    """

    model_config = _STRICT

    platform: str

    actions_per_agent_round: float | None = None
    active_agent_share_median: float | None = None
    own_post_share: float | None = None
    mutual_pair_share: float | None = None
    max_chain_length: int | None = None
    rejection_share: float | None = None
    contra_reply_share: float | None = None
    seed_echo_share: float | None = None
    duplicate_log_lines: int | None = None
    round_fill_share: float | None = None

    action_type_counts: dict[str, int] = Field(default_factory=dict)
    data_quality_notes: list[str] = Field(default_factory=list)


class SimulationLivenessReport(BaseModel):
    """Ergebnis von ``sim_liveness_metrics.py <run_dir>``."""

    model_config = _STRICT

    sim_id: str
    platforms: list[str]
    agent_count: int
    rounds_completed: int
    runner_status: str
    wall_clock_seconds: float | None = None

    per_platform: dict[str, PlatformLiveness] = Field(default_factory=dict)
    overall: PlatformLiveness
