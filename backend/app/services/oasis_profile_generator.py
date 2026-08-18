"""
OASIS Agent Profile Generator
Convert entities from the knowledge graph to OASIS simulation platform's required Agent Profile format

Optimization improvements:
1. Call knowledge graph retrieval function to enrich node information
2. Optimize prompts to generate very detailed personas
3. Distinguish between individual entities and abstract group entities
"""

import json
import random
import re
from typing import TYPE_CHECKING, Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI
from pydantic import BaseModel, Field

from ..config import Config
from ..contracts import PersonaQuotaPlan
from ..contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
)
from .settings_layer import get_default_service as _get_settings
from ..utils.llm_latency import measure_llm_latency
from ..utils.logger import get_logger
from .entity_reader import EntityNode
from ..storage import GraphStorage
from .persona_domain_coherence import coherence_findings, is_collective_entity_type
from .persona_demographics import (
    DACH_NAME_ORIGIN_QUOTAS,
    build_name_quota_prompt_block,
    build_name_quota_prompt_block_en,
    filter_first_names_for_gender,
)
from .persona_quota_defaults import (
    build_industry_quota_prompt_block,
    build_industry_quota_prompt_block_en,
    default_dach_industry_quota,
)
from ..llm.json_mode import _try_repair_truncated_json

if TYPE_CHECKING:
    from .degradation_collector import DegradationCollector

logger = get_logger('agora.oasis_profile')

# Erlaubte Voice-Register-Werte (gespiegelt aus VoiceRegister Literal in persona_contract.py)
VOICE_REGISTERS = ("formal-de", "neutral-de", "technical-de", "skeptisch-de")


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

# Persona-Detail-Level steuert die Output-Größe pro Persona — direkter
# Hebel auf Cloud-LLM-Inference-Zeit (Output-Tokens dominieren). Issue #217.
PERSONA_DETAIL_LEVELS = {
    'compact': {
        'word_count_de': '300–500 Wörter',
        'word_count_en': '300–500 words',
        'context_limit': 1200,
        'max_tokens': 8192,
    },
    'standard': {
        'word_count_de': '700–900 Wörter',
        'word_count_en': '700–900 words',
        'context_limit': 2000,
        'max_tokens': 16384,
    },
    'rich': {
        'word_count_de': '1500–2000 Wörter',
        'word_count_en': '2000 words',
        'context_limit': 3000,
        'max_tokens': 32768,
    },
}


def _resolve_persona_detail_level() -> dict:
    """Resolve persona detail level from settings_layer (Issue #212 / #217 Stufe 2b).

    AGORA_PERSONA_DETAIL_LEVEL=compact|standard|rich (Default: standard).
    Unknown values fall back to 'standard' with a warning.
    """
    level = str(_get_settings().effective_value('AGORA_PERSONA_DETAIL_LEVEL')).strip().lower()
    if level not in PERSONA_DETAIL_LEVELS:
        logger.warning(
            "AGORA_PERSONA_DETAIL_LEVEL='%s' unknown, falling back to 'standard'. "
            "Valid: compact, standard, rich.",
            level,
        )
        level = 'standard'
    return PERSONA_DETAIL_LEVELS[level]


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


class OasisProfileGenerator:
    """
    OASIS Profile Generator

    Convert entities from the knowledge graph to Agent Profile required by OASIS simulation

    Optimization features:
    1. Call knowledge graph retrieval function to get richer context
    2. Generate very detailed personas (including basic information, career experience, personality traits, social media behavior, etc.)
    3. Distinguish between individual entities and abstract group entities
    """

    # Budget-Enforcement (#984): Class-Level-Default, weil mehrere Tests die
    # Klasse via ``__new__`` ohne ``__init__`` instanziieren — ohne Default
    # bräche ``_generate_profile_with_llm`` dort mit AttributeError.
    run_id: Optional[str] = None

    # MBTI types list
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]
    REQUIRED_PROFILE_FIELDS = ("age", "gender", "mbti", "country")
    VALID_PROFILE_GENDERS = {"male", "female", "nonbinary", "other"}
    PERSONA_GENDER_WEIGHTS = (
        ("male", 0.47),
        ("female", 0.47),
        ("nonbinary", 0.06),
    )
    PERSONA_MBTI_WEIGHTS = (
        ("ISFJ", 0.13),
        ("ESFJ", 0.12),
        ("ISTJ", 0.11),
        ("ISFP", 0.09),
        ("ESTJ", 0.08),
        ("ESFP", 0.08),
        ("ENFP", 0.08),
        ("INFP", 0.07),
        ("ESTP", 0.06),
        ("INTP", 0.05),
        ("ENTP", 0.04),
        ("ENFJ", 0.03),
        ("ISTP", 0.02),
        ("INTJ", 0.02),
        ("ENTJ", 0.01),
        ("INFJ", 0.01),
    )
    INDIVIDUAL_AGE_BANDS = (
        ((18, 24), 0.10),
        ((25, 34), 0.22),
        ((35, 44), 0.22),
        ((45, 54), 0.20),
        ((55, 65), 0.16),
        ((66, 75), 0.10),
    )
    GROUP_AGE_BANDS = (
        ((25, 34), 0.18),
        ((35, 44), 0.30),
        ((45, 54), 0.30),
        ((55, 65), 0.22),
    )

    # Common countries list
    COUNTRIES = [
        "US", "UK", "Japan", "Germany", "France",
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]

    # DACH-Namenspools werden aus persona_demographics.DACH_NAME_ORIGIN_QUOTAS abgeleitet —
    # kein separater Pool mehr, damit alle Pfade dieselbe demographische Verteilung nutzen.

    @staticmethod
    def _pick_dach_name(gender: Optional[str] = None) -> str:
        """Wählt einen Vor- und Nachnamen gewichtet nach DACH-Mikrozensus-Quoten.

        Nutzt DACH_NAME_ORIGIN_QUOTAS als Single Source of Truth statt eines
        statischen deutschen Namenspools.
        """
        weights = [q.share for q in DACH_NAME_ORIGIN_QUOTAS]
        bucket = random.choices(DACH_NAME_ORIGIN_QUOTAS, weights=weights, k=1)[0]
        first = random.choice(filter_first_names_for_gender(bucket.first_names, gender))
        last = random.choice(bucket.last_names)
        return f"{first} {last}"

    @staticmethod
    def _last_name(name: str) -> Optional[str]:
        parts = (name or "").strip().split()
        if len(parts) < 2:
            return None
        return parts[-1].lower()

    @staticmethod
    def _pick_individual_gender() -> str:
        # ~47% male, ~47% female, ~6% nonbinary (statistisch grob realistisch, genug Varianz)
        return random.choices(["male", "female", "nonbinary"], weights=[47, 47, 6], k=1)[0]

    @staticmethod
    def _largest_remainder_counts(weighted_values: tuple[tuple[object, float], ...], total: int) -> list[int]:
        raw = [share * total for _, share in weighted_values]
        counts = [int(value) for value in raw]
        remainder = total - sum(counts)
        ranked = sorted(
            ((raw[idx] - counts[idx], idx) for idx in range(len(weighted_values))),
            reverse=True,
        )
        for _, idx in ranked[:remainder]:
            counts[idx] += 1
        return counts

    @classmethod
    def _build_weighted_slots(cls, weighted_values: tuple[tuple[str, float], ...], total: int) -> list[str]:
        slots: list[str] = []
        for (value, _share), count in zip(
            weighted_values,
            cls._largest_remainder_counts(weighted_values, total),
        ):
            slots.extend([value] * count)
        random.shuffle(slots)
        return slots

    @classmethod
    def _build_age_slots(
        cls,
        weighted_bands: tuple[tuple[tuple[int, int], float], ...],
        total: int,
    ) -> list[int]:
        ages: list[int] = []
        for (age_range, _share), count in zip(
            weighted_bands,
            cls._largest_remainder_counts(weighted_bands, total),
        ):
            start, end = age_range
            band_ages = list(range(start, end + 1))
            random.shuffle(band_ages)
            ages.extend(band_ages[idx % len(band_ages)] for idx in range(count))
        random.shuffle(ages)
        return ages

    def _build_demographic_slots(self, entities: List[EntityNode]) -> list[PersonaDemographicSlot]:
        total = len(entities)
        if total == 0:
            return []

        genders = self._build_weighted_slots(self.PERSONA_GENDER_WEIGHTS, total)
        mbtis = self._build_weighted_slots(self.PERSONA_MBTI_WEIGHTS, total)

        age_by_index: list[Optional[int]] = [None] * total
        individual_indices: list[int] = []
        group_indices: list[int] = []
        for idx, entity in enumerate(entities):
            entity_type = entity.get_entity_type() or "Entity"
            if self._is_group_entity(entity_type):
                group_indices.append(idx)
            else:
                individual_indices.append(idx)

        if individual_indices:
            for idx, age in zip(
                individual_indices,
                self._build_age_slots(self.INDIVIDUAL_AGE_BANDS, len(individual_indices)),
            ):
                age_by_index[idx] = age
        if group_indices:
            for idx, age in zip(
                group_indices,
                self._build_age_slots(self.GROUP_AGE_BANDS, len(group_indices)),
            ):
                age_by_index[idx] = age

        if any(age is None for age in age_by_index):
            raise AssertionError("Demographic slot planning left at least one age unassigned.")

        slots: list[PersonaDemographicSlot] = []
        for idx in range(total):
            assigned_age = age_by_index[idx]
            assert assigned_age is not None  # guarded above; keeps the invariant explicit for type-checkers
            slots.append(
                PersonaDemographicSlot(
                    age=assigned_age,
                    gender=genders[idx],
                    mbti=mbtis[idx],
                )
            )
        return slots

    def _build_demographic_slot_prompt_block(
        self,
        demographic_slot: PersonaDemographicSlot,
    ) -> str:
        if self.language == "de":
            return (
                "### Zugewiesener Demografie-Slot (verbindlich)\n"
                f"- age: exakt {demographic_slot.age}\n"
                f"- gender: exakt \"{demographic_slot.gender}\"\n"
                f"- mbti: exakt \"{demographic_slot.mbti}\"\n"
                "- Diese drei Felder sind vorgegeben und müssen unverändert ins JSON übernommen werden.\n"
                "- display_name muss zu diesem Gender passen."
            )
        return (
            "### Assigned demographic slot (mandatory)\n"
            f"- age: exactly {demographic_slot.age}\n"
            f"- gender: exactly \"{demographic_slot.gender}\"\n"
            f"- mbti: exactly \"{demographic_slot.mbti}\"\n"
            "- These three fields are fixed and must be copied into the JSON unchanged.\n"
            "- display_name must match this gender."
        )

    # Individual type entities (need to generate specific personas)
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure",
        "expert", "faculty", "official", "journalist", "activist"
    ]

    # Group/institutional type entities (need to generate group representative personas)
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo",
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        storage: Optional[GraphStorage] = None,
        graph_id: Optional[str] = None,
        language: Optional[str] = None,
        industry_quota_plan: Optional[PersonaQuotaPlan] = None,
        run_id: Optional[str] = None,
    ):
        # Budget-Enforcement (#984): die run_id des Prepare-Runs bindet jeden
        # LLM-Call dieser Generierung an den Budget-Enforcer des Runs.
        self.run_id = run_id
        self.base_url = base_url or Config.LLM_BASE_URL
        # Key und Base-URL muessen aus derselben Quelle stammen (#778). Loest der
        # Aufrufer einen Provider-Endpoint auf, darf der .env-Key NICHT einspringen —
        # sonst geht der lokale Ollama-Key an einen Fremd-Provider (404/401).
        self.api_key = api_key or (
            Config.LLM_API_KEY if self.base_url == Config.LLM_BASE_URL else None
        )
        self.model_name = model_name or Config.LLM_MODEL_NAME
        # Language for generated personas ("de" or "en"); affects prompts and bio language.
        self.language = (language or Config.AGENT_LANGUAGE or "de").lower()

        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

        # GraphStorage for hybrid search enrichment
        self.storage = storage
        self.graph_id = graph_id

        # Destatis-WZ-2008-Branchenverteilung für LLM-Prompt-Steuerung (Issue #215).
        # Wenn kein expliziter Plan übergeben wird, wird der Default-Plan mit
        # einer realistischen DACH-Verteilung verwendet (IT-Cap ≤ 12 %).
        self._industry_quota_plan: PersonaQuotaPlan = (
            industry_quota_plan or default_dach_industry_quota(100)
        )
    
    def generate_profile_from_entity(
        self,
        entity: EntityNode,
        user_id: int,
        use_llm: bool = True,
        demographic_slot: Optional[PersonaDemographicSlot] = None,
    ) -> OasisAgentProfile:
        """
        Generate OASIS Agent Profile from knowledge graph entity

        Args:
            entity: Knowledge graph entity node
            user_id: User ID (for OASIS)
            use_llm: Whether to use LLM to generate detailed persona

        Returns:
            OasisAgentProfile
        """
        entity_type = entity.get_entity_type() or "Entity"

        # Fallback-Basics: echter Entity-Name + abgeleiteter Username.
        # Werden später überschrieben, wenn LLM/Rule-based display_name + handle liefern.
        name = entity.name
        user_name = self._generate_username(name)

        # Build context information
        context = self._build_entity_context(entity)
        
        if use_llm:
            # Use LLM to generate detailed persona
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context,
                demographic_slot=demographic_slot,
            )
        else:
            # Use rules to generate basic persona
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                demographic_slot=demographic_slot,
            )

        # Issue #1247: Das Modell darf die Entitaet zurueckweisen, statt eine
        # Persona zu erfinden. Bewusst als Ausnahme und nicht als stilles
        # Ueberspringen — der Aufrufer muss den Slot nachbesetzen koennen.
        if profile_data.get("ineligible"):
            reason = (profile_data.get("ineligible_reason") or "").strip() or (
                "vom Persona-Generator als nicht personenfaehig zurueckgewiesen"
            )
            logger.info(
                "Persona-Eligibility (LLM): Entitaet abgelehnt name=%s type=%s reason=%s",
                name,
                entity_type,
                reason,
            )
            raise PersonaIneligible(name, entity_type, reason)

        # Issue #1246: Der Kollektiv-Zweig ist bewusst hier sichtbar und nicht
        # in den Individuenpfad eingebettet. Eine Organisation bekommt keine
        # Demografie zugewiesen — es gibt kein Alter, kein Geschlecht und
        # keinen MBTI-Typ, den man ihr zuschreiben koennte, und jeder Wert an
        # dieser Stelle waere eine Erfindung.
        is_collective = self._is_group_entity(entity_type)
        persona_kind = "collective" if is_collective else "individual"

        if is_collective:
            profile_data["age"] = None
            profile_data["gender"] = None
            profile_data["mbti"] = None
            # Eine Kollektiv-Persona hat keinen Beruf. "Dozent und
            # Betriebsratsmitglied" war aus einem Bildungstraeger nicht
            # ableitbar, sondern eine plausible Vita.
            profile_data["profession"] = None
        elif demographic_slot is not None:
            profile_data["age"] = demographic_slot.age
            profile_data["gender"] = demographic_slot.gender
            profile_data["mbti"] = demographic_slot.mbti

        # LLM/Rule-based darf display_name (echter Name) + handle (kurzes Social-Handle)
        # überschreiben. So wird aus Entity "GraphRAG" z.B. Person "Lena Hoffmann" mit
        # Handle "lena_hoffmann". Fuer Kollektive bleibt der Entitaetsname stehen:
        # der Traeger spricht als Traeger, nicht als erfundener Mitarbeiter.
        if not is_collective:
            display_name = (profile_data.get("display_name") or "").strip()
            if display_name:
                name = display_name
            handle = (profile_data.get("handle") or "").strip()
            if handle:
                user_name = self._generate_username(handle)

        # Issue #1246 (P1): Der Freitext muss dieselbe Person beschreiben, die
        # oben benannt ist. Fuer Kollektive entfaellt die Frage.
        persona_text = profile_data.get("persona", entity.summary or f"A {entity_type} named {name}.")
        if not is_collective:
            persona_text = self._align_persona_identity(persona_text, name)

        # Issue #1246 (P3): Der Entitaetstyp ist keine Berufsbezeichnung. Wo
        # der degradierte Pfad nichts abzuleiten wusste, reichte er ihn woertlich
        # durch — "AIProvider", "WorkingGroup", "TechnologyVendor". Lieber keine
        # Angabe als eine falsche.
        profession = profile_data.get("profession")
        if isinstance(profession, str) and profession.strip().lower() == entity_type.strip().lower():
            logger.debug(
                "Persona-Beruf verworfen: entity_type wurde als profession durchgereicht (%s)",
                entity_type,
            )
            profession = None

        profession = self._profession_after_coherence_check(
            entity_type=entity_type,
            entity_name=name,
            persona_kind=persona_kind,
            profession=profession,
            persona_text=persona_text,
            entity_summary=entity.summary,
            entity_context=context,
        )

        # Segment = entity_type string for PersonaQuotaPlan validation.
        # entity_type is already resolved above (get_entity_type() or "Entity").
        segment = entity_type if entity_type != "Entity" else None

        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=persona_text,
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            profession=profession,
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
            segment=segment,
            persona_kind=persona_kind,
            voice_register=profile_data.get("voice_register"),
            # Issue #1029: Default "llm" — nur der regelbasierte Pfad setzt
            # den Schlüssel, und er setzt ihn immer.
            generation_source=profile_data.get("generation_source", "llm"),
            generation_error=profile_data.get("generation_error"),
        )
    
    def _generate_username(self, name: str) -> str:
        """Generate username"""
        # Remove special characters, convert to lowercase
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')

        # Add random suffix to avoid duplicates
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_graph_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """
        Use GraphStorage hybrid search to obtain rich information related to entity

        Uses storage.search() (hybrid vector + BM25) for both edges and nodes.

        Args:
            entity: Entity node object

        Returns:
            Dictionary containing facts, node_summaries, context
        """
        if not self.storage:
            return {"facts": [], "node_summaries": [], "context": ""}

        entity_name = entity.name

        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }

        if not self.graph_id:
            logger.debug("Skip knowledge graph search: graph_id not set")
            return results

        comprehensive_query = f"All information, activities, events, relationships and background about {entity_name}"

        try:
            # Search edges (facts)
            edge_results = self.storage.search(
                graph_id=self.graph_id,
                query=comprehensive_query,
                limit=30,
                scope="edges"
            )

            all_facts = set()
            if isinstance(edge_results, dict) and 'edges' in edge_results:
                for edge in edge_results['edges']:
                    fact = edge.get('fact', '')
                    if fact:
                        all_facts.add(fact)
            results["facts"] = list(all_facts)

            # Search nodes (entity summaries)
            node_results = self.storage.search(
                graph_id=self.graph_id,
                query=comprehensive_query,
                limit=20,
                scope="nodes"
            )

            all_summaries = set()
            if isinstance(node_results, dict) and 'nodes' in node_results:
                for node in node_results['nodes']:
                    summary = node.get('summary', '')
                    if summary:
                        all_summaries.add(summary)
                    name = node.get('name', '')
                    if name and name != entity_name:
                        all_summaries.add(f"Related Entity: {name}")
            results["node_summaries"] = list(all_summaries)

            # Build combined context
            context_parts = []
            if results["facts"]:
                context_parts.append("Fact Information:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("Related Entities:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)

            logger.info(f"Knowledge graph hybrid search completed: {entity_name}, retrieved {len(results['facts'])} facts, {len(results['node_summaries'])} related nodes")

        except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.warning(f"Knowledge graph search failed ({entity_name}): {e}")

        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        Build complete context information for entity

        Includes:
        1. Edge information of the entity itself (facts)
        2. Detailed information of associated nodes
        3. Rich information retrieved from knowledge graph hybrid search
        """
        context_parts = []

        # 1. Add entity attribute information
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### Entity Attributes\n" + "\n".join(attrs))

        # 2. Add related edge information (facts/relationships)
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # No limit on quantity
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")

                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (Related Entity)")
                    else:
                        relationships.append(f"- (Related Entity) --[{edge_name}]--> {entity.name}")

            if relationships:
                context_parts.append("### Related Facts and Relationships\n" + "\n".join(relationships))

        # 3. Add detailed information of related nodes
        if entity.related_nodes:
            related_info = []
            for node in entity.related_nodes:  # No limit on quantity
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")

                # Filter out default labels
                custom_labels = [lbl for lbl in node_labels if lbl not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""

                if node_summary:
                    related_info.append(f"- **{node_name}**{label_str}: {node_summary}")
                else:
                    related_info.append(f"- **{node_name}**{label_str}")

            if related_info:
                context_parts.append("### Related Entity Information\n" + "\n".join(related_info))

        # 4. Use knowledge graph hybrid search to get richer information
        graph_results = self._search_graph_for_entity(entity)

        if graph_results.get("facts"):
            # Deduplication: exclude existing facts
            new_facts = [f for f in graph_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### Facts Retrieved from Knowledge Graph\n" + "\n".join(f"- {f}" for f in new_facts[:15]))

        if graph_results.get("node_summaries"):
            context_parts.append("### Related Nodes Retrieved from Knowledge Graph\n" + "\n".join(f"- {s}" for s in graph_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    #: Erster Eigenname am Textanfang: zwei bis drei grossgeschriebene Tokens,
    #: gefolgt von einer namenstypischen Grenze.
    #:
    #: Mindestens zwei Tokens, weil im Deutschen auch Verben und Substantive am
    #: Satzanfang grossgeschrieben sind — "Arbeitet seit zwölf Jahren…" ist
    #: kein Name, "Sabine Krüger, 47…" schon.
    #:
    #: Die Grenze ist Pflicht (CodeRabbit PR #1257): "Als IT-Leiter
    #: verantwortet …" besteht ebenfalls aus zwei grossgeschriebenen Tokens.
    #: Ohne die Bedingung haette ``_align_persona_identity`` daraus einen Namen
    #: gemacht, ihn durch den Anzeigenamen ersetzt und spaetere Vorkommen von
    #: "Als" und "IT-Leiter" gleich mit — der Text haette seine Rollensemantik
    #: verloren. Ein Personenname am Satzanfang wird im Profiltext praktisch
    #: immer von Komma, Klammer, Gedankenstrich oder Satzende gefolgt.
    _LEADING_NAME_RE = re.compile(
        r"^\s*([A-ZÄÖÜ][\wäöüßáàéèíìóòúù'-]+(?:\s+[A-ZÄÖÜ][\wäöüßáàéèíìóòúù'-]+){1,2})"
        r"(?=\s*[,;:(]|\s+[–—]|\s*$)"
    )

    @classmethod
    def _align_persona_identity(cls, persona: str, display_name: str) -> str:
        """Zieht den Namen im Persona-Freitext auf den Anzeigenamen (#1246).

        Der Generator liefert ``display_name`` und ``persona`` als getrennte
        Felder, und in 50 bis 81 Prozent der messbaren Faelle beschrieben sie
        verschiedene Menschen — haeufig mit abweichendem Geschlecht. Der
        Interview-Systemprompt setzt beides zusammen ("Du bist <label>" plus
        Profiltext), die Persona bekommt damit zwei Identitaeten in derselben
        Nachricht. Das ist die plausibelste Erklaerung fuer die beobachtete
        Rollenuebernahme in den Interview-Antworten.

        Die Reparatur ist bewusst deterministisch statt ein weiterer
        Prompt-Appell: der Prompt enthielt bereits eine Rollentreue-Regel, das
        Modell verletzte also eine vorhandene Regel, keine fehlende.

        Ersetzt werden der vollstaendige Eroeffnungsname und seine einzelnen
        Bestandteile, damit auch spaetere Erwaehnungen ("Sabine schaetzt…",
        "Frau Krueger meldet…") mitgezogen werden. Findet sich kein
        Eroeffnungsname oder stimmt er bereits, bleibt der Text unangetastet.
        """
        if not persona or not display_name:
            return persona

        match = cls._LEADING_NAME_RE.match(persona)
        if not match:
            return persona

        found = match.group(1).strip()
        if found == display_name:
            return persona

        found_parts = found.split()
        target_parts = display_name.split()

        # Laengste Zeichenketten zuerst, sonst zerlegt die Teilersetzung den
        # Vollnamen, bevor er als Ganzes getroffen wird.
        replacements: List[tuple[str, str]] = [(found, display_name)]
        for idx, part in enumerate(found_parts):
            if len(part) < 3:
                continue
            target = target_parts[idx] if idx < len(target_parts) else target_parts[-1]
            replacements.append((part, target))

        aligned = persona
        for source, target in sorted(replacements, key=lambda p: -len(p[0])):
            aligned = re.sub(rf"\b{re.escape(source)}\b", target, aligned)
        return aligned

    @staticmethod
    def _profession_after_coherence_check(
        *,
        entity_type: str,
        entity_name: str,
        persona_kind: str,
        profession: Optional[str],
        persona_text: str,
        entity_summary: Optional[str],
        entity_context: Optional[str],
    ) -> Optional[str]:
        """Prueft Domaenen-Kohaerenz und leert einen fachfremden Beruf.

        Im Referenzlauf report_cc2ef45da5e9 wurde aus einer EmployeeGroup eines
        Klinik-Rollouts eine "Sachbearbeiterin in der Fertigungsplanung" und aus
        einem PatientAdvisoryCouncil ein "Schichtleiter Maschinenbau" —
        plausible Vitae aus einem Fach, das in keiner Quelle vorkam.

        Bereinigt wird nur der Beruf und nur bei eindeutigem Drift: dieselbe
        Linie wie beim nicht ableitbaren Beruf (#1246) — lieber leer als
        erfunden. Der Freitext bleibt stehen; ihn zu beschneiden wuerde mehr
        zerstoeren als retten, und der Befund steht im Log.
        """
        source_text = " ".join(
            part for part in (entity_summary or "", entity_context or "") if part
        )
        findings = coherence_findings(
            entity_type=entity_type,
            entity_name=entity_name,
            persona_kind=persona_kind,
            profession=profession or "",
            persona_text=persona_text,
            source_text=source_text,
        )
        if not findings:
            return profession
        # Der Entitaetsname bleibt draussen: er traegt einen Personen- oder
        # Organisationsnamen, und Logs verlassen den Prozess (dieselbe Linie
        # wie beim producer_key, CodeRabbit PR #1151). Typ und Befundart
        # reichen zur Diagnose — sie sagen, *was* nicht stimmt, ohne zu sagen,
        # *wer* betroffen ist.
        logger.warning(
            "persona coherence: type=%r befunde=%s",
            entity_type,
            "; ".join(finding["kind"] for finding in findings),
        )
        if profession and any(
            finding["kind"] == "domain_drift" for finding in findings
        ):
            return None
        return profession

    def _is_individual_entity(self, entity_type: str) -> bool:
        """Determine if entity is an individual type"""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES

    def _is_group_entity(self, entity_type: str) -> bool:
        """Determine if entity is a group/institutional type.

        Die Liste bleibt die erste Instanz — sie ist gepflegt und trennt Fälle,
        die morphologisch nicht auffallen ("NGO"). Danach entscheidet das
        Grundwort des Typs. Im Referenzlauf ``report_cc2ef45da5e9`` fielen
        ``HospitalNetwork``, ``EmployeeGroup`` und ``PatientAdvisoryCouncil``
        durch die Liste und wurden zu erfundenen Einzelpersonen mit Alter,
        Geschlecht und Biografie. Eine Ontologie bringt solche Typen laufend
        hervor; die Liste hinterherzupflegen ist kein Verfahren.
        """
        return (
            entity_type.lower() in self.GROUP_ENTITY_TYPES
            or is_collective_entity_type(entity_type)
        )

    def _build_eligibility_prompt_block(self, entity_name: str, entity_type: str) -> str:
        """Erlaubt dem Modell, die Entitaet abzulehnen statt sie zu erfinden (#1247).

        Die Blockliste in ``persona_eligibility`` haengt am ``entity_type`` und
        kann diesen Fall strukturell nicht fangen: 28 von 29 beobachteten
        Nicht-Stakeholdern trugen den Typ ``Organization`` — ``Moodle``,
        ``ChatGPT``, ``Magdeburg``, ``AZAV-Zulassung``, ``Kursstart Februar
        2027``. ``organization`` kann nicht auf die Blockliste, weil
        Bildungstraeger, Betriebe und Behoerden legitime Stakeholder sind.

        Ein enger gefasstes Typvokabular hilft ebenfalls nicht: In einem Lauf
        lieferte das Modell ausschliesslich kanonische Typen — und trotzdem
        landeten 16 von 16 Nicht-Stakeholdern in ``Organization``. Der Typ ist
        gleichzeitig legitimes Label und Auffangtopf fuer alles Unklare.

        Die Frage wird deshalb am Namen und am Kontext beantwortet, nicht am
        Label, und in den ohnehin stattfindenden Generierungsaufruf gefaltet.
        """
        if self.language == "de":
            return f"""### Eignungsprüfung (vor allem anderen zu beantworten)

Prüfe zuerst, ob „{entity_name}" überhaupt einen menschlichen Träger haben kann — also ob es Menschen gibt, die für diese Entität sprechen und im Szenario eine eigene Interessenlage vertreten.

Setze `ineligible: true` und begründe knapp in `ineligible_reason`, wenn „{entity_name}" eines der folgenden ist:
- eine Software, ein Modell, ein Werkzeug oder ein technisches System (auch wenn der Typ „{entity_type}" etwas anderes nahelegt)
- ein Ort, eine Stadt, ein Bundesland oder eine Region
- ein Datum, ein Termin, ein Zeitraum oder ein Meilenstein
- ein Dokument, ein Abschnitt, eine Zulassung, ein Verfahren oder ein Regelwerk
- ein Gerät, eine Infrastruktur oder eine Systemkomponente
- ein abstrakter Begriff, ein Sammelbegriff oder das Analysewerkzeug selbst

Der Entitätstyp ist dabei nur ein Hinweis, keine Antwort — er trägt in der Praxis häufig „Organization", auch wenn die Entität eine Software oder eine Stadt ist. Entscheide nach dem Namen und dem Kontext.

Bei `ineligible: true` sind alle übrigen Felder bedeutungslos, müssen aber weiterhin schemagültig sein — sonst wird die Antwort verworfen, drei Versuche scheitern und die Entität landet über den regelbasierten Pfad doch als Persona im Lauf. Verwende genau: display_name und handle je ein Minuszeichen, age 30, gender other, mbti ISTJ, country DE, voice_register neutral-de, leere Strings für bio, persona und profession, leere Liste für interested_topics. Erfinde in diesem Fall KEINE Persona.

Bei `ineligible: false` beantworte die Aufgabe oben wie beschrieben."""

        return f"""### Eligibility check (answer this first)

First decide whether "{entity_name}" can have a human bearer at all — that is, whether there are people who speak for this entity and hold their own stake in the scenario.

Set `ineligible: true` and give a short `ineligible_reason` if "{entity_name}" is any of:
- a piece of software, a model, a tool, or a technical system (even if the type "{entity_type}" suggests otherwise)
- a place, city, state, or region
- a date, deadline, period, or milestone
- a document, section, accreditation, procedure, or set of rules
- a device, infrastructure, or system component
- an abstract concept, an umbrella term, or the analysis tool itself

The entity type is a hint, not an answer — in practice it often reads "Organization" even when the entity is software or a city. Decide from the name and the context.

When `ineligible: true`, all other fields are meaningless but must still be schema-valid — otherwise the response is rejected, three attempts fail and the entity becomes a persona anyway via the rule-based path. Use exactly: display_name and handle each a single hyphen, age 30, gender other, mbti ISTJ, country DE, voice_register neutral-de, empty strings for bio, persona and profession, empty list for interested_topics. Do NOT invent a persona in that case.

When `ineligible: false`, answer the task above as described."""


    @measure_llm_latency(
        operation='persona_generation',
        extract_model=lambda self, *a, **kw: getattr(self, 'model_name', None),
        extract_prompt_chars=None,
    )
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
        demographic_slot: Optional[PersonaDemographicSlot] = None,
    ) -> Dict[str, Any]:
        """
        Use LLM to generate very detailed persona

        Based on entity type:
        - Individual entities: generate specific character profiles
        - Group/institutional entities: generate representative account profiles
        """

        # Issue #1246 (CodeRabbit PR #1257): Prompt-Auswahl und
        # Kollektiv-Behandlung muessen dasselbe Praedikat benutzen. Vorher
        # entschied hier ``_is_individual_entity`` und in
        # ``generate_profile_from_entity`` ``_is_group_entity`` — ein
        # unbekannter Typ wie ``WorkingGroup`` bekam damit den Kollektiv-Prompt
        # und trotzdem die Individuen-Nachbehandlung: Demografie aus dem Slot,
        # Personenname vom Modell, ``persona_kind="individual"`` neben einem
        # Text ueber eine Organisation.
        #
        # Ausgerichtet auf ``_is_group_entity``: nur explizit als Gruppe
        # gefuehrte Typen werden Kollektive. Unbekannte Typen sind in dieser
        # Domaene ueberwiegend deutsche Rollennamen (``Dozent``,
        # ``Betriebsrat``) und damit Personen; sie bekommen jetzt auch den
        # Individuen-Prompt statt einer Beschreibung, die nicht zu ihrer
        # Nachbehandlung passt.
        is_individual = not self._is_group_entity(entity_type)
        detail_level = _resolve_persona_detail_level()
        max_tokens = detail_level['max_tokens']

        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context,
                detail_level=detail_level, demographic_slot=demographic_slot,
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context,
                detail_level=detail_level, demographic_slot=demographic_slot,
            )

        # Issue #1247: Einmal angehaengt statt in beide Prompts kopiert — es ist
        # dieselbe Frage, unabhaengig davon, ob die Entitaet als Individuum oder
        # als Kollektiv gefuehrt wird.
        prompt = f"{prompt}\n\n{self._build_eligibility_prompt_block(entity_name, entity_type)}"

        # Try multiple times until successful or max retry attempts reached
        max_attempts = 3
        last_error = None

        # LLMClient statt rohem OpenAI-Client: kapselt Provider-Detection
        # (MiniMax-thinking-extra_body), strict json_schema-Mode und zentrale
        # JSON-Repair-Logik. force_no_thinking=True deaktiviert M3-Reasoning,
        # das ohne diese Verdrahtung bis zu 63 % des Token-Budgets als
        # lesbaren Text in den content emittiert → kaputtes JSON → Retry-Loop.
        from ..llm.client import LLMClient as _LLMClient

        llm = _LLMClient(
            api_key=self.api_key,
            base_url=self.base_url,
            model=self.model_name,
            # Budget-Enforcement (#984): ohne run_id gibt es keinen Enforcer —
            # Persona-Generierung liefe am harten Run-Budget vorbei.
            run_id=self.run_id,
        )
        messages = [
            {"role": "system", "content": self._get_system_prompt(is_individual)},
            {"role": "user", "content": prompt},
        ]

        for attempt in range(max_attempts):
            try:
                # Strict-json_schema-Mode + force_no_thinking: M3 liefert
                # gültiges JSON nach Schema, ohne Reasoning-Text im content.
                result = llm.chat_json(
                    messages=messages,
                    temperature=0.7 - (attempt * 0.1),
                    max_tokens=max_tokens,
                    # Issue #1246: Der Kollektiv-Prompt fordert die
                    # Personenfelder nicht an — mit dem Individuen-Schema
                    # scheiterte jede Gruppen-Entitaet dreimal und fiel auf
                    # den regelbasierten Pfad zurueck.
                    schema=PersonaProfileSchema if is_individual else CollectivePersonaSchema,
                    schema_name="persona_profile" if is_individual else "collective_persona",
                    context="persona",
                    force_no_thinking=True,
                )

                # chat_json validiert bereits gegen das Pydantic-Schema; die
                # nachfolgenden Fallbacks (bio, persona, voice_register)
                # bleiben als Defensive-Programmierung bestehen.
                if demographic_slot is not None:
                    result["age"] = demographic_slot.age
                    result["gender"] = demographic_slot.gender
                    result["mbti"] = demographic_slot.mbti
                if not result.get("bio"):
                    result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                if not result.get("persona"):
                    result["persona"] = entity_summary or f"{entity_name} is a {entity_type}."

                # voice_register: Fallback vor allgemeiner Validation (kein Retry nötig)
                vr_value = result.get("voice_register")
                if vr_value not in VOICE_REGISTERS:
                    logger.warning(
                        "voice_register fehlt oder ungültig: %r → fallback neutral-de", vr_value
                    )
                    result["voice_register"] = "neutral-de"

                missing_fields = self._validate_profile_metadata(
                    result, is_collective=not is_individual
                )
                if missing_fields:
                    last_error = ValueError(
                        f"Missing required persona metadata: {', '.join(missing_fields)}"
                    )
                    logger.warning(
                        f"LLM persona missing required metadata (attempt {attempt+1}): "
                        f"{', '.join(missing_fields)}"
                    )
                    continue

                return result

            except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
                logger.warning(f"LLM call failed (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # Exponential backoff

        logger.warning(f"LLM persona generation failed ({max_attempts} attempts): {last_error}, using rule-based generation")
        # Issue #1029: Der Ausfall wandert mit ins Profil. Ohne ihn ist ein
        # Platzhalterprofil nach dem Erzeugungszeitpunkt nicht mehr von
        # einem echten zu unterscheiden.
        return self._generate_profile_rule_based(
            entity_name,
            entity_type,
            entity_summary,
            entity_attributes,
            generation_error=(
                f"LLM-Generierung nach {max_attempts} Versuchen fehlgeschlagen: "
                f"{str(last_error)[:160]}"
            ),
        )

    def _validate_profile_metadata(
        self, result: Dict[str, Any], *, is_collective: bool = False
    ) -> List[str]:
        """Validate and normalize structured fields that OASIS actually consumes.

        Issue #1246 (CodeRabbit PR #1257): Fuer Kollektive pruefen nur die
        Felder, die eine Organisation ueberhaupt haben kann. Alter, Geschlecht,
        MBTI und Berufsbezeichnung als fehlend zu melden hiesse, eine
        vollstaendige Antwort dreimal zu verwerfen und auf den regelbasierten
        Pfad zu fallen — dieselbe Falle wie beim Schema.
        """
        missing_fields = []

        if is_collective:
            country = result.get("country")
            if not isinstance(country, str) or not country.strip():
                missing_fields.append("country")
            register = result.get("voice_register")
            if not isinstance(register, str) or register.strip() not in VOICE_REGISTERS:
                missing_fields.append("voice_register")
            return missing_fields

        age = result.get("age")
        if isinstance(age, str) and age.strip().isdigit():
            age = int(age.strip())
            result["age"] = age
        if not isinstance(age, int) or age < 18 or age > 75:
            missing_fields.append("age")

        gender = result.get("gender")
        if isinstance(gender, str):
            normalized_gender = gender.strip().lower()
            if normalized_gender in self.VALID_PROFILE_GENDERS:
                result["gender"] = normalized_gender
            else:
                missing_fields.append("gender")
        else:
            missing_fields.append("gender")

        mbti = result.get("mbti")
        if isinstance(mbti, str):
            normalized_mbti = mbti.strip().upper()
            if normalized_mbti in self.MBTI_TYPES:
                result["mbti"] = normalized_mbti
            else:
                missing_fields.append("mbti")
        else:
            missing_fields.append("mbti")

        country = result.get("country")
        if isinstance(country, str) and country.strip():
            country_map = {
                "germany": "DE",
                "deutschland": "DE",
                "united states": "US",
                "usa": "US",
            }
            country_value = country.strip()
            result["country"] = country_map.get(country_value.lower(), country_value.upper())
        else:
            missing_fields.append("country")

        vr = result.get("voice_register")
        if vr is not None and vr not in VOICE_REGISTERS:
            missing_fields.append(f"voice_register: invalid value '{vr}'")

        return missing_fields

    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """Try to fix corrupted JSON"""
        import re

        # 1. First try to fix truncated case via the centralized repair helper
        # (Issue #869). Returns the repaired payload or None when no
        # structural recovery is possible — in which case we keep the
        # original content and let the regex/json.loads fallbacks below
        # attempt their own recovery (newline sanitization, partial-field
        # extraction, etc.).
        repaired = _try_repair_truncated_json(content)
        if repaired is not None:
            content = repaired

        # 2. Try to extract JSON portion
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()

            # 3. Handle newline issues in strings
            # Find all string values and replace newlines
            def fix_string_newlines(match):
                s = match.group(0)
                # Replace actual newlines in string with spaces
                s = s.replace('\n', ' ').replace('\r', ' ')
                # Replace excess spaces
                s = re.sub(r'\s+', ' ', s)
                return s

            # Match JSON string values
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)

            # 4. Try to parse
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError:
                # 5. If still failed, try more aggressive fix
                try:
                    # Remove all control characters
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # Replace all consecutive whitespace
                    json_str = re.sub(r'\s+', ' ', json_str)
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

        # 6. Try to extract partial information from content
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  # May be truncated

        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name} is a {entity_type}.")

        # If extracted meaningful content, mark as fixed
        if bio_match or persona_match:
            logger.info("Extracted partial information from corrupted JSON")
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }

        # 7. Complete failure, return basic structure
        logger.warning("JSON fix failed, returning basic structure")
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name} is a {entity_type}."
        }
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        """Get system prompt — language-aware (de/en)."""
        if self.language == "de":
            return (
                "Du erstellst realistische Social-Media-Personas für eine Meinungssimulation. "
                "Ziel: möglichst nah an der bekannten Realität bleiben. "
                "Antworte ausschließlich mit gültigem JSON ohne unescapte Zeilenumbrüche. "
                "Alle Texte (insbesondere bio und persona) müssen auf Deutsch verfasst sein."
            )
        return (
            "You are an expert in generating social media user profiles. Generate detailed, realistic "
            "personas for opinion simulation that maximize restoration of existing reality. Must return "
            "valid JSON format with all string values containing no unescaped newlines. Use English."
        )

    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
        detail_level: Optional[dict] = None,
        demographic_slot: Optional[PersonaDemographicSlot] = None,
    ) -> str:
        """Build detailed persona prompt for individual entities — language-aware."""

        detail = detail_level if detail_level is not None else _resolve_persona_detail_level()
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "Keine"
        context_str = context[:detail['context_limit']] if context else "Keine zusätzlichen Informationen"

        _quota_block_de = build_name_quota_prompt_block()
        _industry_block_de = build_industry_quota_prompt_block(self._industry_quota_plan)
        _slot_block = (
            self._build_demographic_slot_prompt_block(demographic_slot)
            if demographic_slot is not None
            else ""
        )

        if self.language == "de":
            return f"""Erzeuge eine detaillierte Social-Media-Persona für die folgende Entität. Bleibe nah an der bekannten Realität.

Name der Entität: {entity_name}
Typ: {entity_type}
Zusammenfassung: {entity_summary}
Attribute: {attrs_str}

Kontext:
{context_str}

{_quota_block_de}

{_industry_block_de}

{_slot_block}

Antworte als JSON mit folgenden Feldern:

1. display_name: Echter Vor- und Nachname einer Person im DACH-Raum — entsprechend der obigen Namensverteilung. WICHTIG: Nur dann den tatsächlichen Namen einer realen Person nehmen, wenn "{entity_name}" selbst bereits ein Personenname ist UND diese Person in der Realität so heißt. Bei Rollen ("IT-Umschüler"), Themen ("GraphRAG"), Produkten ("Agora") oder Berufsbezeichnungen IMMER einen anderen, frei gewählten Namen nehmen — nicht den Namen einer im Kontext erwähnten Person übernehmen. Jede Persona soll einen EIGENEN Namen haben.
2. handle: Kurzes Social-Media-Handle in Kleinbuchstaben ohne Leerzeichen (z. B. "lena_hoffmann" oder "marcelschmitz"). Keine Zahlen anhängen — das passiert später.
3. bio: Social-Media-Bio, max. 200 Zeichen, auf Deutsch.
4. persona: Ausführliche Personenbeschreibung ({detail['word_count_de']}, durchgehend Fließtext, auf Deutsch). Enthalten muss sein:
   - Eckdaten (Alter, Beruf, Bildungsweg, Wohnort)
   - Hintergrund (prägende Erfahrungen, Bezug zu Ereignissen, soziales Umfeld)
   - Persönlichkeit (MBTI, Kernzüge, emotionaler Ausdruck)
   - Social-Media-Verhalten (Posting-Frequenz, Themenpräferenzen, Stil, Sprache)
   - Haltungen und Meinungen (zu zentralen Themen, was emotional triggert)
   - Eigenheiten (Sprachmarotten, besondere Erfahrungen, Hobbys)
   - Erinnerungen (Verbindung zu den Ereignissen, frühere Reaktionen)
5. age: Alter als Ganzzahl, frei gewählt im Bereich 18–75 — variiere bewusst, vermeide Standardalter wie 30/35/40.
6. gender: Genau einer von "male", "female", "nonbinary". KEIN "other" — das ist Institutionen vorbehalten.
7. mbti: MBTI-Typ (z. B. INTJ, ENFP)
8. country: ISO-Land in Englisch (z. B. "DE", "AT", "CH")
9. profession: Beruf (auf Deutsch)
10. interested_topics: Array deutscher Themen-Strings
11. voice_register: Genau einer von "formal-de" | "neutral-de" | "technical-de" | "skeptisch-de".
    Wähle passend zu Beruf und Bildungsniveau der Persona:
    - "formal-de": gehoben, Sie-Form, Behörden-/Konzern-Ton, keine Anglizismen (z. B. Beamtin, Juristin).
    - "neutral-de": alltagssprachlich, Du-Form möglich, keine Werbesprache (z. B. Umschüler, Elternteil).
    - "technical-de": präzise, Fachvokabular, knapp, kein Marketing (z. B. Senior-Entwicklerin, DevOps-Ingenieur).
    - "skeptisch-de": kritisch-distanziert, hinterfragend, Anführungszeichen für Buzzwords (z. B. Aktivistin, Journalist).

Wichtig:
- Antworte ausschließlich mit JSON, keine zusätzlichen Erklärungen.
- Alle Texte in bio und persona sind auf Deutsch.
- Keine unescapten Zeilenumbrüche in Strings.
- age muss Ganzzahl, gender muss "male"/"female"/"nonbinary" sein.
- display_name muss ein echter Personenname sein, nicht der abstrakte Entity-Begriff.
- voice_register MUSS eines der vier exakten Werte sein.
"""

        _quota_block_en = build_name_quota_prompt_block_en()
        _industry_block_en = build_industry_quota_prompt_block_en(self._industry_quota_plan)

        return f"""Generate a detailed social media user persona for the entity, maximizing restoration of existing reality.

Entity Name: {entity_name}
Entity Type: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

{_quota_block_en}

{_industry_block_en}

{_slot_block}

Please generate JSON containing the following fields:

1. display_name: Realistic first + last name of a person — following the name distribution above (DACH Mikrozensus 2024). IMPORTANT: Only use a real person's actual name if "{entity_name}" itself IS a personal name AND matches reality. For roles, topics, products, or job titles ALWAYS pick a different, freshly chosen name — do NOT reuse names of people mentioned in the context. Every persona must have its own unique name.
2. handle: Short lowercase social handle without spaces (e.g. "lena_hoffmann"). Do not append digits.
3. bio: Social media bio, 200 characters
4. persona: Detailed persona description ({detail['word_count_en']} of pure text), must include:
   - Basic information (age, profession, educational background, location)
   - Personal background (important experiences, event associations, social relationships)
   - Personality traits (MBTI type, core personality, emotional expression)
   - Social media behavior (posting frequency, content preferences, interaction style, language characteristics)
   - Positions and views (attitudes toward topics, content that may provoke/touch emotions)
   - Unique features (catchphrases, special experiences, personal interests)
   - Personal memories (important part of persona, introduce this individual's association with events and their existing actions/reactions in events)
5. age: Age as integer, pick deliberately across 18–75 — vary it, avoid default ages like 30.
6. gender: Exactly one of "male", "female", "nonbinary". Do NOT use "other" — that is reserved for institutions.
7. mbti: MBTI type (e.g., INTJ, ENFP)
8. country: Country ISO code (e.g., "DE", "AT", "CH")
9. profession: Profession
10. interested_topics: Array of interested topics
11. voice_register: Exactly one of "formal-de" | "neutral-de" | "technical-de" | "skeptisch-de".
    Choose based on the persona's profession and education:
    - "formal-de": elevated style, formal address, bureaucratic tone, no anglicisms (e.g. civil servant, lawyer).
    - "neutral-de": everyday language, casual address, no marketing speak (e.g. trainee, parent).
    - "technical-de": precise, specialist vocabulary, concise, no marketing (e.g. senior developer, DevOps engineer).
    - "skeptisch-de": critical, questioning, uses quotation marks for buzzwords (e.g. activist, journalist).

Important:
- All field values must be strings or numbers, do not use newlines
- persona must be a coherent text description
- Use English
- display_name must be a realistic personal name, not the abstract entity label.
- age must be a valid integer, gender must be "male"/"female"/"nonbinary".
- voice_register MUST be one of the four exact values listed above.
"""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
        detail_level: Optional[dict] = None,
        demographic_slot: Optional[PersonaDemographicSlot] = None,
    ) -> str:
        """Build the collective persona prompt for group/institutional entities.

        Issue #1246: Dieser Prompt forderte bis zu diesem Slice einen erfundenen
        **Menschen** als Repraesentant der Organisation an — mit Alter,
        Geschlecht, MBTI-Typ, Bildungsweg und "praegenden Erfahrungen". Eine
        gGmbH hat davon nichts. Der Generator musste all das erfinden, und
        genau so entstand aus dem Bildungstraeger "Nordharz Bildungswerk gGmbH"
        ein "Juergen Hartmann, 57, Dozent fuer IT-Umschulungen und
        Betriebsratsmitglied" — weder "Dozent" noch "Betriebsratsmitglied" war
        aus der Quellentitaet ableitbar.

        Der Prompt beschreibt jetzt das Kollektiv selbst: Auftrag, Interessen,
        Positionen, Kommunikationsstil. Eine Kollektiv-Persona hat keine Vita,
        also nichts, was erfunden werden koennte. Der Demografie-Slot wird
        bewusst nicht eingespielt.

        Das ist eine Darstellungs-, keine Architekturaenderung: Der
        Simulations-Agent bleibt ein Agent und fuehrt weiterhin individuelle
        Aktionen aus. Was sich aendert, ist die Selbstbeschreibung.
        """

        detail = detail_level if detail_level is not None else _resolve_persona_detail_level()
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "Keine"
        context_str = context[:detail['context_limit']] if context else "Keine zusätzlichen Informationen"

        if self.language == "de":
            return f"""Beschreibe die folgende Organisation / Gruppe als **kollektive Stimme** im Szenario. Sie äußert sich als Organisation — nicht als erfundene Einzelperson. Erfinde KEINE Person, KEINEN Namen, KEINEN Lebenslauf.

Organisation/Gruppe: {entity_name}
Typ: {entity_type}
Zusammenfassung: {entity_summary}
Attribute: {attrs_str}

Kontext:
{context_str}

Antworte als JSON mit folgenden Feldern:

1. bio: Kurzbeschreibung der Organisation, max. 200 Zeichen, Deutsch. Was sie ist und wofür sie steht.
2. persona: Ausführliche Beschreibung der Organisation ({detail['word_count_de']}, Fließtext, Deutsch). Enthalten:
   - Auftrag und Zuständigkeit (wofür ist sie da, woran wird sie gemessen)
   - Verhältnis zum Szenario (was betrifft sie daran konkret)
   - Interessenlage (was gewinnt sie, was verliert sie)
   - Bekannte Positionen und typische Argumentationslinien
   - Kommunikationsverhalten (wie äußert sie sich öffentlich, wie förmlich, wie schnell)
   - Konfliktlinien zu anderen Beteiligten
   Schreibe durchgehend über die Organisation ("Der Träger…", "Die Kammer…"), nie über eine Einzelperson.
3. country: ISO-Land in Englisch (z. B. "DE", "AT", "CH")
4. interested_topics: Array deutscher Themen-Strings
5. voice_register: Genau einer von "formal-de" | "neutral-de" | "technical-de" | "skeptisch-de".
    Passend zu Auftrag und Kontext von "{entity_name}":
    - "formal-de": gehoben, Sie-Form, Behörden-/Konzern-Ton, keine Anglizismen.
    - "neutral-de": alltagssprachlich, Du-Form möglich, keine Werbesprache.
    - "technical-de": präzise, Fachvokabular, knapp, kein Marketing.
    - "skeptisch-de": kritisch-distanziert, hinterfragend, Anführungszeichen für Buzzwords.

Wichtig:
- Antworte ausschließlich mit JSON.
- Texte auf Deutsch.
- Keine unescapten Zeilenumbrüche.
- KEIN Alter, KEIN Geschlecht, KEIN MBTI-Typ, KEINE Berufsbezeichnung — eine Organisation hat davon nichts.
- KEIN erfundener Personenname. Die Organisation spricht unter ihrem eigenen Namen.
- voice_register MUSS eines der vier exakten Werte sein.
"""

        return f"""Describe the following organization/group as a **collective voice** in the scenario. It speaks as an organization — not as an invented individual. Do NOT invent a person, a name, or a biography.

Organization/Group: {entity_name}
Entity Type: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

Please generate JSON containing the following fields:

1. bio: Short description of the organization, 200 characters. What it is and what it stands for.
2. persona: Detailed description of the organization ({detail['word_count_en']} of pure text), must include:
   - Mandate and remit (what it exists for, what it is measured on)
   - Relationship to the scenario (what concretely affects it)
   - Interests (what it stands to gain or lose)
   - Known positions and typical lines of argument
   - Communication behaviour (how it speaks publicly, how formal, how fast)
   - Lines of conflict with other participants
   Write throughout about the organization, never about an individual.
3. country: Country ISO code (e.g., "DE", "AT", "CH")
4. interested_topics: Array of topics
5. voice_register: Exactly one of "formal-de" | "neutral-de" | "technical-de" | "skeptisch-de".
    Choose based on the mandate of "{entity_name}":
    - "formal-de": elevated style, formal address, bureaucratic tone, no anglicisms.
    - "neutral-de": everyday language, casual address, no marketing speak.
    - "technical-de": precise, specialist vocabulary, concise, no marketing.
    - "skeptisch-de": critical, questioning, uses quotation marks for buzzwords.

Important:
- All field values must be strings or arrays, no null values allowed
- NO age, NO gender, NO MBTI type, NO profession — an organization has none of these.
- NO invented personal name. The organization speaks under its own name.
- persona must be coherent, no newlines.
- voice_register MUST be one of the four exact values listed above.
- Use English."""
    
    @staticmethod
    def _rule_based_voice_register(entity_type: str, profession: str = "") -> str:
        """Minimale Heuristik: leite voice_register aus entity_type/profession ab."""
        combined = (entity_type + " " + profession).lower()
        if any(k in combined for k in ("beamt", "jurist", "lawyer", "governmentagency", "official", "verwalt")):
            return "formal-de"
        if any(k in combined for k in ("develop", "engineer", "devops", "software", "tech", "it_admin", "faculty")):
            return "technical-de"
        if any(k in combined for k in ("activist", "journalist", "ngo", "redakteur", "aktivist")):
            return "skeptisch-de"
        return "neutral-de"

    def _report_persona_degradation(
        self,
        profiles: List[Optional[OasisAgentProfile]],
        degradations: "DegradationCollector",
    ) -> None:
        """Meldet Platzhalterprofile einmal für die ganze Runde (Issue #1029).

        Ein einzelner Fallback ist unauffällig; erst die Anzahl zeigt, ob
        die Runde überhaupt echte Stimmen hervorgebracht hat.

        Die Meldung hängt an ``generation_error``, nicht an
        ``generation_source``: Bei ``use_llm=False`` ist der regelbasierte
        Pfad die bewusste Wahl und keine Degradierung.
        """
        present = [p for p in profiles if p]
        failed = [p for p in present if p.generation_error]
        if not failed:
            return

        first_error = failed[0].generation_error or "unbekannt"
        degradations.record(
            kind=DegradationKind.PERSONA_RULE_BASED_FALLBACK,
            severity=DegradationSeverity.WARNING,
            detail=(
                f"{len(failed)} von {len(present)} Personas konnten nicht vom "
                "Modell erzeugt werden und sind regelbasierte Platzhalter. "
                "Ihre Beiträge tragen keine belastbaren Aussagen. "
                f"Erste Ursache: {first_error}"
            ),
            context={
                "fallback_personas": len(failed),
                "total_personas": len(present),
            },
        )

    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        generation_error: Optional[str] = None,
        demographic_slot: Optional[PersonaDemographicSlot] = None,
    ) -> Dict[str, Any]:
        """Regelbasiertes Profil — immer als solches gekennzeichnet (Issue #1029).

        Diese Profile nehmen regulär an der Simulation teil, und ihre
        Beiträge waren im Report bis dahin nicht von echten Personas zu
        unterscheiden. Die Kennzeichnung passiert hier und nicht beim
        Aufrufer, damit sie keine Aufrufstelle vergessen kann.

        ``generation_error`` unterscheidet die beiden Wege hierher: eine
        bewusste Wahl (``use_llm=False``, kein Fehler) von einem Ausfall
        nach drei gescheiterten LLM-Versuchen. Nur der zweite Fall ist
        eine Degradierung.
        """
        payload = self._build_rule_based_payload(
            entity_name, entity_type, entity_summary, entity_attributes, demographic_slot
        )
        payload["generation_source"] = "rule_based"
        if generation_error:
            payload["generation_error"] = generation_error
        return payload

    def _build_collective_payload(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
    ) -> Dict[str, Any]:
        """Regelbasierte Kollektiv-Persona fuer Gruppen-Entitaeten (#1246).

        Bewusst eine eigene Methode und kein Zweig im Personen-Pfad: Alter,
        Geschlecht, Persoenlichkeitstyp und Beruf sind die vier Felder, die es
        an einer Institution nicht zu wissen gibt. Wer sie hier fuellt,
        erfindet — genau so wurde aus einem Bildungstraeger ein "Dozent und
        Betriebsratsmitglied".
        """
        return {
            "display_name": entity_name,
            "handle": self._generate_username(entity_name),
            "bio": (entity_summary[:150] if entity_summary else entity_name),
            "persona": (
                f"{entity_name} ist eine {entity_type}-Entität im Szenario und "
                f"äußert sich als Organisation, nicht als Einzelperson. "
                f"{entity_summary}"
            ).strip(),
            "age": None,
            "gender": None,
            "mbti": None,
            "country": "DE",
            "profession": None,
            "interested_topics": ["Organisation", "Positionen"],
            "voice_register": self._rule_based_voice_register(entity_type.lower(), ""),
        }

    def _build_rule_based_payload(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        demographic_slot: Optional[PersonaDemographicSlot] = None,
    ) -> Dict[str, Any]:
        """Generate basic persona using rules"""

        # Generate different personas based on entity type
        entity_type_lower = entity_type.lower()
        assigned_gender = (
            demographic_slot.gender if demographic_slot is not None else self._pick_individual_gender()
        )
        assigned_age = demographic_slot.age if demographic_slot is not None else None
        assigned_mbti = demographic_slot.mbti if demographic_slot is not None else None

        # Issue #1246: Kollektiv-Fallback. Sichtbar vor allen Personenzweigen,
        # damit eine Organisation gar nicht erst in einen Pfad geraet, der ihr
        # eine Vita andichtet.
        if self._is_group_entity(entity_type_lower):
            return self._build_collective_payload(entity_name, entity_type, entity_summary)

        # Personen-Fallback: echter DACH-Name + breite Altersstreuung + realistisches Gender.
        if entity_type_lower in ["student", "alumni"]:
            dach = self._pick_dach_name(assigned_gender)
            return {
                "display_name": dach,
                "handle": dach.lower().replace(" ", "_"),
                "bio": f"{entity_type} with interests in academics and social issues.",
                "persona": f"{dach} ist {entity_type.lower()} und aktiv in akademischen und sozialen Diskussionen. Teilt Perspektiven und vernetzt sich mit Peers.",
                "age": assigned_age if assigned_age is not None else random.randint(18, 32),
                "gender": assigned_gender,
                "mbti": assigned_mbti or random.choice(self.MBTI_TYPES),
                "country": "DE",
                "profession": "Student",
                "interested_topics": ["Bildung", "Gesellschaft", "Technologie"],
                "voice_register": self._rule_based_voice_register(entity_type_lower, "Student"),
            }

        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            dach = self._pick_dach_name(assigned_gender)
            profession_str = entity_attributes.get("occupation", "Fachexpertin/Fachexperte")
            return {
                "display_name": dach,
                "handle": dach.lower().replace(" ", "_"),
                "bio": "Expert and thought leader in their field.",
                "persona": f"{dach} ist eine anerkannte Fachperson und teilt Einschätzungen zu relevanten Themen. Bekannt für Expertise und Einfluss im öffentlichen Diskurs.",
                "age": assigned_age if assigned_age is not None else random.randint(32, 68),
                "gender": assigned_gender,
                "mbti": assigned_mbti or random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "country": "DE",
                "profession": profession_str,
                "interested_topics": ["Politik", "Wirtschaft", "Gesellschaft"],
                "voice_register": self._rule_based_voice_register(entity_type_lower, profession_str),
            }

        # Institutionen-Fallback: ECHTE PERSON als Repräsentant/in der Organisation.
        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            dach = self._pick_dach_name(assigned_gender)
            return {
                "display_name": dach,
                "handle": dach.lower().replace(" ", "_"),
                "bio": f"Redaktion bei {entity_name} | Nachrichten, Analysen, Einordnung",
                "persona": f"{dach} arbeitet als Redakteur:in bei {entity_name} und teilt berufliche Einschätzungen zu aktuellen Themen sowie gelegentlich persönliche Meinungen.",
                "age": assigned_age if assigned_age is not None else random.randint(28, 58),
                "gender": assigned_gender,
                "mbti": assigned_mbti or random.choice(self.MBTI_TYPES),
                "country": "DE",
                "profession": f"Redakteur:in bei {entity_name}",
                "interested_topics": ["Nachrichten", "Aktuelles", "Öffentlichkeit"],
                "voice_register": self._rule_based_voice_register(entity_type_lower, "journalist"),
            }

        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            dach = self._pick_dach_name(assigned_gender)
            return {
                "display_name": dach,
                "handle": dach.lower().replace(" ", "_"),
                "bio": f"Mitarbeiter:in bei {entity_name} | spricht aus der Praxis",
                "persona": f"{dach} ist bei {entity_name} beschäftigt und vertritt die Organisation öffentlich — mal mit offizieller Position, mal mit persönlicher Sicht aus dem Arbeitsalltag.",
                "age": assigned_age if assigned_age is not None else random.randint(25, 62),
                "gender": assigned_gender,
                "mbti": assigned_mbti or random.choice(self.MBTI_TYPES),
                "country": "DE",
                "profession": f"Mitarbeiter:in bei {entity_name}",
                "interested_topics": ["Politik", "Community", "Arbeit"],
                "voice_register": self._rule_based_voice_register(entity_type_lower, ""),
            }

        else:
            return self._build_generic_person_payload(
                entity_name=entity_name,
                entity_type=entity_type,
                entity_summary=entity_summary,
                assigned_gender=assigned_gender,
                assigned_age=assigned_age,
                assigned_mbti=assigned_mbti,
            )

    def _build_generic_person_payload(
        self,
        *,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        assigned_gender: str,
        assigned_age: Optional[int],
        assigned_mbti: Optional[str],
    ) -> Dict[str, Any]:
        """Default-Pfad: Entitaet ohne eigenen Zweig wird Person mit breiter Streuung.

        Issue #1246: Zwei Defekte sassen hier. Der Personatext war die blanke
        ``entity_summary`` — ohne den Namen, unter dem die Persona auftritt; der
        Interview-Prompt setzte damit "Du bist Maria Martin" und eine
        Beschreibung zusammen, die niemanden benennt. Und ``profession`` trug
        den Entitaetstyp, was Berufsbezeichnungen wie "AIProvider" oder
        "WorkingGroup" ergab. Wo nichts abzuleiten ist, bleibt das Feld leer.
        """
        dach = self._pick_dach_name(assigned_gender)
        persona = (
            f"{dach} steht im Szenario für „{entity_name}“. {entity_summary}".strip()
            if entity_summary
            else f"{dach} nimmt aktiv an sozialen Diskussionen teil."
        )
        return {
            "display_name": dach,
            "handle": dach.lower().replace(" ", "_"),
            "bio": entity_summary[:150] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": persona,
            "age": assigned_age if assigned_age is not None else random.randint(20, 70),
            "gender": assigned_gender,
            "mbti": assigned_mbti or random.choice(self.MBTI_TYPES),
            "country": "DE",
            "profession": None,
            "interested_topics": ["Allgemein", "Gesellschaft"],
            "voice_register": self._rule_based_voice_register(
                entity_type.lower(), entity_type
            ),
        }
    
    def set_graph_id(self, graph_id: str):
        """Set knowledge graph ID for knowledge graph search"""
        self.graph_id = graph_id
    
    def _backfill_rejected_slots(
        self,
        *,
        profiles: List[Optional[OasisAgentProfile]],
        entities: List[EntityNode],
        reserve_entities: List[EntityNode],
        use_llm: bool,
        rejected: List["PersonaIneligible"],
    ) -> None:
        """Besetzt abgelehnte Persona-Slots aus dem Reservepool nach (#1247).

        Der Eignungsfilter ueber die Blockliste laeuft vor dem ``max_agents``-Cap
        und ist damit unproblematisch. Die typunabhaengige Pruefung faellt aber
        erst im Generierungsaufruf, also *nach* dem Cap — eine Ablehnung dort
        liess den Platz bisher ersatzlos leer.

        Sequentiell und nicht parallel: die Reserve ist klein (die Differenz
        zwischen Kandidatenpool und Cap), und jeder Nachrücker kann selbst
        abgelehnt werden, was einen weiteren Zug aus derselben Liste erfordert.
        Ein Parallelisieren brauchte eine Koordination, die den Aufwand nicht
        rechtfertigt.

        Mutiert ``profiles`` **und** ``entities`` in place. Beides ist noetig:
        ``_phase_generate_profiles`` reicht seine Entity-Liste an
        ``SimulationConfigGenerator.generate_config`` weiter. Ohne den Tausch
        bekaeme das nachbesetzte Profil den ``AgentConfig`` und die
        Initial-Post-Klassifikation der abgelehnten Entitaet — eine
        Honorarkraft liefe dann mit UUID, Name, Typ und Aktivitaetsprofil von
        Moodle (CodeRabbit PR #1258).
        """
        slot_types = {
            idx: (entity.get_entity_type() or "Entity")
            for idx, entity in enumerate(entities)
        }
        open_slots = [idx for idx, profile in enumerate(profiles) if profile is None]
        if not open_slots:
            return

        reserve_slots = self._build_demographic_slots(reserve_entities)
        used: set[int] = set()
        filled = 0

        def _next_candidate(preferred_type: Optional[str]) -> Optional[int]:
            """Naechster unverbrauchter Reserve-Index, Typgleichheit bevorzugt.

            Issue #1247 (CodeRabbit PR #1258): Ohne Typpraeferenz verbraucht die
            Nachbesetzung stur den naechsten Eintrag. Gehoert der einer anderen
            Rollenfamilie, faellt ein aktiver ``PersonaQuotaPlan`` anschliessend
            durch ``_validate_persona_quota`` — und auch ohne Plan verschwindet
            die Typvertretung, die das Round-Robin des Caps gerade gesichert
            hat, obwohl weiter hinten ein gleichartiger Kandidat steht.
            """
            if preferred_type:
                for idx, entity in enumerate(reserve_entities):
                    if idx in used:
                        continue
                    if (entity.get_entity_type() or "Entity") == preferred_type:
                        return idx
            for idx in range(len(reserve_entities)):
                if idx not in used:
                    return idx
            return None

        for slot_idx in open_slots:
            preferred = slot_types.get(slot_idx) if slot_types else None
            while True:
                reserve_index = _next_candidate(preferred)
                if reserve_index is None:
                    break
                candidate = reserve_entities[reserve_index]
                candidate_slot = reserve_slots[reserve_index]
                used.add(reserve_index)
                try:
                    profiles[slot_idx] = self.generate_profile_from_entity(
                        entity=candidate,
                        user_id=slot_idx,
                        use_llm=use_llm,
                        demographic_slot=candidate_slot,
                    )
                except PersonaIneligible as rejection:
                    rejected.append(rejection)
                    continue
                except Exception as exc:  # noqa: BLE001 — Nachrücker duerfen den Lauf nicht kippen
                    logger.warning(
                        "Nachbesetzung fuer Slot %d fehlgeschlagen (%s): %r",
                        slot_idx,
                        candidate.name,
                        exc,
                    )
                    continue
                # Die Entity am selben Index mittauschen, damit die
                # Config-Generierung den Nachruecker beschreibt und nicht die
                # abgelehnte Entitaet.
                if slot_idx < len(entities):
                    entities[slot_idx] = candidate
                filled += 1
                break

        logger.info(
            "Persona-Eligibility: %d Kandidat(en) abgelehnt, %d von %d freien "
            "Plaetzen aus der Reserve nachbesetzt (Reserve: %d Kandidaten). "
            "Abgelehnt: %s",
            len(rejected),
            filled,
            len(open_slots),
            len(reserve_entities),
            ", ".join(f"{r.entity_name} ({r.entity_type})" for r in rejected[:10]),
        )

    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: Optional[int] = None,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit",
        degradations: Optional["DegradationCollector"] = None,
        reserve_entities: Optional[List[EntityNode]] = None,
    ) -> List[OasisAgentProfile]:
        """
        Generate Agent Profiles in batch from entities (supports parallel generation)

        Args:
            entities: Entity list
            use_llm: Whether to use LLM to generate detailed personas
            progress_callback: Progress callback function (current, total, message)
            graph_id: Knowledge graph ID for knowledge graph search to get richer context
            parallel_count: Number of parallel LLM-Roundtrips. If None, falls back to
                env ``AGORA_PARALLEL_PERSONA_COUNT`` (default 10). Cloud-LLM-Setups
                (Ollama-Bridge gegen gemini-3-flash, qwen3-coder:cloud usw.) vertragen
                10–15 parallele Requests; lokales Ollama sollte auf 3–5 reduziert werden,
                um KV-Cache-Trashing zu vermeiden.
            realtime_output_path: Real-time output file path (if provided, write after each generation)
            output_platform: Output platform format ("reddit" or "twitter")
            degradations: optionaler Sammler für stille Teilausfälle
                (Issue #1029). Gemeldet wird einmal am Ende, mit der Anzahl
                der Platzhalterprofile — nicht pro Persona.

        Returns:
            List of Agent Profiles
        """
        import concurrent.futures
        from threading import Lock

        from .sim.cancel_flag import is_cancel_requested

        if parallel_count is None:
            parallel_count = int(
                _get_settings().effective_value('AGORA_PARALLEL_PERSONA_COUNT')
            )
        
        # Set graph_id for knowledge graph search
        if graph_id:
            self.graph_id = graph_id

        total = len(entities)
        profiles = [None] * total  # Pre-allocate list to maintain order
        completed_count = [0]  # Use list for modification in closure
        lock = Lock()
        demographic_slots = self._build_demographic_slots(entities)
        # Issue #1247: abgelehnte Kandidaten, gesammelt fuer die Nachbesetzung.
        rejected: List[PersonaIneligible] = []

        # Helper function for real-time file writing
        def save_profiles_realtime():
            """Real-time save generated profiles to file"""
            if not realtime_output_path:
                return

            with lock:
                # Filter generated profiles
                existing_profiles = [p for p in profiles if p is not None]
                if not existing_profiles:
                    return

                try:
                    if output_platform == "reddit":
                        # Reddit JSON format
                        profiles_data = [p.to_reddit_format() for p in existing_profiles]
                        with open(realtime_output_path, 'w', encoding='utf-8') as f:
                            json.dump(profiles_data, f, ensure_ascii=False, indent=2)
                    else:
                        # Twitter CSV format
                        import csv
                        profiles_data = [p.to_twitter_format() for p in existing_profiles]
                        if profiles_data:
                            # Issue #1246 (CodeRabbit PR #1257): Spaltenmenge
                            # ueber ALLE Profile vereinigen. ``to_twitter_format``
                            # laesst nicht gesetzte Felder weg, und Kollektive
                            # haben garantiert kein Alter, Geschlecht oder MBTI.
                            # War das erste fertige Profil ein Kollektiv, warf
                            # jedes spaetere Individualprofil
                            # "dict contains fields not in fieldnames" — der
                            # Fehler wurde unten geschluckt und die
                            # Realtime-Datei blieb ab da veraltet.
                            fieldnames: List[str] = []
                            for row in profiles_data:
                                for key in row:
                                    if key not in fieldnames:
                                        fieldnames.append(key)
                            with open(realtime_output_path, 'w', encoding='utf-8', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
                                writer.writeheader()
                                writer.writerows(profiles_data)
                except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
                    logger.warning(f"Real-time profile save failed: {e}")
        
        def generate_single_profile(idx: int, entity: EntityNode) -> tuple:
            """Worker function to generate single profile"""
            entity_type = entity.get_entity_type() or "Entity"

            try:
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=idx,
                    use_llm=use_llm,
                    demographic_slot=demographic_slots[idx],
                )

                # Real-time output generated persona to console and log
                self._print_generated_profile(entity.name, entity_type, profile)

                return idx, profile, None

            except PersonaIneligible as rejection:
                # Issue #1247: Ablehnung ist kein Fehlschlag. Der Slot bleibt
                # leer und wird aus dem Reservepool nachbesetzt — vor diesem
                # Slice bekam jede Entitaet, die den Generator erreichte, eine
                # Persona, auch "Moodle" und "Kursstart Februar 2027".
                with lock:
                    rejected.append(rejection)
                return idx, None, None

            except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
                logger.error(f"Failed to generate persona for entity {entity.name}: {str(e)}")
                # Create a fallback profile
                fallback_profile = OasisAgentProfile(
                    user_id=idx,
                    user_name=self._generate_username(entity.name),
                    name=entity.name,
                    bio=f"{entity_type}: {entity.name}",
                    persona=entity.summary or "A participant in social discussions.",
                    source_entity_uuid=entity.uuid,
                    source_entity_type=entity_type,
                    # Issue #1029: Notprofil nach einem Ausfall — noch
                    # dünner als das regelbasierte, also erst recht nicht
                    # als echte Stimme zu behandeln.
                    generation_source="rule_based",
                    generation_error=str(e)[:160],
                )
                return idx, fallback_profile, str(e)

        logger.info(
            "Starting parallel generation of %d agent personas (parallel count: %d)",
            total,
            parallel_count,
        )

        # Detect active gevent monkey-patching so we can pick the cooperative Pool.
        # ``gevent.monkey.is_patched()`` (ohne Argument) liefert seit gevent 23.x
        # keinen "socket"-Status mehr — die öffentliche API ist
        # ``monkey.is_module_patched(name)``. Wir verwenden genau die, damit
        # der Import-Fallback eng bleibt und Programmierfehler nicht
        # verschluckt werden.
        try:
            from gevent import monkey
        except ImportError:
            is_gevent = False
        else:
            is_gevent = monkey.is_module_patched("socket")

        def _process_result(result_idx: int, profile: OasisAgentProfile, error: str | None) -> None:
            """Unified per-result handling: store profile, write realtime file, report progress, log."""
            entity = entities[result_idx]
            entity_type = entity.get_entity_type() or "Entity"
            profiles[result_idx] = profile

            with lock:
                completed_count[0] += 1
                current = completed_count[0]

            # Real-time file writing
            save_profiles_realtime()

            if progress_callback:
                progress_callback(
                    current,
                    total,
                    f"Completed {current}/{total}: {entity.name} ({entity_type})"
                )

            if error:
                logger.warning(f"[{current}/{total}] {entity.name} using fallback persona: {error}")
            else:
                logger.info(f"[{current}/{total}] Successfully generated persona: {entity.name} ({entity_type})")

        # Issue B2 (PLAN.md „Abbrechen & Pause"): kooperativer Abbruch der
        # Persona-Generierung. Bereits gestartete Persona-Generierungen
        # dürfen auslaufen — das ist akzeptiert (kein hartes Kill der
        # aktuell laufenden Anfrage). Nur das Nachlegen NEUER Arbeit stoppt
        # sofort. ``cancel_requested`` gated unten die Nachbesetzungsrunde
        # (``_backfill_rejected_slots``), die sonst weitere LLM-Calls
        # auslösen würde, obwohl der Nutzer bereits abgebrochen hat.
        cancel_requested = False

        if is_gevent:
            logger.info("Gevent detected: using native cooperative Pool for parallel persona generation")
            from gevent.pool import Pool
            pool = Pool(parallel_count)

            def worker_wrapper(args):
                idx, entity = args
                try:
                    return generate_single_profile(idx, entity)
                except Exception as e:  # noqa: BLE001
                    logger.error(f"Cooperative greenlet failed unexpectedly for entity {entity.name}: {str(e)}")
                    entity_type = entity.get_entity_type() or "Entity"
                    fallback_profile = OasisAgentProfile(
                        user_id=idx,
                        user_name=self._generate_username(entity.name),
                        name=entity.name,
                        bio=f"{entity_type}: {entity.name}",
                        persona=entity.summary or "A participant in social discussions.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                        # Issue #1029: Notprofil nach einem Ausfall — noch
                        # dünner als das regelbasierte, also erst recht
                        # nicht als echte Stimme zu behandeln.
                        generation_source="rule_based",
                        generation_error=str(e)[:160],
                    )
                    return idx, fallback_profile, str(e)

            # Consume results inside try/finally so the pool is joined on success
            # and on exceptions — no orphaned greenlets outlive add_text_batches.
            try:
                for result_idx, profile, error in pool.imap_unordered(worker_wrapper, enumerate(entities)):
                    _process_result(result_idx, profile, error)
                    if self.run_id and is_cancel_requested(self.run_id):
                        # Gevent kennt keine Trennung "nur Wartende abbrechen"
                        # wie ThreadPoolExecutor.shutdown(cancel_futures=True)
                        # — pool.kill() beendet auch bereits laufende
                        # Greenlets. Gröberer Schnitt als im Thread-Pfad
                        # unten, aber der einzige verfügbare Weg, neue
                        # LLM-Calls sofort zu stoppen (best effort).
                        logger.info(
                            "Persona-Generierung kooperativ abgebrochen (gevent): "
                            "run_id=%s, %d/%d Personas fertig",
                            self.run_id, completed_count[0], total,
                        )
                        cancel_requested = True
                        pool.kill()
                        break
            finally:
                pool.join()
        else:
            # Use thread pool for parallel execution.
            # Consume as_completed futures *inside* the `with` block so the
            # executor is not shut down (shutdown(wait=True) blocks until all
            # tasks finish) before results are processed — otherwise real-time
            # progress and incremental file writes regress to 0% until the
            # slowest persona completes.
            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
                future_to_entity = {
                    executor.submit(generate_single_profile, idx, entity): (idx, entity)
                    for idx, entity in enumerate(entities)
                }

                for future in concurrent.futures.as_completed(future_to_entity):
                    idx, entity = future_to_entity[future]
                    entity_type = entity.get_entity_type() or "Entity"
                    try:
                        result_idx, profile, error = future.result()
                    except Exception as e:  # noqa: BLE001
                        logger.error(f"Thread execution failed unexpectedly for entity {entity.name}: {str(e)}")
                        profile = OasisAgentProfile(
                            user_id=idx,
                            user_name=self._generate_username(entity.name),
                            name=entity.name,
                            bio=f"{entity_type}: {entity.name}",
                            persona=entity.summary or "A participant in social discussions.",
                            source_entity_uuid=entity.uuid,
                            source_entity_type=entity_type,
                        )
                        result_idx, error = idx, str(e)
                    _process_result(result_idx, profile, error)
                    if self.run_id and is_cancel_requested(self.run_id):
                        # Bereits laufende Persona-Generierungen dürfen
                        # auslaufen — das ist akzeptiert.
                        # shutdown(cancel_futures=True) verwirft nur Futures,
                        # die noch nicht gestartet sind; bereits angelaufene
                        # Worker schreiben ihr Ergebnis noch fertig (der
                        # `with`-Block wartet beim Verlassen darauf, s.
                        # ThreadPoolExecutor.__exit__ → shutdown(wait=True)).
                        logger.info(
                            "Persona-Generierung kooperativ abgebrochen (Thread-Pfad): "
                            "run_id=%s, %d/%d Personas fertig",
                            self.run_id, completed_count[0], total,
                        )
                        cancel_requested = True
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

        # Issue #1247: Abgelehnte Slots aus dem Reservepool nachbesetzen. Ohne
        # diesen Schritt unterschreitet jede Ablehnung den konfigurierten
        # max_agents-Wert — bei einem Cap von 30 (nach eigener Empfehlung der
        # Floor ohne Puffer) und einer beobachteten Ablehnungsquote von bis zu
        # 32 % waere das der Unterschied zwischen 30 und 20 Stimmen.
        # Bei einem Nutzerabbruch (cancel_requested) bleibt die Nachbesetzung
        # aus — sie würde weitere LLM-Calls auslösen, obwohl bereits
        # abgebrochen wurde.
        if rejected and not cancel_requested:
            self._backfill_rejected_slots(
                profiles=profiles,
                entities=entities,
                reserve_entities=list(reserve_entities or []),
                use_llm=use_llm,
                rejected=rejected,
            )

        # Dedup display_name und user_name: LLM neigt dazu, dieselbe reale Person
        # mehrfach zu klonen wenn sie im Doc prominent ist. Bei Dubletten neuen
        # DACH-Namen aus dem Pool ziehen, Handle entsprechend neu bauen.
        seen_names: set = set()
        seen_last_names: set = set()
        seen_handles: set = set()
        for p in profiles:
            if p is None:
                continue
            # Issue #1246 (CodeRabbit PR #1257): Kollektive nehmen an der
            # Personennamen-Dedup nicht teil. Zwei Organisationen mit gleichem
            # Schlusstoken — "… GmbH", "… e.V." — galten hier als doppelter
            # Nachname, und die zweite bekam einen zufaelligen DACH-Personen-
            # namen zugewiesen, waehrend ihr Personatext weiter die
            # Organisation beschreibt. Das ist exakt der Identitaetsbruch,
            # den dieser Slice schliesst.
            if p.persona_kind == "collective":
                continue
            norm_name = (p.name or "").strip().lower()
            last_name = self._last_name(p.name or "")
            if norm_name and (
                norm_name in seen_names
                or (last_name is not None and last_name in seen_last_names)
            ):
                new_name = self._pick_dach_name(p.gender)
                attempts = 0
                while (
                    new_name.lower() in seen_names
                    or (self._last_name(new_name) or "") in seen_last_names
                ) and attempts < 30:
                    new_name = self._pick_dach_name(p.gender)
                    attempts += 1
                p.name = new_name
                p.user_name = self._generate_username(new_name)
            seen_names.add((p.name or "").strip().lower())
            last_name = self._last_name(p.name or "")
            if last_name:
                seen_last_names.add(last_name)

            norm_handle = (p.user_name or "").strip().lower()
            if norm_handle and norm_handle in seen_handles:
                # Handle steht schon; hänge Suffix-Rotation an.
                base = norm_handle.rsplit("_", 1)[0] if "_" in norm_handle else norm_handle
                p.user_name = self._generate_username(base)
            seen_handles.add((p.user_name or "").strip().lower())

        logger.info(
            "Persona generation complete — %d agents generated.",
            len([p for p in profiles if p]),
        )

        if degradations is not None:
            self._report_persona_degradation(profiles, degradations)

        # Re-save after dedup to keep realtime file in sync with final state.
        save_profiles_realtime()

        # Issue #1247 (CodeRabbit PR #1258): Leere Slots verdichten. Eine
        # Ablehnung ohne verfuegbaren Nachruecker liess bisher ``None`` in der
        # Liste stehen; ``save_profiles`` dereferenziert aber jeden Eintrag und
        # waere daran gescheitert — der bewusst unterstuetzte Fall "Platz bleibt
        # leer" haette die Vorbereitung abgebrochen statt einen kleineren, aber
        # gueltigen Personensatz zu liefern.
        return [profile for profile in profiles if profile is not None]
    
    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        """Log generated persona details at INFO level (visible in default log config)."""
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else 'None'
        logger.info(
            "[Generated] %s (%s) → %s | age=%s gender=%s mbti=%s profession=%s topics=%s",
            entity_name,
            entity_type,
            profile.user_name,
            profile.age,
            profile.gender,
            profile.mbti,
            profile.profession,
            topics_str,
        )
    
    def save_profiles(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """
        Save profiles to file (choose correct format based on platform)

        OASIS platform format requirements:
        - Twitter: CSV format
        - Reddit: JSON format

        Args:
            profiles: Profile list
            file_path: File path
            platform: Platform type ("reddit" or "twitter")
        """
        if platform == "twitter":
            self._save_twitter_csv(profiles, file_path)
        else:
            self._save_reddit_json(profiles, file_path)
    
    def _save_twitter_csv(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Save Twitter Profile as CSV format (compliant with OASIS official requirements)

        OASIS Twitter required CSV fields:
        - user_id: User ID (starting from 0 based on CSV order)
        - name: User real name
        - username: Username in the system
        - user_char: Detailed persona description (injected into LLM system prompt, guides agent behavior)
        - description: Short public bio (displayed on user profile page)

        user_char vs description difference:
        - user_char: Internal use, LLM system prompt, determines how agent thinks and acts
        - description: External display, visible to other users
        """
        import csv

        # Ensure file extension is .csv
        if not file_path.endswith('.csv'):
            file_path = file_path.replace('.json', '.csv')

        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Write OASIS required header
            headers = ['user_id', 'name', 'username', 'user_char', 'description']
            writer.writerow(headers)

            # Write data rows
            for idx, profile in enumerate(profiles):
                # user_char: Complete persona (bio + persona) for LLM system prompt
                user_char = profile.bio
                if profile.persona and profile.persona != profile.bio:
                    user_char = f"{profile.bio} {profile.persona}"
                # Handle newlines (replace with space in CSV)
                user_char = user_char.replace('\n', ' ').replace('\r', ' ')

                # description: Short bio for external display
                description = profile.bio.replace('\n', ' ').replace('\r', ' ')

                row = [
                    idx,                    # user_id: Sequential ID starting from 0
                    profile.name,           # name: Real name
                    profile.user_name,      # username: Username
                    user_char,              # user_char: Complete persona (internal LLM use)
                    description             # description: Short bio (external display)
                ]
                writer.writerow(row)

        logger.info(f"Saved {len(profiles)} Twitter profiles to {file_path} (OASIS CSV format)")
    
    def _normalize_gender(self, gender: Optional[str]) -> str:
        """
        Normalize gender field to OASIS required English format

        OASIS requires: male, female, other
        """
        if not gender:
            return "other"

        gender_lower = gender.lower().strip()

        # Gender mapping
        gender_map = {
            "male": "male",
            "female": "female",
            "other": "other",
        }

        return gender_map.get(gender_lower, "other")
    
    def _save_reddit_json(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Save Reddit Profile as JSON format

        Use format consistent with to_reddit_format() to ensure OASIS can read correctly.
        Must include user_id field, which is the key for OASIS agent_graph.get_agent() matching!

        Required fields:
        - user_id: User ID (integer, used to match poster_agent_id in initial_posts)
        - username: Username
        - name: Display name
        - bio: Bio
        - persona: Detailed persona
        - age: Age (integer)
        - gender: "male", "female", or "other"
        - mbti: MBTI type
        - country: Country
        """
        data = []
        for idx, profile in enumerate(profiles):
            # Issue #1186: ``to_reddit_format()`` ist die Quelle, nicht eine
            # handgepflegte Feldliste.
            #
            # Diese Methode baute das Dict frueher neu — und ueberschrieb damit
            # die Datei, die der Realtime-Pfad zuvor korrekt ueber
            # ``to_reddit_format()`` geschrieben hatte. Jedes Feld, das hier
            # nicht einzeln aufgefuehrt war, ging beim finalen Speichern
            # verloren: ``voice_register`` und ``segment`` fehlten in allen
            # 262 persistierten Profilen ueber sechs Laeufe, unabhaengig
            # davon, ob sie vom LLM oder regelbasiert erzeugt wurden.
            #
            # #1029 hat dasselbe Muster schon einmal getroffen und damals nur
            # ``generation_source`` nachgetragen. Eine zweite Nachtragung
            # waere die dritte Gelegenheit fuer denselben Fehler — deshalb
            # jetzt die Umkehrung: das vollstaendige Format als Basis, und
            # obendrauf nur die Defaults, die OASIS verlangt und die im
            # Format bewusst fehlen (dort ist ein nicht gesetztes Feld
            # abwesend, hier braucht OASIS einen Wert).
            item = profile.to_reddit_format()
            item.update({
                "user_id": profile.user_id if profile.user_id is not None else idx,
                "bio": profile.bio[:150] if profile.bio else f"{profile.name}",
                "persona": profile.persona or f"{profile.name} is a participant in social discussions.",
                "karma": profile.karma if profile.karma else 1000,
                "country": profile.country if profile.country else "US",
            })
            # Issue #1246 (CodeRabbit PR #1257): Die OASIS-Defaults gelten nur
            # fuer Individuen. Vorher fuellte dieser Block Alter, Geschlecht und
            # MBTI unbedingt auf — und schrieb damit genau die erfundene
            # Demografie zurueck in reddit_profiles.json, die der Kollektivzweig
            # entfernt. Die Realtime-Datei war korrekt, der finale Save
            # ueberschrieb sie. Persona-Galerie und Simulation lesen diese Datei.
            if profile.persona_kind != "collective":
                item.update({
                    "age": profile.age if profile.age else 30,
                    "gender": self._normalize_gender(profile.gender),
                    "mbti": profile.mbti if profile.mbti else "ISTJ",
                })

            data.append(item)

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(profiles)} Reddit profiles to {file_path} (JSON format, includes user_id field)")
    
    # Keep old method name as alias for backward compatibility
    def save_profiles_to_json(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """[Deprecated] Please use save_profiles() method"""
        logger.warning("save_profiles_to_json is deprecated, please use save_profiles method")
        self.save_profiles(profiles, file_path, platform)
