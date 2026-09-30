"""SimActionRecord / SimActionPage / RoundSummary — Layer-0-Contracts fuer das
Simulations-Aktionsprotokoll (Slice UI-2a, #1713).

Verbindliche Vertraege fuer ``GET /api/simulation/<id>/actions`` (paginiert)
und ``GET /api/simulation/<id>/rounds``. Die interne Laufzeit-Datenstruktur
bleibt ``AgentAction`` (dataclass, ``app.services.sim.run_state_store``) —
dieser Contract ist die API-Grenze, in die ``AgentAction`` konvertiert wird,
nicht ihr Ersatz (kein Cross-Layer-Refactor des IPC-Handlers/Loggers).

``RoundSummary`` hier ist ein anderer Typ als die gleichnamige Dataclass in
``run_state_store.py`` (Laufzeitzustand mit Rohaktionen) — dieser Contract
ist die aggregierte, gerundete API-Antwort fuer die Runden-Ansicht.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.post_event_contract import Platform
from app.contracts.role_leakage_contract import ConflictReason

_STRICT = ConfigDict(extra="forbid")


class SimActionType(str, Enum):
    """Bekannte Aktionsarten aus dem OASIS-Trace (``oasis_action_ingest.ACTION_TYPE_MAP``).

    ``OTHER`` faengt zukuenftige/unbekannte Werte aus Altlaeufen ab, damit ein
    einzelner unerwarteter Log-Eintrag nicht die gesamte Seite ablehnt.
    """

    CREATE_POST = "CREATE_POST"
    CREATE_COMMENT = "CREATE_COMMENT"
    LIKE_POST = "LIKE_POST"
    DISLIKE_POST = "DISLIKE_POST"
    LIKE_COMMENT = "LIKE_COMMENT"
    DISLIKE_COMMENT = "DISLIKE_COMMENT"
    REPOST = "REPOST"
    QUOTE_POST = "QUOTE_POST"
    FOLLOW = "FOLLOW"
    MUTE = "MUTE"
    SEARCH_POSTS = "SEARCH_POSTS"
    SEARCH_USER = "SEARCH_USER"
    TREND = "TREND"
    REFRESH = "REFRESH"
    DO_NOTHING = "DO_NOTHING"
    INTERVIEW = "INTERVIEW"
    OTHER = "OTHER"


class SimActionRecord(BaseModel):
    """Eine einzelne protokollierte Simulationsaktion (API-Grenze)."""

    model_config = _STRICT

    round_num: int = Field(..., ge=0)
    sim_time: datetime | None = Field(
        default=None,
        description="Simulierte Agenten-Wallclock. None bei Alt-Aktionen ohne Sim-Zeit.",
    )
    timestamp: datetime
    platform: Platform
    agent_id: str = Field(..., min_length=1)
    agent_name: str = Field(..., min_length=1)
    action_type: SimActionType
    target_post_id: str | None = None
    target_comment_id: str | None = None
    target_agent_id: str | None = None
    target_agent_name: str | None = None
    content: str | None = None
    success: bool = True
    role_conflict: ConflictReason | None = None


class SimActionPage(BaseModel):
    """Cursor-paginierte Antwort fuer ``GET /api/simulation/<id>/actions``."""

    model_config = _STRICT

    items: list[SimActionRecord]
    next_cursor: str | None = Field(
        default=None,
        description="Opakes Cursor-Token fuer die naechste Seite. None am Ende der Liste.",
    )


class RoundSummary(BaseModel):
    """Aggregierte Aktionsbilanz einer Sim-Runde je Plattform.

    ``action_counts`` ist bewusst ein offenes Mapping (Enum-Wert -> Anzahl)
    statt Einzelfelder je Aktionsart — neue Aktionsarten brauchen dann keine
    Vertragsaenderung.
    """

    model_config = _STRICT

    round_num: int = Field(..., ge=0)
    platform: Platform
    action_counts: dict[SimActionType, int] = Field(default_factory=dict)


__all__ = [
    "RoundSummary",
    "SimActionPage",
    "SimActionRecord",
    "SimActionType",
]
