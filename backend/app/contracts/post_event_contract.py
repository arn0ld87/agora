"""PostCreatedEvent — Layer-0-Contract für Live-Sim-Feed.

Slice FE-Redesign-5-pre · 2026-05-15

Wird emittiert nach jedem CREATE_POST-Action im OASIS-Runner. Geht via
event_bus + simulation_stream als SSE-Frame ``event: post_created`` ans
Frontend. Slice 5 (Dual-Column Sim-Feed) konsumiert.

Wording-Glossar v1: ``is_simulated=True`` ist Pflicht-Marker für alle
OASIS-emittierten Posts. Frontend rendert SIM-Badge. Kein "prediction".
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Platform(str, Enum):
    """Plattform-Enum für Dual-Column-Routing.

    Eng halten — andere Channels (Mastodon, Threads) brauchen ADR + Slice.
    """

    REDDIT = "reddit"
    TWITTER = "twitter"


class VoiceRegister(str, Enum):
    """Voice-Register aus oasis_profile_generator (Sub-Slice 10).

    Frontend rendert Badge in PersonaAvatar.
    """

    FORMAL = "formal"
    CASUAL = "casual"
    JUGENDSPRACHE = "jugendsprache"


class PostCreatedEvent(BaseModel):
    """SSE-Frame für einen einzelnen Post-Action des OASIS-Runners."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: Literal["post_created"] = "post_created"
    simulation_id: str = Field(..., min_length=1)
    post_id: str = Field(..., min_length=1)
    parent_post_id: str | None = None
    platform: Platform
    persona_id: str = Field(..., min_length=1)
    voice_register: VoiceRegister
    is_simulated: bool = True
    body: str = Field(..., min_length=1)
    timestamp: datetime


__all__ = [
    "Platform",
    "PostCreatedEvent",
    "VoiceRegister",
]
