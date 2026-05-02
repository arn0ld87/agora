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
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from .entity_reader import EntityNode
from ..storage import GraphStorage

logger = get_logger('agora.oasis_profile')

# Erlaubte Voice-Register-Werte (gespiegelt aus VoiceRegister Literal in persona_contract.py)
VOICE_REGISTERS = ("formal-de", "neutral-de", "technical-de", "skeptisch-de")


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

    # DACH-Voice-Register (Layer 2)
    voice_register: Optional[str] = None

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
        if self.segment:
            profile["segment"] = self.segment
        if self.voice_register:
            profile["voice_register"] = self.voice_register

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
        if self.segment:
            profile["segment"] = self.segment
        if self.voice_register:
            profile["voice_register"] = self.voice_register

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
            "segment": self.segment,
            "voice_register": self.voice_register,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """
    OASIS Profile Generator

    Convert entities from the knowledge graph to Agent Profile required by OASIS simulation

    Optimization features:
    1. Call knowledge graph retrieval function to get richer context
    2. Generate very detailed personas (including basic information, career experience, personality traits, social media behavior, etc.)
    3. Distinguish between individual entities and abstract group entities
    """

    # MBTI types list
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]
    REQUIRED_PROFILE_FIELDS = ("age", "gender", "mbti", "country")
    VALID_PROFILE_GENDERS = {"male", "female", "nonbinary", "other"}

    # Common countries list
    COUNTRIES = [
        "US", "UK", "Japan", "Germany", "France",
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]

    # DACH name pool used when the LLM fallback kicks in for individuals.
    DACH_FIRST_NAMES = [
        "Lena", "Marie", "Sophie", "Hannah", "Emma", "Laura", "Julia", "Katharina",
        "Anna", "Sarah", "Lisa", "Nora", "Clara", "Mia", "Leonie",
        "Jonas", "Leon", "Felix", "Maximilian", "Tim", "Lukas", "Paul", "Julian",
        "Niklas", "Jan", "Philipp", "David", "Moritz", "Finn", "Tobias",
        "Alex", "Kim", "Robin", "Sam",  # geschlechtsneutral / nonbinary-freundlich
    ]
    DACH_LAST_NAMES = [
        "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
        "Becker", "Schulz", "Hoffmann", "Schäfer", "Koch", "Bauer", "Richter",
        "Klein", "Wolf", "Neumann", "Schröder", "Zimmermann", "Braun", "Krüger",
        "Hofmann", "Hartmann", "Lange", "Werner", "Krause", "Lehmann", "Schmitz",
        "Maier", "König"
    ]

    @classmethod
    def _pick_dach_name(cls) -> str:
        return f"{random.choice(cls.DACH_FIRST_NAMES)} {random.choice(cls.DACH_LAST_NAMES)}"

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
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
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
    
    def generate_profile_from_entity(
        self,
        entity: EntityNode,
        user_id: int,
        use_llm: bool = True
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
                context=context
            )
        else:
            # Use rules to generate basic persona
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes
            )
        
        # LLM/Rule-based darf display_name (echter Name) + handle (kurzes Social-Handle)
        # überschreiben. So wird aus Entity "GraphRAG" z.B. Person "Lena Hoffmann" mit
        # Handle "lena_hoffmann" oder Organisation "Docker Inc." mit "docker".
        display_name = (profile_data.get("display_name") or "").strip()
        if display_name:
            name = display_name
        handle = (profile_data.get("handle") or "").strip()
        if handle:
            user_name = self._generate_username(handle)

        # Segment = entity_type string for PersonaQuotaPlan validation.
        # entity_type is already resolved above (get_entity_type() or "Entity").
        segment = entity_type if entity_type != "Entity" else None

        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"A {entity_type} named {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
            segment=segment,
            voice_register=profile_data.get("voice_register"),
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

        except Exception as e:
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
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """Determine if entity is an individual type"""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES

    def _is_group_entity(self, entity_type: str) -> bool:
        """Determine if entity is a group/institutional type"""
        return entity_type.lower() in self.GROUP_ENTITY_TYPES
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """
        Use LLM to generate very detailed persona

        Based on entity type:
        - Individual entities: generate specific character profiles
        - Group/institutional entities: generate representative account profiles
        """

        is_individual = self._is_individual_entity(entity_type)

        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )

        # Try multiple times until successful or max retry attempts reached
        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # Lower temperature with each retry
                    # Don't set max_tokens, let LLM generate freely
                )

                content = response.choices[0].message.content

                # Check if output was truncated (finish_reason is not 'stop')
                finish_reason = response.choices[0].finish_reason
                if finish_reason == 'length':
                    logger.warning(f"LLM output truncated (attempt {attempt+1}), attempting to fix...")
                    content = self._fix_truncated_json(content)

                # Try to parse JSON
                try:
                    result = json.loads(content)

                    # Validate required fields
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name} is a {entity_type}."

                    # voice_register: Fallback vor allgemeiner Validation (kein Retry nötig)
                    vr_value = result.get("voice_register")
                    if vr_value not in VOICE_REGISTERS:
                        logger.warning(
                            "voice_register fehlt oder ungültig: %r → fallback neutral-de", vr_value
                        )
                        result["voice_register"] = "neutral-de"

                    missing_fields = self._validate_profile_metadata(result)
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

                except json.JSONDecodeError as je:
                    logger.warning(f"JSON parsing failed (attempt {attempt+1}): {str(je)[:80]}")

                    # Try to fix JSON
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        if "bio" not in result or not result["bio"]:
                            result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                        if "persona" not in result or not result["persona"]:
                            result["persona"] = entity_summary or f"{entity_name} is a {entity_type}."
                        missing_fields = self._validate_profile_metadata(result)
                        if missing_fields:
                            last_error = ValueError(
                                f"Missing required persona metadata after JSON repair: {', '.join(missing_fields)}"
                            )
                            logger.warning(
                                f"Fixed JSON still missing required metadata (attempt {attempt+1}): "
                                f"{', '.join(missing_fields)}"
                            )
                            continue
                        return result

                    last_error = je

            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # Exponential backoff

        logger.warning(f"LLM persona generation failed ({max_attempts} attempts): {last_error}, using rule-based generation")
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )

    def _validate_profile_metadata(self, result: Dict[str, Any]) -> List[str]:
        """Validate and normalize structured fields that OASIS actually consumes."""
        missing_fields = []

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
    
    def _fix_truncated_json(self, content: str) -> str:
        """Fix truncated JSON (output truncated by max_tokens limit)"""

        # If JSON is truncated, try to close it
        content = content.strip()

        # Count unclosed parentheses
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')

        # Check for unclosed strings
        # Simple check: if last character is not comma or closing bracket, string might be truncated
        if content and content[-1] not in '",}]':
            # Try to close the string
            content += '"'

        # Close parentheses
        content += ']' * open_brackets
        content += '}' * open_braces

        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """Try to fix corrupted JSON"""
        import re

        # 1. First try to fix truncated case
        content = self._fix_truncated_json(content)

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
        context: str
    ) -> str:
        """Build detailed persona prompt for individual entities — language-aware."""

        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "Keine"
        context_str = context[:3000] if context else "Keine zusätzlichen Informationen"

        if self.language == "de":
            return f"""Erzeuge eine detaillierte Social-Media-Persona für die folgende Entität. Bleibe nah an der bekannten Realität.

Name der Entität: {entity_name}
Typ: {entity_type}
Zusammenfassung: {entity_summary}
Attribute: {attrs_str}

Kontext:
{context_str}

Antworte als JSON mit folgenden Feldern:

1. display_name: Echter Vor- und Nachname einer Person im DACH-Raum (z. B. "Lena Hoffmann", "Marcel Schmitz"). WICHTIG: Nur dann den tatsächlichen Namen einer realen Person nehmen, wenn "{entity_name}" selbst bereits ein Personenname ist UND diese Person in der Realität so heißt. Bei Rollen ("IT-Umschüler"), Themen ("GraphRAG"), Produkten ("Agora") oder Berufsbezeichnungen IMMER einen anderen, frei gewählten DACH-Namen nehmen — nicht den Namen einer im Kontext erwähnten Person übernehmen. Jede Persona soll einen EIGENEN Namen haben.
2. handle: Kurzes Social-Media-Handle in Kleinbuchstaben ohne Leerzeichen (z. B. "lena_hoffmann" oder "marcelschmitz"). Keine Zahlen anhängen — das passiert später.
3. bio: Social-Media-Bio, max. 200 Zeichen, auf Deutsch.
4. persona: Ausführliche Personenbeschreibung (rund 1500–2000 Wörter, durchgehend Fließtext, auf Deutsch). Enthalten muss sein:
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
8. country: ISO-Land in Englisch (z. B. "DE", "US")
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

        return f"""Generate a detailed social media user persona for the entity, maximizing restoration of existing reality.

Entity Name: {entity_name}
Entity Type: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

Please generate JSON containing the following fields:

1. display_name: Realistic first + last name of a person (culturally appropriate). IMPORTANT: Only use a real person's actual name if "{entity_name}" itself IS a personal name AND matches reality. For roles, topics, products, or job titles ALWAYS pick a different, freshly chosen name — do NOT reuse names of people mentioned in the context. Every persona must have its own unique name.
2. handle: Short lowercase social handle without spaces (e.g. "lena_hoffmann"). Do not append digits.
3. bio: Social media bio, 200 characters
4. persona: Detailed persona description (2000 words of pure text), must include:
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
8. country: Country (use English, e.g., "US")
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
        context: str
    ) -> str:
        """Build detailed persona prompt for group/institutional entities — language-aware."""

        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "Keine"
        context_str = context[:3000] if context else "Keine zusätzlichen Informationen"

        if self.language == "de":
            return f"""Erzeuge einen realistischen **Menschen**, der als Repräsentantin/Repräsentant oder Mitarbeiter:in für die folgende Organisation / Gruppe auf Social Media spricht — keinen Institutions-Account. Bleibe nah an der bekannten Realität.

Organisation/Gruppe: {entity_name}
Typ: {entity_type}
Zusammenfassung: {entity_summary}
Attribute: {attrs_str}

Kontext:
{context_str}

Antworte als JSON mit folgenden Feldern:

1. display_name: Echter Vor- und Nachname einer Person aus dem DACH-Raum (z. B. "Lena Hoffmann", "Marcel Schmitz"). KEIN Organisationsname.
2. handle: Kurzes Social-Media-Handle der Person in Kleinbuchstaben (z. B. "lena_hoffmann"). Keine Zahlen.
3. bio: Social-Bio der Person, max. 200 Zeichen, Deutsch. Darf die Rolle in der Organisation erwähnen (z. B. "Senior Tech-Recruiter @TalentCore | Karriereberatung für Quereinsteiger").
4. persona: Ausführliche Personen-Beschreibung (rund 1500–2000 Wörter, Fließtext, Deutsch). Enthalten:
   - Eckdaten (Alter, Bildungsweg, Wohnort)
   - Rolle in/Beziehung zur Organisation "{entity_name}" (Position, Dauer, Aufgaben)
   - Persönlicher Hintergrund (wie kam sie/er dahin, prägende Erfahrungen)
   - Persönlichkeit (MBTI, Kernzüge, emotionaler Ausdruck)
   - Social-Media-Verhalten (Frequenz, Themen, Stil — offizielle Linie vs. persönliche Meinung)
   - Haltungen (wo vertritt sie/er die Organisation, wo eigene Meinung)
   - Eigenheiten (Sprachmarotten, Hobbys)
   - Erinnerungen (Bezug zu Ereignissen im Kontext der Organisation)
5. age: Ganzzahl 25–65 (arbeitsfähiges Alter einer:s Repräsentant:in). Variieren, nicht auf 30/40 festnageln.
6. gender: Genau einer von "male", "female", "nonbinary". KEIN "other".
7. mbti: MBTI-Typ (z. B. INTJ, ENFP)
8. country: ISO-Land in Englisch (z. B. "DE")
9. profession: Konkrete Rolle bei/Beziehung zu "{entity_name}" (z. B. "Senior Tech-Recruiter bei TalentCore GmbH", "Developer Advocate bei Docker Inc.", "Redakteur bei alexle135.de").
10. interested_topics: Array deutscher Themen-Strings
11. voice_register: Genau einer von "formal-de" | "neutral-de" | "technical-de" | "skeptisch-de".
    Passend zu Rolle und Kontext der Persona bei "{entity_name}":
    - "formal-de": gehoben, Sie-Form, Behörden-/Konzern-Ton, keine Anglizismen.
    - "neutral-de": alltagssprachlich, Du-Form möglich, keine Werbesprache.
    - "technical-de": präzise, Fachvokabular, knapp, kein Marketing.
    - "skeptisch-de": kritisch-distanziert, hinterfragend, Anführungszeichen für Buzzwords.

Wichtig:
- Antworte ausschließlich mit JSON.
- Texte auf Deutsch.
- Keine unescapten Zeilenumbrüche.
- display_name MUSS ein echter Personenname sein, NICHT der Name der Organisation.
- gender MUSS "male"/"female"/"nonbinary" sein, age MUSS im Bereich 25–65 liegen.
- voice_register MUSS eines der vier exakten Werte sein.
"""

        return f"""Generate a realistic **human person** who speaks FOR the following organization/group on social media — not an institutional account. The person can be an employee, advocate, official representative, or community member.

Organization/Group: {entity_name}
Entity Type: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

Please generate JSON containing the following fields:

1. display_name: Realistic first + last name of a person (culturally appropriate — e.g. "Lena Hoffmann" for DE-context, "Emily Carter" for US-context). NOT the organization's name.
2. handle: Short lowercase social handle of the person (e.g. "lena_hoffmann"). Do not append digits.
3. bio: Personal social bio, 200 characters. May reference the role (e.g. "Senior Recruiter @TalentCore | hiring engineers").
4. persona: Detailed person description (2000 words of pure text), must include:
   - Basic information (age, education, location)
   - Role in / relationship to "{entity_name}" (position, tenure, responsibilities)
   - Personal background (how they got there, formative experiences)
   - Personality traits (MBTI, core personality)
   - Social media behavior (frequency, topics, style — official line vs. personal view)
   - Positions (where they represent the org, where they share personal opinion)
   - Unique features (catchphrases, hobbies)
   - Memories (connection to events in the org's context)
5. age: Integer 25–65 (working-age representative). Vary — do not pin to 30 or 40.
6. gender: Exactly one of "male", "female", "nonbinary". NOT "other".
7. mbti: MBTI type (e.g., INTJ, ENFP)
8. country: Country (use English, e.g., "DE")
9. profession: Concrete role at/relation to "{entity_name}" (e.g. "Senior Tech Recruiter at TalentCore GmbH", "Developer Advocate at Docker Inc.").
10. interested_topics: Array of topics
11. voice_register: Exactly one of "formal-de" | "neutral-de" | "technical-de" | "skeptisch-de".
    Choose based on role at "{entity_name}":
    - "formal-de": elevated style, formal address, bureaucratic tone, no anglicisms.
    - "neutral-de": everyday language, casual address, no marketing speak.
    - "technical-de": precise, specialist vocabulary, concise, no marketing.
    - "skeptisch-de": critical, questioning, uses quotation marks for buzzwords.

Important:
- All field values must be strings or numbers, no null values allowed
- display_name MUST be a real personal name, NEVER the organization's name.
- gender MUST be "male"/"female"/"nonbinary"; age MUST be in 25–65.
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

    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate basic persona using rules"""

        # Generate different personas based on entity type
        entity_type_lower = entity_type.lower()

        # Personen-Fallback: echter DACH-Name + breite Altersstreuung + realistisches Gender.
        if entity_type_lower in ["student", "alumni"]:
            dach = self._pick_dach_name()
            return {
                "display_name": dach,
                "handle": dach.lower().replace(" ", "_"),
                "bio": f"{entity_type} with interests in academics and social issues.",
                "persona": f"{dach} ist {entity_type.lower()} und aktiv in akademischen und sozialen Diskussionen. Teilt Perspektiven und vernetzt sich mit Peers.",
                "age": random.randint(18, 32),
                "gender": self._pick_individual_gender(),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": "DE",
                "profession": "Student",
                "interested_topics": ["Bildung", "Gesellschaft", "Technologie"],
                "voice_register": self._rule_based_voice_register(entity_type_lower, "Student"),
            }

        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            dach = self._pick_dach_name()
            profession_str = entity_attributes.get("occupation", "Fachexpertin/Fachexperte")
            return {
                "display_name": dach,
                "handle": dach.lower().replace(" ", "_"),
                "bio": "Expert and thought leader in their field.",
                "persona": f"{dach} ist eine anerkannte Fachperson und teilt Einschätzungen zu relevanten Themen. Bekannt für Expertise und Einfluss im öffentlichen Diskurs.",
                "age": random.randint(32, 68),
                "gender": self._pick_individual_gender(),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "country": "DE",
                "profession": profession_str,
                "interested_topics": ["Politik", "Wirtschaft", "Gesellschaft"],
                "voice_register": self._rule_based_voice_register(entity_type_lower, profession_str),
            }

        # Institutionen-Fallback: ECHTE PERSON als Repräsentant/in der Organisation.
        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            dach = self._pick_dach_name()
            return {
                "display_name": dach,
                "handle": dach.lower().replace(" ", "_"),
                "bio": f"Redaktion bei {entity_name} | Nachrichten, Analysen, Einordnung",
                "persona": f"{dach} arbeitet als Redakteur:in bei {entity_name} und teilt berufliche Einschätzungen zu aktuellen Themen sowie gelegentlich persönliche Meinungen.",
                "age": random.randint(28, 58),
                "gender": self._pick_individual_gender(),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": "DE",
                "profession": f"Redakteur:in bei {entity_name}",
                "interested_topics": ["Nachrichten", "Aktuelles", "Öffentlichkeit"],
                "voice_register": self._rule_based_voice_register(entity_type_lower, "journalist"),
            }

        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            dach = self._pick_dach_name()
            return {
                "display_name": dach,
                "handle": dach.lower().replace(" ", "_"),
                "bio": f"Mitarbeiter:in bei {entity_name} | spricht aus der Praxis",
                "persona": f"{dach} ist bei {entity_name} beschäftigt und vertritt die Organisation öffentlich — mal mit offizieller Position, mal mit persönlicher Sicht aus dem Arbeitsalltag.",
                "age": random.randint(25, 62),
                "gender": self._pick_individual_gender(),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": "DE",
                "profession": f"Mitarbeiter:in bei {entity_name}",
                "interested_topics": ["Politik", "Community", "Arbeit"],
                "voice_register": self._rule_based_voice_register(entity_type_lower, ""),
            }

        else:
            # Default: behandeln wir als Person mit breiter Streuung.
            dach = self._pick_dach_name()
            return {
                "display_name": dach,
                "handle": dach.lower().replace(" ", "_"),
                "bio": entity_summary[:150] if entity_summary else f"{entity_type}: {entity_name}",
                "persona": entity_summary or f"{dach} nimmt aktiv an sozialen Diskussionen teil.",
                "age": random.randint(20, 70),
                "gender": self._pick_individual_gender(),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": "DE",
                "profession": entity_type,
                "interested_topics": ["Allgemein", "Gesellschaft"],
                "voice_register": self._rule_based_voice_register(entity_type_lower, entity_type),
            }
    
    def set_graph_id(self, graph_id: str):
        """Set knowledge graph ID for knowledge graph search"""
        self.graph_id = graph_id
    
    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 5,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """
        Generate Agent Profiles in batch from entities (supports parallel generation)

        Args:
            entities: Entity list
            use_llm: Whether to use LLM to generate detailed personas
            progress_callback: Progress callback function (current, total, message)
            graph_id: Knowledge graph ID for knowledge graph search to get richer context
            parallel_count: Number of parallel generations, default 5
            realtime_output_path: Real-time output file path (if provided, write after each generation)
            output_platform: Output platform format ("reddit" or "twitter")

        Returns:
            List of Agent Profiles
        """
        import concurrent.futures
        from threading import Lock
        
        # Set graph_id for knowledge graph search
        if graph_id:
            self.graph_id = graph_id

        total = len(entities)
        profiles = [None] * total  # Pre-allocate list to maintain order
        completed_count = [0]  # Use list for modification in closure
        lock = Lock()

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
                            fieldnames = list(profiles_data[0].keys())
                            with open(realtime_output_path, 'w', encoding='utf-8', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(profiles_data)
                except Exception as e:
                    logger.warning(f"Real-time profile save failed: {e}")
        
        def generate_single_profile(idx: int, entity: EntityNode) -> tuple:
            """Worker function to generate single profile"""
            entity_type = entity.get_entity_type() or "Entity"

            try:
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=idx,
                    use_llm=use_llm
                )

                # Real-time output generated persona to console and log
                self._print_generated_profile(entity.name, entity_type, profile)

                return idx, profile, None

            except Exception as e:
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
                )
                return idx, fallback_profile, str(e)

        logger.info(f"Starting parallel generation of {total} agent personas (parallel count: {parallel_count})...")
        print(f"\n{'='*60}")
        print(f"Starting agent persona generation - {total} entities total, parallel count: {parallel_count}")
        print(f"{'='*60}\n")
        
        # Use thread pool for parallel execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            # Submit all tasks
            future_to_entity = {
                executor.submit(generate_single_profile, idx, entity): (idx, entity)
                for idx, entity in enumerate(entities)
            }

            # Collect results
            for future in concurrent.futures.as_completed(future_to_entity):
                idx, entity = future_to_entity[future]
                entity_type = entity.get_entity_type() or "Entity"

                try:
                    result_idx, profile, error = future.result()
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

                except Exception as e:
                    logger.error(f"Exception occurred while processing entity {entity.name}: {str(e)}")
                    with lock:
                        completed_count[0] += 1
                    profiles[idx] = OasisAgentProfile(
                        user_id=idx,
                        user_name=self._generate_username(entity.name),
                        name=entity.name,
                        bio=f"{entity_type}: {entity.name}",
                        persona=entity.summary or "A participant in social discussions.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                    )
                    # Real-time file writing (even for fallback personas)
                    save_profiles_realtime()

        # Dedup display_name und user_name: LLM neigt dazu, dieselbe reale Person
        # mehrfach zu klonen wenn sie im Doc prominent ist. Bei Dubletten neuen
        # DACH-Namen aus dem Pool ziehen, Handle entsprechend neu bauen.
        seen_names: set = set()
        seen_last_names: set = set()
        seen_handles: set = set()
        for p in profiles:
            if p is None:
                continue
            norm_name = (p.name or "").strip().lower()
            last_name = self._last_name(p.name or "")
            if norm_name and (
                norm_name in seen_names
                or (last_name is not None and last_name in seen_last_names)
            ):
                new_name = self._pick_dach_name()
                attempts = 0
                while (
                    new_name.lower() in seen_names
                    or (self._last_name(new_name) or "") in seen_last_names
                ) and attempts < 30:
                    new_name = self._pick_dach_name()
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

        print(f"\n{'='*60}")
        print(f"Persona generation complete! Generated {len([p for p in profiles if p])} agents")
        print(f"{'='*60}\n")

        # Re-save after dedup to keep realtime file in sync with final state.
        save_profiles_realtime()

        return profiles
    
    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        """Real-time output generated persona to console (complete content, not truncated)"""
        separator = "-" * 70

        # Build complete output content (not truncated)
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else 'None'

        output_lines = [
            f"\n{separator}",
            f"[Generated] {entity_name} ({entity_type})",
            f"{separator}",
            f"Username: {profile.user_name}",
            "",
            "[Bio]",
            f"{profile.bio}",
            "",
            "[Detailed Persona]",
            f"{profile.persona}",
            "",
            "[Basic Attributes]",
            f"Age: {profile.age} | Gender: {profile.gender} | MBTI: {profile.mbti}",
            f"Profession: {profile.profession} | Country: {profile.country}",
            f"Interested Topics: {topics_str}",
            separator
        ]

        output = "\n".join(output_lines)

        # Only output to console (avoid duplication, logger no longer outputs complete content)
        print(output)
    
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
            # Use format consistent with to_reddit_format()
            item = {
                "user_id": profile.user_id if profile.user_id is not None else idx,  # Key: must include user_id
                "username": profile.user_name,
                "name": profile.name,
                "bio": profile.bio[:150] if profile.bio else f"{profile.name}",
                "persona": profile.persona or f"{profile.name} is a participant in social discussions.",
                "karma": profile.karma if profile.karma else 1000,
                "created_at": profile.created_at,
                # OASIS required fields - ensure all have defaults
                "age": profile.age if profile.age else 30,
                "gender": self._normalize_gender(profile.gender),
                "mbti": profile.mbti if profile.mbti else "ISTJ",
                "country": profile.country if profile.country else "US",
            }

            # Optional fields
            if profile.profession:
                item["profession"] = profile.profession
            if profile.interested_topics:
                item["interested_topics"] = profile.interested_topics
            if profile.source_entity_uuid:
                item["source_entity_uuid"] = profile.source_entity_uuid
            if profile.source_entity_type:
                item["source_entity_type"] = profile.source_entity_type

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
