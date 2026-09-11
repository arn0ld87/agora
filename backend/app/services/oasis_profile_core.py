"""Implementation helpers extracted from OasisProfileGenerator.

The public compatibility surface remains app.services.oasis_profile_generator.
"""

from __future__ import annotations

from typing import Any

from . import oasis_profile_generator as _legacy
import random
from typing import Optional
from .entity_reader import EntityNode
from .oasis_profile_models import OasisAgentProfile, PersonaDemographicSlot, PersonaIneligible

def generate_profile_from_entity (
self: Any ,
entity :EntityNode ,
user_id :int ,
use_llm :bool =True ,
demographic_slot :Optional [PersonaDemographicSlot ]=None ,
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

    if use_llm :
    # Use LLM to generate detailed persona
        profile_data =self ._generate_profile_with_llm (
        entity_name =name ,
        entity_type =entity_type ,
        entity_summary =entity .summary ,
        entity_attributes =entity .attributes ,
        context =context ,
        demographic_slot =demographic_slot ,
        )
    else :
    # Use rules to generate basic persona
        profile_data =self ._generate_profile_rule_based (
        entity_name =name ,
        entity_type =entity_type ,
        entity_summary =entity .summary ,
        entity_attributes =entity .attributes ,
        demographic_slot =demographic_slot ,
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
    profession =profile_data .get ("profession")
    if isinstance (profession ,str )and profession .strip ().lower ()==entity_type .strip ().lower ():
        _legacy .logger .debug (
        "Persona-Beruf verworfen: entity_type wurde als profession durchgereicht (%s)",
        entity_type ,
        )
        profession =None 

    profession =self ._profession_after_coherence_check (
    entity_type =entity_type ,
    entity_name =name ,
    persona_kind =persona_kind ,
    profession =profession ,
    persona_text =persona_text ,
    entity_summary =entity .summary ,
    entity_context =context ,
    )

    # Segment = entity_type string for PersonaQuotaPlan validation.
    # entity_type is already resolved above (get_entity_type() or "Entity").
    segment =entity_type if entity_type !="Entity"else None 

    return OasisAgentProfile (
    user_id =user_id ,
    user_name =user_name ,
    name =name ,
    bio =profile_data .get ("bio",f"{entity_type }: {name }"),
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
    segment =segment ,
    persona_kind =persona_kind ,
    voice_register =profile_data .get ("voice_register"),
    # Issue #1029: Default "llm" — nur der regelbasierte Pfad setzt
    # den Schlüssel, und er setzt ihn immer.
    generation_source =profile_data .get ("generation_source","llm"),
    generation_error =profile_data .get ("generation_error"),
    )


def _generate_username (self: Any ,name :str )->str :
    """Generate username"""
    # Remove special characters, convert to lowercase
    username =name .lower ().replace (" ","_")
    username =''.join (c for c in username if c .isalnum ()or c =='_')

    # Add random suffix to avoid duplicates
    suffix =random .randint (100 ,999 )
    return f"{username }_{suffix }"
