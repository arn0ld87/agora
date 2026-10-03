"""Implementation helpers extracted from OasisProfileGenerator.

The public compatibility surface remains app.services.oasis_profile_generator.
"""

from __future__ import annotations

from typing import Any

from . import oasis_profile_generator as _legacy
import random
from typing import List, Optional
from collections.abc import Mapping
from ..contracts.persona_contract import (
    documented_age,
    documented_gender,
    role_corrected_gender,
)
from .entity_reader import EntityNode
from .oasis_profile_models import (
    OasisAgentProfile,
    PersonaDemographicSlot,
    PersonaIneligible,
    taken_display_names,
)

#: Graph-Attribute, die eine im Dokument belegte Position tragen (Issue #1759, A3).
_POSITION_ATTRIBUTE_KEYS = ("stance", "position", "position_on_closure", "haltung")


def _documented_position_block (attributes :Optional [Mapping [str ,Any ]])->str :
    """Verbindlicher Prompt-Hinweis auf die im Dokument belegte Position."""
    lines =[
    f"- {key }: {str (value ).strip ()}"
    for key ,value in (attributes or {}).items ()
    if str (key ).casefold ()in _POSITION_ATTRIBUTE_KEYS and str (value or "").strip ()
    ]
    if not lines :
        return ""
    return (
    "### Dokumentierte Position (verbindlich)\n"
    "Die Position dieser Entität ist im Quelldokument belegt. Übernimm sie "
    "unverändert; erfinde keine abweichende Haltung.\n"+"\n".join (lines )
    )


def _with_position_block (attributes :Optional [Mapping [str ,Any ]],context :str )->str :
    """Stellt die dokumentierte Position (falls vorhanden) dem Kontext voran (A3)."""
    block =_documented_position_block (attributes )
    return f"{block }\n\n{context }"if block else context


def _resolve_taken_names (generator :Any ,taken_names :Optional [List [str ]])->Optional [List [str ]]:
    """Explizit uebergebene Namen gewinnen, sonst die des laufenden Batches (A1)."""
    return taken_display_names (generator )if taken_names is None else taken_names


def _apply_role_gender (
profile_data :dict [str ,Any ],
attributes :Optional [Mapping [str ,Any ]],
profession :Optional [str ],
bio :Optional [str ],
)->None :
    """Gender auf die Berufsbezeichnung korrigieren, sofern nicht im Dokument belegt (A2)."""
    if documented_gender (attributes )is None :
        profile_data ["gender"]=role_corrected_gender (profile_data .get ("gender"),profession ,bio )


def _apply_documented_demographics (
profile_data :dict [str ,Any ],
attributes :Optional [Mapping [str ,Any ]],
is_collective :bool =False ,
)->None :
    """Dokument-Belege (Alter, Geschlecht) schlagen gewuerfelte Slot-Werte (#1759 A2).

    Kollektive tragen keine Demografie und bleiben unberuehrt.
    """
    if is_collective :
        return
    age =documented_age (attributes )
    if age is not None :
        profile_data ["age"]=age
    gender =documented_gender (attributes )
    if gender is not None :
        profile_data ["gender"]=gender


def generate_profile_from_entity (
self: Any ,
entity :EntityNode ,
user_id :int ,
use_llm :bool =True ,
demographic_slot :Optional [PersonaDemographicSlot ]=None ,
taken_names :Optional [List [str ]]=None ,
)->OasisAgentProfile :
    """
    Generate OASIS Agent Profile from knowledge graph entity

    Args:
        entity: Knowledge graph entity node
        user_id: User ID (for OASIS)
        use_llm: Whether to use LLM to generate detailed persona

    Returns:
        OasisAgentProfile
    """
    entity_type =entity .get_entity_type ()or "Entity"

    # Fallback-Basics: echter Entity-Name + abgeleiteter Username.
    # Werden später überschrieben, wenn LLM/Rule-based display_name + handle liefern.
    name =entity .name
    user_name =self ._generate_username (name )

    # Build context information
    context =self ._build_entity_context (entity )

    # Issue #1713/#1470: Die Person wurde beim Prepare-Lesen mit der
    # Organisation zusammengelegt, die sie laut Graph-Relation vertritt.
    # Der Prompt bekommt das explizit, sonst schreibt das Modell eine Bio,
    # die diese Zugehoerigkeit nicht kennt.
    if entity .affiliation :
        context =(
        f"### Organisationszugehörigkeit\n"
        f"Diese Person vertritt laut Wissensgraph „{entity .affiliation }“. "
        f"Bio und Personenbeschreibung sollen das benennen, z. B. "
        f"„spricht für {entity .affiliation }“.\n\n{context }"
        )

    # Issue #1759 (A3): Eine im Dokument belegte Position der Entität ist
    # verbindlich und darf nicht durch eine erfundene Haltung ersetzt werden.
    context =_with_position_block (entity .attributes ,context )

    # Issue #1759 (A1): bereits vergebene Anzeigenamen reichen bis in den
    # Prompt, damit der Dedup nicht nachtraeglich umbenennen muss.
    taken_names =_resolve_taken_names (self ,taken_names )

    if use_llm :
    # Use LLM to generate detailed persona
        profile_data =self ._generate_profile_with_llm (
        entity_name =name ,
        entity_type =entity_type ,
        entity_summary =entity .summary ,
        entity_attributes =entity .attributes ,
        context =context ,
        demographic_slot =demographic_slot ,
        taken_names =taken_names ,
        )
    else :
    # Use rules to generate basic persona
        profile_data =self ._generate_profile_rule_based (
        entity_name =name ,
        entity_type =entity_type ,
        entity_summary =entity .summary ,
        entity_attributes =entity .attributes ,
        demographic_slot =demographic_slot ,
        affiliation =entity .affiliation ,
        )

        # Issue #1247: Das Modell darf die Entitaet zurueckweisen, statt eine
        # Persona zu erfinden. Bewusst als Ausnahme und nicht als stilles
        # Ueberspringen — der Aufrufer muss den Slot nachbesetzen koennen.
    if profile_data .get ("ineligible"):
        reason =(profile_data .get ("ineligible_reason")or "").strip ()or (
        "vom Persona-Generator als nicht personenfaehig zurueckgewiesen"
        )
        _legacy .logger .info (
        "Persona-Eligibility (LLM): Entitaet abgelehnt name=%s type=%s reason=%s",
        name ,
        entity_type ,
        reason ,
        )
        raise PersonaIneligible (name ,entity_type ,reason )

        # Issue #1246: Der Kollektiv-Zweig ist bewusst hier sichtbar und nicht
        # in den Individuenpfad eingebettet. Eine Organisation bekommt keine
        # Demografie zugewiesen — es gibt kein Alter, kein Geschlecht und
        # keinen MBTI-Typ, den man ihr zuschreiben koennte, und jeder Wert an
        # dieser Stelle waere eine Erfindung.
    is_collective =self ._is_group_entity (entity_type )
    persona_kind ="collective"if is_collective else "individual"

    if is_collective :
        profile_data ["age"]=None
        profile_data ["gender"]=None
        profile_data ["mbti"]=None
        # Eine Kollektiv-Persona hat keinen Beruf. "Dozent und
        # Betriebsratsmitglied" war aus einem Bildungstraeger nicht
        # ableitbar, sondern eine plausible Vita.
        profile_data ["profession"]=None
    elif demographic_slot is not None :
        profile_data ["age"]=demographic_slot .age
        profile_data ["gender"]=demographic_slot .gender
        profile_data ["mbti"]=demographic_slot .mbti
    _apply_documented_demographics (profile_data ,entity .attributes ,is_collective )

        # LLM/Rule-based darf display_name (echter Name) + handle (kurzes Social-Handle)
        # überschreiben. So wird aus Entity "GraphRAG" z.B. Person "Lena Hoffmann" mit
        # Handle "lena_hoffmann". Fuer Kollektive bleibt der Entitaetsname stehen:
        # der Traeger spricht als Traeger, nicht als erfundener Mitarbeiter.
    if not is_collective :
        display_name =(profile_data .get ("display_name")or "").strip ()
        if display_name :
            name =display_name
        handle =(profile_data .get ("handle")or "").strip ()
        if handle :
            user_name =self ._generate_username (handle )

            # Issue #1246 (P1): Der Freitext muss dieselbe Person beschreiben, die
            # oben benannt ist. Fuer Kollektive entfaellt die Frage.
    persona_text =profile_data .get ("persona",entity .summary or f"A {entity_type } named {name }.")
    if not is_collective :
        persona_text =self ._align_persona_identity (persona_text ,name )

        # Issue #1246 (P3): Der Entitaetstyp ist keine Berufsbezeichnung. Wo
        # der degradierte Pfad nichts abzuleiten wusste, reichte er ihn woertlich
        # durch — "AIProvider", "WorkingGroup", "TechnologyVendor". Lieber keine
        # Angabe als eine falsche.
    profession =_profession_without_entity_type (
    profile_data .get ("profession"),entity_type
    )

    bio =profile_data .get ("bio",f"{entity_type }: {name }")
    resolution =self ._persona_after_coherence_check (
    entity_type =entity_type ,
    entity_name =name ,
    persona_kind =persona_kind ,
    profession =profession ,
    bio =bio ,
    persona_text =persona_text ,
    entity_summary =entity .summary ,
    entity_context =context ,
    use_llm =use_llm ,
    )
    profession =resolution .profession
    bio =resolution .bio
    persona_text =resolution .persona_text
    if not is_collective :
    # Die Korrektur kann den Eroeffnungsnamen des Freitexts veraendern;
    # dieselbe Angleichung wie bei der Erstgenerierung, idempotent wenn
    # sich nichts geaendert hat.
        persona_text =self ._align_persona_identity (persona_text ,name )
        # Issue #1759 (A2): grammatisches Gender der Berufsbezeichnung
        # (Chefaerztin/Chefarzt) schlaegt den gewuerfelten Slot-Wert; ein
        # im Dokument belegtes Geschlecht bleibt unangetastet.
        _apply_role_gender (profile_data ,entity .attributes ,profession ,bio )
    generation_error =_merge_generation_error (
    profile_data .get ("generation_error"),resolution .generation_error
    )

    # Segment = entity_type string for PersonaQuotaPlan validation.
    # entity_type is already resolved above (get_entity_type() or "Entity").
    segment =entity_type if entity_type !="Entity"else None

    return OasisAgentProfile (
    user_id =user_id ,
    user_name =user_name ,
    name =name ,
    bio =bio ,
    persona =persona_text ,
    karma =profile_data .get ("karma",random .randint (500 ,5000 )),
    friend_count =profile_data .get ("friend_count",random .randint (50 ,500 )),
    follower_count =profile_data .get ("follower_count",random .randint (100 ,1000 )),
    statuses_count =profile_data .get ("statuses_count",random .randint (100 ,2000 )),
    age =profile_data .get ("age"),
    gender =profile_data .get ("gender"),
    mbti =profile_data .get ("mbti"),
    country =profile_data .get ("country"),
    profession =profession ,
    interested_topics =profile_data .get ("interested_topics",[]),
    source_entity_uuid =entity .uuid ,
    source_entity_type =entity_type ,
    affiliation =entity .affiliation ,
    segment =segment ,
    persona_kind =persona_kind ,
    voice_register =profile_data .get ("voice_register"),
    # Issue #1029: Default "llm" — nur der regelbasierte Pfad setzt
    # den Schlüssel, und er setzt ihn immer.
    generation_source =profile_data .get ("generation_source","llm"),
    generation_error =generation_error ,
    )


def _profession_without_entity_type (
profession :Any ,entity_type :str
)->Optional [str ]:
    """Issue #1246 (P3): Der Entitaetstyp ist keine Berufsbezeichnung. Wo der
    degradierte Pfad nichts abzuleiten wusste, reichte er ihn woertlich durch
    — "AIProvider", "WorkingGroup", "TechnologyVendor". Lieber keine Angabe
    als eine falsche."""
    if isinstance (profession ,str )and profession .strip ().lower ()==entity_type .strip ().lower ():
        _legacy .logger .debug (
        "Persona-Beruf verworfen: entity_type wurde als profession durchgereicht (%s)",
        entity_type ,
        )
        return None
    return profession


def _merge_generation_error (
existing :Optional [str ],coherence_error :Optional [str ]
)->Optional [str ]:
    """Der Fehler der Erstgenerierung und der der Drift-Korrektur bleiben
    beide sichtbar."""
    if not coherence_error :
        return existing
    return f"{existing }; {coherence_error }"if existing else coherence_error


def _generate_username (self: Any ,name :str )->str :
    """Generate username"""
    # Remove special characters, convert to lowercase
    username =name .lower ().replace (" ","_")
    username =''.join (c for c in username if c .isalnum ()or c =='_')

    # Add random suffix to avoid duplicates
    suffix =random .randint (100 ,999 )
    return f"{username }_{suffix }"
