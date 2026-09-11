"""
OASIS Agent Profile Generator
Convert entities from the knowledge graph to OASIS simulation platform's required Agent Profile format

Optimization improvements:
1. Call knowledge graph retrieval function to enrich node information
2. Optimize prompts to generate very detailed personas
3. Distinguish between individual entities and abstract group entities
"""

import re
from typing import TYPE_CHECKING, Dict, Any, List, Optional

from openai import OpenAI

from ..config import Config
from ..contracts import PersonaQuotaPlan
from ..contracts.provider_types import PROVIDER_CODEX_CLI
from .settings_layer import get_default_service as _get_settings
from ..utils.llm_latency import measure_llm_latency
from ..utils.logger import get_logger
from .entity_reader import EntityNode
from ..storage import GraphStorage
from .persona_quota_defaults import (
    default_dach_industry_quota,
)
from ..llm.json_mode import _try_repair_truncated_json as _try_repair_truncated_json
from .oasis_profile_models import (
    CollectivePersonaSchema as CollectivePersonaSchema,
    OasisAgentProfile as OasisAgentProfile,
    PersonaDemographicSlot as PersonaDemographicSlot,
    PersonaIneligible as PersonaIneligible,
    PersonaProfileSchema as PersonaProfileSchema,
)

if TYPE_CHECKING:
    from .degradation_collector import DegradationCollector

logger = get_logger('agora.oasis_profile')

# Erlaubte Voice-Register-Werte (gespiegelt aus VoiceRegister Literal in persona_contract.py)
VOICE_REGISTERS = ("formal-de", "neutral-de", "technical-de", "skeptisch-de")







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







# Intentional late imports: helper modules depend on legacy module globals.
from . import oasis_profile_core as _oasis_profile_core  # noqa: E402
from . import oasis_profile_demographics as _oasis_profile_demographics  # noqa: E402
from . import oasis_profile_context as _oasis_profile_context  # noqa: E402
from . import oasis_profile_llm as _oasis_profile_llm  # noqa: E402
from . import oasis_profile_prompts as _oasis_profile_prompts  # noqa: E402
from . import oasis_profile_rule_based as _oasis_profile_rule_based  # noqa: E402
from . import oasis_profile_batch_results as _oasis_profile_batch_results  # noqa: E402
from . import oasis_profile_batch as _oasis_profile_batch  # noqa: E402
from . import oasis_profile_persistence as _oasis_profile_persistence  # noqa: E402

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
    def _pick_dach_name(gender: Optional[str]=None) -> str:
        return _oasis_profile_demographics._pick_dach_name(gender)

    @staticmethod
    def _last_name(name: str) -> Optional[str]:
        return _oasis_profile_demographics._last_name(name)

    @staticmethod
    def _pick_individual_gender() -> str:
        return _oasis_profile_demographics._pick_individual_gender()

    @staticmethod
    def _largest_remainder_counts(weighted_values: tuple[tuple[object, float], ...], total: int) -> list[int]:
        return _oasis_profile_demographics._largest_remainder_counts(weighted_values, total)

    @classmethod
    def _build_weighted_slots(cls, weighted_values: tuple[tuple[str, float], ...], total: int) -> list[str]:
        return _oasis_profile_demographics._build_weighted_slots(cls, weighted_values, total)

    @classmethod
    def _build_age_slots(cls, weighted_bands: tuple[tuple[tuple[int, int], float], ...], total: int) -> list[int]:
        return _oasis_profile_demographics._build_age_slots(cls, weighted_bands, total)

    def _build_demographic_slots(self, entities: List[EntityNode]) -> list[PersonaDemographicSlot]:
        return _oasis_profile_demographics._build_demographic_slots(self, entities)

    def _build_demographic_slot_prompt_block(self, demographic_slot: PersonaDemographicSlot) -> str:
        return _oasis_profile_demographics._build_demographic_slot_prompt_block(self, demographic_slot)

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
        provider_type: Optional[str] = None,
        storage: Optional[GraphStorage] = None,
        graph_id: Optional[str] = None,
        language: Optional[str] = None,
        industry_quota_plan: Optional[PersonaQuotaPlan] = None,
        run_id: Optional[str] = None,
    ):
        # Budget-Enforcement (#984): die run_id des Prepare-Runs bindet jeden
        # LLM-Call dieser Generierung an den Budget-Enforcer des Runs.
        self.run_id = run_id
        self.provider_type = provider_type
        if provider_type == PROVIDER_CODEX_CLI:
            # Issue #1418: codex_cli (transport="cli", #1405) hat weder
            # base_url noch api_key — der .env-Fallback unten wuerde das
            # Modell aus der Route an einen fremden HTTP-Provider schicken
            # (beobachtet: gpt-5.6-luna an https://api.minimax.io/v1 → 400).
            self.base_url = None
            self.api_key = api_key or "codex-cli-local-session"
        else:
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
    
    def generate_profile_from_entity(self, entity: EntityNode, user_id: int, use_llm: bool=True, demographic_slot: Optional[PersonaDemographicSlot]=None) -> OasisAgentProfile:
        return _oasis_profile_core.generate_profile_from_entity(self, entity, user_id, use_llm, demographic_slot)
    
    def _generate_username(self, name: str) -> str:
        return _oasis_profile_core._generate_username(self, name)
    
    def _search_graph_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        return _oasis_profile_context._search_graph_for_entity(self, entity)
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        return _oasis_profile_context._build_entity_context(self, entity)
    
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
        return _oasis_profile_context._align_persona_identity(cls, persona, display_name)

    @staticmethod
    def _profession_after_coherence_check(*, entity_type: str, entity_name: str, persona_kind: str, profession: Optional[str], persona_text: str, entity_summary: Optional[str], entity_context: Optional[str]) -> Optional[str]:
        return _oasis_profile_context._profession_after_coherence_check(entity_type=entity_type, entity_name=entity_name, persona_kind=persona_kind, profession=profession, persona_text=persona_text, entity_summary=entity_summary, entity_context=entity_context)

    def _is_individual_entity(self, entity_type: str) -> bool:
        return _oasis_profile_context._is_individual_entity(self, entity_type)

    def _is_group_entity(self, entity_type: str) -> bool:
        return _oasis_profile_context._is_group_entity(self, entity_type)

    def _build_eligibility_prompt_block(self, entity_name: str, entity_type: str) -> str:
        return _oasis_profile_context._build_eligibility_prompt_block(self, entity_name, entity_type)


    @measure_llm_latency(operation='persona_generation', extract_model=lambda self, *a, **kw: getattr(self, 'model_name', None), extract_prompt_chars=None)
    def _generate_profile_with_llm(self, entity_name: str, entity_type: str, entity_summary: str, entity_attributes: Dict[str, Any], context: str, demographic_slot: Optional[PersonaDemographicSlot]=None) -> Dict[str, Any]:
        return _oasis_profile_llm._generate_profile_with_llm(self, entity_name, entity_type, entity_summary, entity_attributes, context, demographic_slot)

    def _validate_profile_metadata(self, result: Dict[str, Any], *, is_collective: bool=False) -> List[str]:
        return _oasis_profile_llm._validate_profile_metadata(self, result, is_collective=is_collective)

    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str='') -> Dict[str, Any]:
        return _oasis_profile_llm._try_fix_json(self, content, entity_name, entity_type, entity_summary)
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        return _oasis_profile_prompts._get_system_prompt(self, is_individual)

    def _build_individual_persona_prompt(self, entity_name: str, entity_type: str, entity_summary: str, entity_attributes: Dict[str, Any], context: str, detail_level: Optional[dict]=None, demographic_slot: Optional[PersonaDemographicSlot]=None) -> str:
        return _oasis_profile_prompts._build_individual_persona_prompt(self, entity_name, entity_type, entity_summary, entity_attributes, context, detail_level, demographic_slot)

    def _build_group_persona_prompt(self, entity_name: str, entity_type: str, entity_summary: str, entity_attributes: Dict[str, Any], context: str, detail_level: Optional[dict]=None, demographic_slot: Optional[PersonaDemographicSlot]=None) -> str:
        return _oasis_profile_prompts._build_group_persona_prompt(self, entity_name, entity_type, entity_summary, entity_attributes, context, detail_level, demographic_slot)
    
    @staticmethod
    def _rule_based_voice_register(entity_type: str, profession: str='') -> str:
        return _oasis_profile_rule_based._rule_based_voice_register(entity_type, profession)

    def _report_persona_degradation(self, profiles: List[Optional[OasisAgentProfile]], degradations: 'DegradationCollector') -> None:
        return _oasis_profile_rule_based._report_persona_degradation(self, profiles, degradations)

    def _generate_profile_rule_based(self, entity_name: str, entity_type: str, entity_summary: str, entity_attributes: Dict[str, Any], generation_error: Optional[str]=None, demographic_slot: Optional[PersonaDemographicSlot]=None) -> Dict[str, Any]:
        return _oasis_profile_rule_based._generate_profile_rule_based(self, entity_name, entity_type, entity_summary, entity_attributes, generation_error, demographic_slot)

    def _build_collective_payload(self, entity_name: str, entity_type: str, entity_summary: str) -> Dict[str, Any]:
        return _oasis_profile_rule_based._build_collective_payload(self, entity_name, entity_type, entity_summary)

    def _build_rule_based_payload(self, entity_name: str, entity_type: str, entity_summary: str, entity_attributes: Dict[str, Any], demographic_slot: Optional[PersonaDemographicSlot]=None) -> Dict[str, Any]:
        return _oasis_profile_rule_based._build_rule_based_payload(self, entity_name, entity_type, entity_summary, entity_attributes, demographic_slot)

    def _build_generic_person_payload(self, *, entity_name: str, entity_type: str, entity_summary: str, assigned_gender: str, assigned_age: Optional[int], assigned_mbti: Optional[str]) -> Dict[str, Any]:
        return _oasis_profile_rule_based._build_generic_person_payload(self, entity_name=entity_name, entity_type=entity_type, entity_summary=entity_summary, assigned_gender=assigned_gender, assigned_age=assigned_age, assigned_mbti=assigned_mbti)
    
    def set_graph_id(self, graph_id: str):
        """Set knowledge graph ID for knowledge graph search"""
        self.graph_id = graph_id
    
    def _backfill_rejected_slots(self, *, profiles: List[Optional[OasisAgentProfile]], entities: List[EntityNode], reserve_entities: List[EntityNode], use_llm: bool, rejected: List['PersonaIneligible']) -> None:
        return _oasis_profile_batch_results._backfill_rejected_slots(self, profiles=profiles, entities=entities, reserve_entities=reserve_entities, use_llm=use_llm, rejected=rejected)

    def _consume_gevent_results(self, pool, worker_wrapper, entities, process_result, completed_count, total) -> bool:
        return _oasis_profile_batch_results._consume_gevent_results(self, pool, worker_wrapper, entities, process_result, completed_count, total)

    def _consume_thread_results(self, generate_single_profile, entities, parallel_count, process_result, completed_count, total) -> bool:
        return _oasis_profile_batch_results._consume_thread_results(self, generate_single_profile, entities, parallel_count, process_result, completed_count, total)

    def _cancel_checkpoint(self, completed: int, total: int, path: str) -> bool:
        return _oasis_profile_batch_results._cancel_checkpoint(self, completed, total, path)

    def generate_profiles_from_entities(self, entities: List[EntityNode], use_llm: bool=True, progress_callback: Optional[callable]=None, graph_id: Optional[str]=None, parallel_count: Optional[int]=None, realtime_output_path: Optional[str]=None, output_platform: str='reddit', degradations: Optional['DegradationCollector']=None, reserve_entities: Optional[List[EntityNode]]=None) -> List[OasisAgentProfile]:
        return _oasis_profile_batch.generate_profiles_from_entities(self, entities, use_llm, progress_callback, graph_id, parallel_count, realtime_output_path, output_platform, degradations, reserve_entities)
    
    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        return _oasis_profile_persistence._print_generated_profile(self, entity_name, entity_type, profile)
    
    def save_profiles(self, profiles: List[OasisAgentProfile], file_path: str, platform: str='reddit'):
        return _oasis_profile_persistence.save_profiles(self, profiles, file_path, platform)
    
    def _save_twitter_csv(self, profiles: List[OasisAgentProfile], file_path: str):
        return _oasis_profile_persistence._save_twitter_csv(self, profiles, file_path)
    
    def _normalize_gender(self, gender: Optional[str]) -> str:
        return _oasis_profile_persistence._normalize_gender(self, gender)
    
    def _save_reddit_json(self, profiles: List[OasisAgentProfile], file_path: str):
        return _oasis_profile_persistence._save_reddit_json(self, profiles, file_path)
    
    # Keep old method name as alias for backward compatibility
    def save_profiles_to_json(self, profiles: List[OasisAgentProfile], file_path: str, platform: str='reddit'):
        return _oasis_profile_persistence.save_profiles_to_json(self, profiles, file_path, platform)
