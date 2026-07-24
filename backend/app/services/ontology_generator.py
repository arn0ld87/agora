"""
Ontology generation service
Interface 1: Analyze text content and generate entity and relationship type definitions suitable for social simulation
"""

from typing import Dict, Any, List, Optional

from pydantic import BaseModel, Field

from ..config import Config
from ..utils.llm_client import LLMClient
from .settings_layer import get_default_service as _get_settings


class OntologyAttribute(BaseModel):
    """Attribut eines Entity- oder Edge-Typs in der Ontology-Definition."""

    name: str = Field(..., description="Attribute name (English, snake_case)")
    type: str = Field("text", description="Attribute type, typically 'text'")
    description: str = Field("", description="Attribute description")


class OntologyEntityType(BaseModel):
    """Entity-Typ in der Ontology-Definition."""

    name: str = Field(..., description="Entity type name (English, PascalCase)")
    description: str = Field(..., description="Brief description (English, <=100 chars)")
    attributes: List[OntologyAttribute] = Field(
        default_factory=list, description="1-3 key attributes"
    )
    examples: List[str] = Field(
        default_factory=list, description="Example entities of this type"
    )


class OntologySourceTarget(BaseModel):
    """Source/Target-Paar eines Edge-Typs."""

    source: str = Field(..., description="Source entity type name")
    target: str = Field(..., description="Target entity type name")


class OntologyEdgeType(BaseModel):
    """Edge-/Relationship-Typ in der Ontology-Definition."""

    name: str = Field(..., description="Relationship type name (English, UPPER_SNAKE_CASE)")
    description: str = Field(..., description="Brief description (English, <=100 chars)")
    source_targets: List[OntologySourceTarget] = Field(
        default_factory=list, description="Valid source/target entity-type pairs"
    )
    attributes: List[OntologyAttribute] = Field(
        default_factory=list, description="Optional edge attributes"
    )


class OntologyDefinition(BaseModel):
    """Striktes Pydantic-Schema für die LLM-generierte Ontology-Definition.

    Wird an ``chat_json(schema=...)`` übergeben, damit der Provider im
    strict-``json_schema``-Mode antwortet und kein Prosa-Envelope emittiert
    (MiniMax-M3-Quirk: ohne ``response_format`` mischt M3 erklärenden Text
    ins JSON → Parse-Fehler in ~20 % der Läufe).
    """

    entity_types: List[OntologyEntityType] = Field(
        ..., description="8-16 entity types (last 2 must be Person, Organization)"
    )
    edge_types: List[OntologyEdgeType] = Field(
        ..., description="6-10 relationship types"
    )
    analysis_summary: str = Field(
        "", description="Brief analysis and explanation of text content"
    )


# System prompt for ontology generation
ONTOLOGY_SYSTEM_PROMPT = """You are a professional knowledge graph ontology design expert. Your task is to analyze given text content and simulation requirements, and design entity types and relationship types suitable for **social media opinion simulation**.

**Important: You must output valid JSON format data, do not output anything else.**

## Core Task Background

We are building a **social media opinion simulation system**. In this system:
- Each entity is an "account" or "subject" that can voice, interact, and spread information on social media
- Entities influence each other, retweet, comment, and respond
- We need to simulate the reactions of various parties in opinion events and information dissemination paths

Therefore, **entities must be real-world entities that can voice and interact on social media**:

**Can be**:
- Specific individuals (public figures, stakeholders, opinion leaders, experts, ordinary people)
- Companies and enterprises (including their official accounts)
- Organizations (universities, associations, NGOs, unions, etc.)
- Government departments and regulatory agencies
- Media institutions (newspapers, TV stations, self-media, websites)
- Social media platforms themselves
- Specific group representatives (such as alumni associations, fan groups, rights protection groups, etc.)

**Cannot be**:
- Abstract concepts (such as "public opinion", "emotion", "trend")
- Topics/subjects (such as "academic integrity", "education reform")
- Views/attitudes (such as "supporters", "opponents")

## Output Format

Please output JSON format with the following structure:

```json
{
    "entity_types": [
        {
            "name": "Entity type name (English, PascalCase)",
            "description": "Brief description (English, no more than 100 characters)",
            "attributes": [
                {
                    "name": "Attribute name (English, snake_case)",
                    "type": "text",
                    "description": "Attribute description"
                }
            ],
            "examples": ["Example entity 1", "Example entity 2"]
        }
    ],
    "edge_types": [
        {
            "name": "Relationship type name (English, UPPER_SNAKE_CASE)",
            "description": "Brief description (English, no more than 100 characters)",
            "source_targets": [
                {"source": "Source entity type", "target": "Target entity type"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "Brief analysis and explanation of text content"
}
```

## Design Guidelines (Extremely Important!)

### 1. Entity Type Design - Must Strictly Follow

**Quantity requirement: Generate 8-16 entity types, based on document complexity**

**Hierarchical structure requirement (must include both specific types and fallback types)**:

Your entity types must include the following hierarchy:

A. **Fallback types (must include, place in last 2 of list)**:
   - `Person`: Fallback type for any natural person. When a person does not fit other more specific person types, use this.
   - `Organization`: Fallback type for any organization. When an organization does not fit other more specific organization types, use this.

B. **Specific types (designed based on text content)**:
   - Design more specific types for main characters appearing in the text
   - Example: If text involves academic events, can have `Student`, `Professor`, `University`
   - Example: If text involves business events, can have `Company`, `CEO`, `Employee`

**Why fallback types are needed**:
- Various people will appear in the text, such as "primary/secondary teachers", "random person", "some netizen"
- If no specific type matches, they should be classified as `Person`
- Similarly, small organizations and temporary groups should be classified as `Organization`

**Design principles for specific types**:
- Identify high-frequency or key role types from the text
- Each specific type should have clear boundaries, avoid overlap
- Description must clearly explain the difference between this type and the fallback type

### 2. Relationship Type Design

- Quantity: 6-10
- Relationships should reflect real connections in social media interactions
- Ensure relationship source_targets cover your defined entity types

### 3. Attribute Design

- 1-3 key attributes per entity type
- **Note**: Attribute names cannot use `name`, `uuid`, `group_id`, `created_at`, `summary` (these are system reserved words)
- Recommended: `full_name`, `title`, `role`, `position`, `location`, `description`, etc.

## Entity Type Reference

**Individual types (specific)**:
- Student: Student
- Professor: Professor/Scholar
- Journalist: Journalist
- Celebrity: Celebrity/Internet celebrity
- Executive: Executive
- Official: Government official
- Lawyer: Lawyer
- Doctor: Doctor

**Individual types (fallback)**:
- Person: Any natural person (use when not fitting other specific types)

**Organization types (specific)**:
- University: University
- Company: Company/Enterprise
- GovernmentAgency: Government agency
- MediaOutlet: Media institution
- Hospital: Hospital
- School: Primary/Secondary school
- NGO: Non-governmental organization

**Organization types (fallback)**:
- Organization: Any organization (use when not fitting other specific types)

## Relationship Type Reference

- WORKS_FOR: Works for
- STUDIES_AT: Studies at
- AFFILIATED_WITH: Affiliated with
- REPRESENTS: Represents
- REGULATES: Regulates
- REPORTS_ON: Reports on
- COMMENTS_ON: Comments on
- RESPONDS_TO: Responds to
- SUPPORTS: Supports
- OPPOSES: Opposes
- COLLABORATES_WITH: Collaborates with
- COMPETES_WITH: Competes with
"""


class OntologyGenerator:
    """
    Ontology generator
    Analyze text content and generate entity and relationship type definitions
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate ontology definition

        Args:
            document_texts: List of document texts
            simulation_requirement: Description of simulation requirements
            additional_context: Additional context

        Returns:
            Ontology definition (entity_types, edge_types, etc.)
        """
        # Build user message
        user_message = self._build_user_message(
            document_texts,
            simulation_requirement,
            additional_context
        )

        messages = [
            {"role": "system", "content": ONTOLOGY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]

        # Call LLM. 12288 tokens fit a 8–12 entity-type schema with attributes
        # and examples plus the reasoning-block overhead that cloud models such
        # as qwen3-coder-next:cloud and deepseek-v4:cloud emit (5–10 k tokens
        # for the JSON alone). With 4096–8192 the answer got clipped mid-string
        # and the chat_json layer surfaced "Invalid JSON format from LLM" in
        # the UI. chat_json still best-effort-repairs trailing truncation as a
        # safety net for outliers.
        #
        # schema=OntologyDefinition erzwingt strict json_schema-Mode beim
        # Provider. MiniMax-M3 misst ohne response_format in ~20 % der Läufe
        # erklärenden Prosa-Text ins JSON ein (finish=stop, Budget nicht
        # voll) → Parse-Fehler. Strict-Schema zwingt M3, gültiges JSON nach
        # Schema zu liefern. force_no_thinking=True deaktiviert zusätzlich den
        # Reasoning-Output, damit das Token-Budget voll für den Content zur
        # Verfügung steht (analog report_agent/planning.py).
        max_tokens = int(_get_settings().effective_value('ONTOLOGY_MAX_TOKENS'))
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.3,
            max_tokens=max_tokens,
            schema=OntologyDefinition,
            schema_name="ontology_definition",
            force_no_thinking=True,
        )

        # Validate and post-process
        result = self._validate_and_process(result)

        return result

    # Maximum text length for LLM (50,000 characters)
    MAX_TEXT_LENGTH_FOR_LLM = 50000

    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """Build user message"""

        # Combine texts
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)

        # If text exceeds 50,000 characters, truncate (only affects LLM input, not graph construction)
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(Original text has {original_length} characters, first {self.MAX_TEXT_LENGTH_FOR_LLM} characters extracted for ontology analysis)..."

        message = f"""## Simulation Requirements

{simulation_requirement}

## Document Content

{combined_text}
"""

        if additional_context:
            message += f"""
## Additional Explanation

{additional_context}
"""

        message += f"""
Based on the above content, design entity types and relationship types suitable for social opinion simulation.

**Rules to follow**:
1. Output between {Config.ONTOLOGY_MIN_ENTITY_TYPES} and {Config.ONTOLOGY_MAX_ENTITY_TYPES} entity types, based on document complexity
2. Last 2 must be fallback types: Person (individual fallback) and Organization (organization fallback)
3. All other types are specific types designed based on text content
4. All entity types must be real-world subjects that can voice opinions, not abstract concepts
5. Attribute names cannot use reserved words like name, uuid, group_id, use full_name, org_name, etc. instead
"""

        return message
    
    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and post-process result"""

        # Ensure necessary fields exist
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""

        # Validate entity types
        for entity in result["entity_types"]:
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            # Ensure description doesn't exceed 100 characters
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."

        # Validate relationship types
        for edge in result["edge_types"]:
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."

        max_entity_types = max(2, Config.ONTOLOGY_MAX_ENTITY_TYPES)
        max_edge_types = max(1, Config.ONTOLOGY_MAX_EDGE_TYPES)

        # Fallback type definitions
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }

        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }

        # Check if fallback types already exist
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names

        # Fallback types to add
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)

        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)

            # If adding would exceed the configured cap, remove some specific
            # types from the end while preserving slots for fallbacks.
            if current_count + needed_slots > max_entity_types:
                # Calculate how many to remove
                to_remove = current_count + needed_slots - max_entity_types
                # Remove from end (keep more important specific types in front)
                result["entity_types"] = result["entity_types"][:-to_remove]

            # Add fallback types
            result["entity_types"].extend(fallbacks_to_add)

        # Final check to ensure limits not exceeded (defensive programming)
        if len(result["entity_types"]) > max_entity_types:
            fallbacks = [
                entity
                for entity in result["entity_types"]
                if entity.get("name") in {"Person", "Organization"}
            ]
            fallback_names = {entity.get("name") for entity in fallbacks}
            specific_slots = max_entity_types - len(fallback_names)
            specifics = [
                entity
                for entity in result["entity_types"]
                if entity.get("name") not in {"Person", "Organization"}
            ][:specific_slots]
            result["entity_types"] = specifics + fallbacks

        if len(result["edge_types"]) > max_edge_types:
            result["edge_types"] = result["edge_types"][:max_edge_types]

        return result
    
    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
        [DEPRECATED] Convert ontology definition to Zep-format Pydantic code.
        Not used in Agora (ontology stored as JSON in Neo4j).
        Kept for reference only.
        """
        code_lines = [
            '"""',
            'Custom entity type definitions',
            'Auto-generated by Agora for social opinion simulation',
            '"""',
            '',
            'from pydantic import Field',
            'from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel',
            '',
            '',
            '# ============== Entity Type Definitions ==============',
            '',
        ]

        # Generate entity types
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")

            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')

            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append('        default=None')
                    code_lines.append('    )')
            else:
                code_lines.append('    pass')

            code_lines.append('')
            code_lines.append('')

        code_lines.append('# ============== Relationship Type Definitions ==============')
        code_lines.append('')

        # Generate relationship types
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # Convert to PascalCase class name
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")

            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')

            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append('        default=None')
                    code_lines.append('    )')
            else:
                code_lines.append('    pass')

            code_lines.append('')
            code_lines.append('')

        # Generate type dictionaries
        code_lines.append('# ============== Type Configuration ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')

        # Generate source_targets mapping for edges
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')

        return '\n'.join(code_lines)
