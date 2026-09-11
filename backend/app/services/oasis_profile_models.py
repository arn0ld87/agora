"""Data contracts for OASIS persona generation.

Extracted from oasis_profile_generator to keep the public generator facade focused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

class PersonaProfileSchema(BaseModel):
    """Striktes Pydantic-Schema für die LLM-generierte Persona.

    Wird an ``LLMClient.chat_json(schema=...)`` übergeben, damit der Provider im
    strict-``json_schema``-Mode antwortet. MiniMax-M3 emittiert ohne diese
    Strukturvorgabe (und ohne ``thinking.type: disabled``) bis zu 63 % des
    Token-Budgets als Reasoning-Text *im content* → kaputtes JSON ("Extra data",
    "Expecting value") → 3-facher Retry-Loop → Persona-Generation extrem
    langsam (~1:30 pro Persona statt ~15-20 s) oder scheinbares Hängen.

    Pflichtfelder sind required; optionale Felder (bio, persona) haben Fallbacks
    in der Post-Processing-Logik. strict-Mode erzwingt gültiges JSON nach Schema.
    """

    display_name: str = Field(..., description="Real first + last name (DACH)")
    handle: str = Field(..., description="Lowercase social handle without spaces/digits")
    bio: str = Field("", description="Social media bio, <=200 chars")
    persona: str = Field("", description="Detailed persona description, pure text")
    age: int = Field(..., description="Age as integer 18-75", ge=18, le=75)
    gender: str = Field(..., description="One of male/female/nonbinary/other")
    mbti: str = Field(..., description="MBTI type, e.g. INTJ, ENFP")
    country: str = Field(..., description="ISO country code, e.g. DE, AT, CH")
    profession: str = Field("", description="Profession")
    interested_topics: List[str] = Field(default_factory=list, description="Topic strings")
    voice_register: str = Field(..., description="One of formal-de/neutral-de/technical-de/skeptisch-de")
    # Issue #1247: Ablehnung statt Erfindung. Die Frage "kann diese Entitaet
    # einen menschlichen Traeger haben" haengt am Namen und am Kontext, nicht
    # am Typlabel — 28 von 29 beobachteten Nicht-Stakeholdern trugen den
    # voellig legitimen Typ ``Organization``. Die Pruefung wird in den ohnehin
    # stattfindenden Generierungsaufruf gefaltet und kostet damit keinen
    # zusaetzlichen Roundtrip.
    ineligible: bool = Field(
        False,
        description="True if this entity cannot have a human bearer and must not become a persona",
    )
    ineligible_reason: str = Field("", description="Short reason when ineligible is true")


class PersonaIneligible(Exception):
    """Das Modell hat die Entitaet als nicht personenfaehig zurueckgewiesen (#1247).

    Bewusst eine eigene Ausnahme und kein stiller ``None``-Rueckgabewert: der
    Aufrufer muss den Unterschied zwischen "Generierung fehlgeschlagen"
    (Notprofil, Slot bleibt besetzt) und "Kandidat abgelehnt" (Slot wird
    nachbesetzt) kennen. Vor diesem Slice gab es diesen Unterschied nicht —
    jede Entitaet, die den Generator erreichte, wurde zu einer Persona.
    """

    def __init__(self, entity_name: str, entity_type: str, reason: str) -> None:
        self.entity_name = entity_name
        self.entity_type = entity_type
        self.reason = reason
        super().__init__(
            f"{entity_name} ({entity_type}) ist nicht personenfaehig: {reason}"
        )


class CollectivePersonaSchema(BaseModel):
    """Antwortvertrag fuer Kollektiv-Personas (Issue #1246, CodeRabbit PR #1257).

    ``PersonaProfileSchema`` beschreibt ausschliesslich die individuelle
    Persona und fuehrt ``display_name``, ``handle``, ``age`` (18-75),
    ``gender`` und ``mbti`` als Pflichtfelder. Der Kollektiv-Prompt weist das
    Modell ausdruecklich an, genau diese Felder wegzulassen — eine Organisation
    hat davon nichts. Beides zusammen liess im strict-``json_schema``-Mode jede
    Gruppen-Entitaet dreimal scheitern und auf den regelbasierten Pfad
    zurueckfallen: der LLM-Kollektivzweig waere nie zum Zug gekommen.

    Getrennter Vertrag statt aufgeweichter Pflichtfelder, damit der
    Individuenpfad seine Garantien behaelt.
    """

    bio: str = Field("", description="Short description of the organization, <=200 chars")
    persona: str = Field("", description="Detailed description of the organization, pure text")
    country: str = Field(..., description="ISO country code, e.g. DE, AT, CH")
    interested_topics: List[str] = Field(default_factory=list, description="Topic strings")
    voice_register: str = Field(..., description="One of formal-de/neutral-de/technical-de/skeptisch-de")
    # Issue #1247: Der Eignungsblock haengt an beiden Prompts, also braucht auch
    # der Kollektiv-Vertrag das Ablehnungsfeld — sonst scheitert eine Ablehnung
    # fuer Gruppen-Entitaeten an der Schemavalidierung.
    ineligible: bool = Field(
        False,
        description="True if this entity cannot have a human bearer and must not become a persona",
    )
    ineligible_reason: str = Field("", description="Short reason when ineligible is true")


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile data structure"""
    # Common fields
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str

    # Optional fields - Reddit style
    karma: int = 1000

    # Optional fields - Twitter style
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500

    # Additional persona information
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)

    # Source entity information
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None

    # Segment tag for PersonaQuotaPlan validation (= entity_type by default)
    segment: Optional[str] = None

    # Issue #1246: "individual" oder "collective". Eine Organisation hat kein
    # Alter, kein Geschlecht, keinen MBTI-Typ und keine Berufsbezeichnung —
    # wer sie als Einzelperson beschreibt, muss all das erfinden. Genau so
    # entstand aus dem Bildungstraeger "Nordharz Bildungswerk gGmbH" ein
    # "Juergen Hartmann, 57, Dozent und Betriebsratsmitglied". Kollektiv-
    # Personas tragen keine Vita, also nichts, was erfunden werden koennte.
    persona_kind: str = "individual"

    # DACH-Voice-Register (Layer 2)
    voice_register: Optional[str] = None

    # Herkunft des Profils (Issue #1029). "llm" oder "rule_based".
    # Regelbasierte Profile entstehen entweder bewusst (use_llm=False) oder
    # nach drei gescheiterten LLM-Versuchen. Sie nehmen regulär an der
    # Simulation teil; ohne dieses Feld sind ihre Beiträge im Report nicht
    # von denen echter Personas zu unterscheiden.
    generation_source: str = "llm"
    # Nur gesetzt, wenn die Degradierung aus einem Ausfall entstand — bei
    # bewusst regelbasierter Erzeugung bleibt es None.
    generation_error: Optional[str] = None

    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    def to_reddit_format(self) -> Dict[str, Any]:
        """Convert to Reddit platform format"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS library requires field name as username (no underscore)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }

        # Add additional persona information (if available)
        # age/gender/mbti werden IMMER als Schluessel geschrieben,
        # auch wenn sie bei Kollektiv-Personas None sind. oasis/social_platform/
        # config/user.py::to_reddit_system_message greift auf agent_info[i]["mbti"]
        # etc. ungeschuetzt zu — ein fehlender Schluessel ist dort ein KeyError,
        # kein fehlender Wert. Der Leerstring erfindet keine Demografie und
        # haelt damit die Zusage aus #1246 ("Organisationen haben keine Vita")
        # ein: ein `None` stuende sonst woertlich im Satz "You are a {gender},
        # {age} years old, with an MBTI personality type of {mbti} from
        # {country}." im Agent-Prompt. Die Substanz der Kollektiv-Persona
        # steht im vorangehenden `user_profile`, nicht in diesen drei Feldern.
        profile["age"] = self.age if self.age else ""
        profile["gender"] = self.gender if self.gender else ""
        profile["mbti"] = self.mbti if self.mbti else ""
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        if self.source_entity_uuid:
            profile["source_entity_uuid"] = self.source_entity_uuid
        if self.source_entity_type:
            profile["source_entity_type"] = self.source_entity_type
        # Issue #1246: immer geschrieben — der Konsument muss Kollektiv und
        # Individuum unterscheiden koennen, ohne den Entitaetstyp nachzuschlagen.
        profile["persona_kind"] = self.persona_kind
        if self.segment:
            profile["segment"] = self.segment
        if self.voice_register:
            profile["voice_register"] = self.voice_register
        # Issue #1029: Die Persona-Galerie liest genau diese Datei. Ohne
        # die Herkunft hier bliebe die Kennzeichnung im Frontend wirkungslos.
        # Nur bei Abweichung vom Default geschrieben, damit LLM-Profile
        # unverändert zum bisherigen Format bleiben.
        if self.generation_source != "llm":
            profile["generation_source"] = self.generation_source
        if self.generation_error:
            profile["generation_error"] = self.generation_error

        return profile

    def to_twitter_format(self) -> Dict[str, Any]:
        """Convert to Twitter platform format"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS library requires field name as username (no underscore)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
        }

        # Add additional persona information
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        if self.source_entity_uuid:
            profile["source_entity_uuid"] = self.source_entity_uuid
        if self.source_entity_type:
            profile["source_entity_type"] = self.source_entity_type
        # Issue #1246: immer geschrieben — der Konsument muss Kollektiv und
        # Individuum unterscheiden koennen, ohne den Entitaetstyp nachzuschlagen.
        profile["persona_kind"] = self.persona_kind
        if self.segment:
            profile["segment"] = self.segment
        if self.voice_register:
            profile["voice_register"] = self.voice_register
        # Issue #1029: Die Persona-Galerie liest genau diese Datei. Ohne
        # die Herkunft hier bliebe die Kennzeichnung im Frontend wirkungslos.
        # Nur bei Abweichung vom Default geschrieben, damit LLM-Profile
        # unverändert zum bisherigen Format bleiben.
        if self.generation_source != "llm":
            profile["generation_source"] = self.generation_source
        if self.generation_error:
            profile["generation_error"] = self.generation_error

        return profile

    def to_dict(self) -> Dict[str, Any]:
        """Convert to complete dictionary format"""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "persona_kind": self.persona_kind,
            "segment": self.segment,
            "voice_register": self.voice_register,
            # Issue #1029: Herkunft immer mitführen — to_dict ist die
            # vollständige Darstellung, hier ist auch der Normalfall "llm"
            # eine Information.
            "generation_source": self.generation_source,
            "generation_error": self.generation_error,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class PersonaDemographicSlot:
    age: int
    gender: str
    mbti: str
