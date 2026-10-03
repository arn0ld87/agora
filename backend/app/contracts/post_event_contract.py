"""PostCreatedEvent — Layer-0-Contract für Live-Sim-Feed.

Slice FE-Redesign-5-pre · 2026-05-15
Phase B · 2026-05-15 — score-Feld ergänzt.
2026-08-11 — ``sentiment`` entfernt (#1209 5b): es gab nie einen
Sentiment-Service, das Feld trug nie einen Wert und wurde nirgends gerendert.
Ein Layer-0-Feld, das nur aus seiner eigenen Nicht-Unterstützung besteht, ist
kein Vertrag. Wiedereinführung erst mit einem Dienst, der es befüllt.

Wird emittiert nach jedem CREATE_POST-Action im OASIS-Runner. Geht via
event_bus + simulation_stream als SSE-Frame ``event: post_created`` ans
Frontend. Slice 5 (Dual-Column Sim-Feed) konsumiert.

Wording-Glossar v1: ``is_simulated=True`` ist Pflicht-Marker für alle
OASIS-emittierten Posts. Frontend rendert SIM-Badge. Kein "prediction".

2026-09-29 — Slice UI-2a (#1713): v2-Felder fuer die Thread-/Diskurs-
darstellung (``docs/design/simulation-feed.md``, PR #1718) ergaenzt. Alle
neuen Felder sind optional mit Default ``None`` — bestehende Emitter/
Snapshots ohne diese Felder bleiben gueltig, altes UI ignoriert sie. Das
Feld ``body`` darf nur bei ``kind=repost`` leer sein (ein reiner Repost hat
keinen eigenen Text); jeder andere ``kind`` verlangt weiterhin nicht-leeren
Text.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Platform(str, Enum):
    """Plattform-Enum für Dual-Column-Routing.

    Eng halten — andere Channels (Mastodon, Threads) brauchen ADR + Slice.
    """

    REDDIT = "reddit"
    TWITTER = "twitter"


class VoiceRegister(str, Enum):
    """Voice-Register aus oasis_profile_generator (Sub-Slice 10).

    Vokabular ist der Profil-Generator-SSoT (``formal-de``/``neutral-de``/
    ``technical-de``/``skeptisch-de`` plus die Betroffenen-Register
    ``betroffen-de``/``emotional-de``/``umgangssprachlich-de``, #1759 A7). Das alte Vokabular
    ``formal``/``casual``/``jugendsprache`` war nie an den Generator
    angebunden und ist entfernt — der Runner-Fallback auf ``casual``
    verschleierte bisher jede Persona als „casual`` (#1009/#1216).
    Frontend rendert Badge in PersonaAvatar.
    """

    FORMAL_DE = "formal-de"
    NEUTRAL_DE = "neutral-de"
    TECHNICAL_DE = "technical-de"
    SKEPTISCH_DE = "skeptisch-de"
    BETROFFEN_DE = "betroffen-de"
    EMOTIONAL_DE = "emotional-de"
    UMGANGSSPRACHLICH_DE = "umgangssprachlich-de"


class PostKind(str, Enum):
    """Diskurs-Art eines Beitrags fuer die Thread-/Diskursdarstellung (#1713).

    ``None`` (kein Wert im Payload) markiert Vor-Slice-UI-2a-Daten — das
    Frontend leitet dort weiterhin aus ``parent_post_id`` ab, ob es sich um
    eine Antwort handelt.
    """

    POST = "post"
    COMMENT = "comment"
    QUOTE = "quote"
    REPOST = "repost"


class PostCreatedEvent(BaseModel):
    """SSE-Frame für einen einzelnen Post-Action des OASIS-Runners."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: Literal["post_created"] = "post_created"
    simulation_id: str = Field(..., min_length=1)
    post_id: str = Field(..., min_length=1)
    parent_post_id: str | None = None
    platform: Platform
    persona_id: str = Field(..., min_length=1)
    persona_name: str = Field(
        ...,
        min_length=1,
        description=(
            "Anzeigename der Persona (z. B. 'Mara Lindner'). ``persona_id`` "
            "bleibt der stabile Identifikator (agent_id); dieses Feld steuert "
            "die UI-Anzeige und ersetzt die reine Agent-ID (#1216 5a)."
        ),
    )
    voice_register: VoiceRegister
    is_simulated: bool = True
    body: str = Field(
        default="",
        description=(
            "Beitragstext. Muss nicht-leer sein ausser bei ``kind=repost`` — "
            "ein reiner Repost hat keinen eigenen Text, der geteilte Beitrag "
            "steht unter ``reposted_post_id`` (siehe body_required_unless_repost)."
        ),
    )
    timestamp: datetime
    score: int = Field(
        default=0,
        description=(
            "Voting-Score (Reddit-Pattern) aus der Simulations-DB "
            "(num_likes - num_dislikes). Twitter-Posts haben kein Voting → 0. "
            "Live-Events tragen den Stand zum Erzeugungszeitpunkt, der Snapshot "
            "den akkumulierten Endstand; spätere Votes aktualisieren ein bereits "
            "gesendetes Live-Event nicht (#1209 5b)."
        ),
    )
    sim_time: datetime | None = Field(
        default=None,
        description=(
            "Simulierte Agenten-Wallclock (Sim-Round → Wallclock, tz-aware). "
            "Quelle: run_parallel_simulation leitet aus start_time + "
            "start_hour_offset + simulated_minutes pro CREATE_POST ab. "
            "None bei Pre-Slice-5-Daten und für Persistenz-Snapshots ohne Feld."
        ),
    )
    kind: PostKind | None = Field(
        default=None,
        description=(
            "Diskurs-Art (post/comment/quote/repost). None bei Pre-Slice-"
            "UI-2a-Daten — Frontend faellt auf die parent_post_id-Heuristik "
            "zurueck."
        ),
    )
    round_num: int | None = Field(
        default=None,
        description="Sim-Runde, in der die Aktion ausgefuehrt wurde. None bei Altdaten.",
    )
    parent_comment_id: str | None = Field(
        default=None,
        description=(
            "Elternkommentar innerhalb eines Reddit-Strangs (Baum-Kante). "
            "Gesetzt wenn der nested-comments-Patch aktiv ist (camel-oasis==0.2.5, "
            "nur Reddit). Twitter-Kommentare kennen dieses Feld nicht (#1713 S5)."
        ),
    )
    root_post_id: str | None = Field(
        default=None,
        description="Wurzel-Post des Strangs, dem dieser Beitrag angehoert.",
    )
    quoted_post_id: str | None = Field(
        default=None,
        description="post_id des zitierten Beitrags bei kind=quote.",
    )
    reposted_post_id: str | None = Field(
        default=None,
        description="post_id des geteilten Beitrags bei kind=repost.",
    )
    quote_body: str | None = Field(
        default=None,
        description="Text des zitierten Beitrags bei kind=quote (nested Block im Feed).",
    )
    parent_persona_id: str | None = Field(
        default=None,
        description="persona_id der Eltern-Persona (Antwort/Zitat/Repost-Quelle).",
    )
    parent_persona_name: str | None = Field(
        default=None,
        description="Anzeigename der Eltern-Persona, fuer die Kontextzeile im Feed.",
    )
    like_count: int | None = Field(
        default=None,
        description="Anzahl Likes zum Zeitpunkt der Emission. None bei Altdaten.",
    )

    @model_validator(mode="after")
    def body_required_unless_repost(self) -> "PostCreatedEvent":
        # Ein reiner Repost traegt seinen Text im referenzierten Beitrag
        # (reposted_post_id) — jede andere Art braucht eigenen Text (#1713).
        if self.kind != PostKind.REPOST and not self.body:
            raise ValueError(
                "body darf nur bei kind='repost' leer sein"
            )
        return self

    @field_validator("persona_name")
    @classmethod
    def persona_name_not_blank(cls, v: str) -> str:
        # min_length=1 lässt reines Whitespace durch; ein Nur-Leerzeichen-Name
        # wäre im Feed ein Nicht-Wert und damit eine Falschaussage (#1216 5a).
        if not v.strip():
            raise ValueError("persona_name darf nicht leer oder nur Whitespace sein")
        return v

    @field_validator("sim_time")
    @classmethod
    def sim_time_tz_aware(cls, v: datetime | None) -> datetime | None:
        # Layer-0 erzwingt tz-aware Timestamps für sim_time. Naive datetimes
        # würden im Frontend zu „local time“-Drift führen, sobald der Container
        # eine andere TZ als der Browser hat.
        if v is not None and v.tzinfo is None:
            raise ValueError("sim_time muss tz-aware sein (UTC + Offset)")
        return v


__all__ = [
    "Platform",
    "PostCreatedEvent",
    "PostKind",
    "VoiceRegister",
]
