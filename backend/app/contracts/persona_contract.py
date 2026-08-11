"""
Persona-Contract v2 (Pydantic v2).

Code-verifiziert gegen:
- backend/app/services/oasis_profile_generator.py (OasisAgentProfile-Felder)

Ergänzt PersonaQuotaPlan, der heute fehlt — siehe ChatGPT-Audit
'Persona-Erzeugung ist nicht an Segment-Plan gebunden'.
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


_STRICT = ConfigDict(extra="forbid")


# DACH-Voice-Register (für Layer 2)
VoiceRegister = Literal["formal-de", "neutral-de", "technical-de", "skeptisch-de"]


class PersonaModel(BaseModel):
    """1:1-Spiegel von OasisAgentProfile, aber typsicher."""
    model_config = _STRICT

    # Pflichtfelder aus OasisAgentProfile
    user_id: int = Field(ge=1)
    user_name: str = Field(min_length=3, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=3)
    bio: str = Field(min_length=10, max_length=200)
    persona: str = Field(min_length=300, max_length=12000)

    # Reddit/Twitter-spezifisch
    karma: int = Field(default=1000, ge=0)
    friend_count: int = Field(default=100, ge=0)
    follower_count: int = Field(default=150, ge=0)
    statuses_count: int = Field(default=500, ge=0)

    # Persona-Demografie
    age: Optional[int] = Field(default=None, ge=18, le=99)
    gender: Optional[Literal["male", "female", "nonbinary", "other"]] = None
    mbti: Optional[Literal[
        "INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP",
    ]] = None
    country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    profession: Optional[str] = None
    interested_topics: list[str] = Field(default_factory=list, max_length=15)

    # Quelle in Knowledge-Graph
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None

    # Issue #1246: "individual" oder "collective". Das Modell ist ein 1:1-
    # Spiegel von ``OasisAgentProfile`` und ``extra="forbid"`` — ohne dieses
    # Feld wuerde jedes serialisierte Profil, das ``persona_kind`` traegt, von
    # vertragspruefenden Konsumenten abgelehnt (CodeRabbit PR #1257).
    # Optional mit Default, damit Profile aus Laeufen vor diesem Slice
    # unveraendert validieren.
    persona_kind: Optional[Literal["individual", "collective"]] = "individual"

    # Review-Status (kommt aus persona_review_service.py)
    review_status: Optional[Literal["pending", "approved", "rejected"]] = None
    is_manual: Optional[bool] = False

    # Layer 2: DACH-Voice — Default neutral-de; None bleibt zulässig für alte Daten
    voice_register: Optional[VoiceRegister] = "neutral-de"

    # Layer 1: Segment-Zuordnung — neu, Pflicht ab Persona-Quoten-Vertrag
    segment: Optional[str] = Field(default=None, min_length=1, max_length=64)

    # Herkunft des Profils (Issue #1029). Regelbasierte Profile entstehen
    # entweder bewusst (use_llm=False) oder nach drei gescheiterten
    # LLM-Versuchen; sie nehmen regulär an der Simulation teil. Ohne dieses
    # Feld sind ihre Beiträge im Report nicht von denen echter Personas zu
    # unterscheiden, und die Oberfläche kann sie nicht kennzeichnen.
    #
    # Additiv mit Default: persistierte Personas von vor #1029 tragen es
    # nicht und validieren unverändert weiter — sie gelten als "llm",
    # was ihrem damaligen Regelfall entspricht.
    generation_source: Literal["llm", "rule_based"] = "llm"
    # Nur bei einem Ausfall gesetzt, nicht bei bewusst regelbasierter
    # Erzeugung.
    generation_error: Optional[str] = Field(default=None, max_length=200)


class PersonaQuotaPlan(BaseModel):
    """
    Soll-Plan für Persona-Generation. Erzwingt exakte Counts pro Segment.
    Adressiert ChatGPT-Audit: 'Persona-Erzeugung ist nicht an Segment-Plan gebunden'.
    """
    model_config = _STRICT

    # z. B. {"kmu_ceo": 8, "it_admin": 6, ...}
    targets: dict[str, Annotated[int, Field(ge=1, le=200)]]
    total: int = Field(ge=1, le=500)

    @model_validator(mode="after")
    def total_matches_sum(self) -> "PersonaQuotaPlan":
        s = sum(self.targets.values())
        if s != self.total:
            raise ValueError(
                f"PersonaQuotaPlan.total={self.total} != sum(targets)={s}. "
                f"Soll-Plan ist inkonsistent."
            )
        return self


class PersonaQuotaActual(BaseModel):
    """Ist-Verteilung nach Generation. Wird gegen Plan validiert."""
    model_config = _STRICT

    plan: PersonaQuotaPlan
    actual_counts: dict[str, Annotated[int, Field(ge=0)]]
    tolerance: Annotated[int, Field(ge=0, le=10)] = 0  # default: exakt

    @model_validator(mode="after")
    def actual_within_tolerance(self) -> "PersonaQuotaActual":
        for segment, target in self.plan.targets.items():
            actual = self.actual_counts.get(segment, 0)
            if abs(actual - target) > self.tolerance:
                raise ValueError(
                    f"Segment '{segment}': Soll={target}, Ist={actual}, "
                    f"Toleranz={self.tolerance} überschritten."
                )
        # Keine unbekannten Segmente
        unknown = set(self.actual_counts) - set(self.plan.targets)
        if unknown:
            raise ValueError(
                f"Unbekannte Segmente in actual_counts: {sorted(unknown)}"
            )
        return self
