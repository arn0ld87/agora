"""PostCreatedEvent — Layer-0-Contract für Live-Sim-Feed.

Slice FE-Redesign-5-pre · 2026-05-15
Phase B · 2026-05-15 — sentiment + score Felder ergänzt.

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

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    sentiment: float | None = Field(
        default=None,
        description="Sentiment-Score -1.0 (negativ) bis 1.0 (positiv). None wenn Sentiment-Service nicht aktiv.",
    )
    score: int = Field(
        default=0,
        description="Voting-Score (Reddit-Pattern). Twitter-Posts haben kein Voting → 0.",
    )

    @field_validator("sentiment")
    @classmethod
    def sentiment_in_range(cls, v: float | None) -> float | None:
        if v is not None and not (-1.0 <= v <= 1.0):
            raise ValueError(f"sentiment muss zwischen -1.0 und 1.0 liegen, erhalten: {v}")
        return v


__all__ = [
    "Platform",
    "PostCreatedEvent",
    "VoiceRegister",
]
