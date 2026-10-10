"""Implementation helpers extracted from OasisProfileGenerator.

The public compatibility surface remains app.services.oasis_profile_generator.
"""

from __future__ import annotations

from typing import Any

from . import oasis_profile_generator as _legacy
import dataclasses
import random
from typing import List, Optional
from collections.abc import Mapping
from ..contracts.persona_contract import (
    documented_age,
    documented_gender,
    role_compatible_age,
    role_corrected_gender,
)
from ..contracts.persona_identity_contract import PersonaIdentityBinding
from .entity_reader import EntityNode
from .persona_identity_binding import (
    build_identity_prompt_block,
    resolve_identity_binding,
    source_gender,
    source_person_fallback_fields,
)
from .oasis_profile_models import (
    OasisAgentProfile,
    PersonaDemographicSlot,
    PersonaIneligible,
    taken_display_names,
)
from .persona_voice_register import resolve_voice_register

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


def _slot_with_documented_demographics (
slot :Optional [PersonaDemographicSlot ],
attributes :Optional [Mapping [str ,Any ]],
is_collective :bool ,
)->Optional [PersonaDemographicSlot ]:
    """Slot mit den im Dokument belegten Werten, schon vor dem LLM-Aufruf (#1759 A2).

    Sonst beschreibt der Freitext den gewuerfelten Slot (``alter 29``), und erst
    nach der Generierung wird ``age`` auf den belegten Wert gesetzt: Feld und
    Text widersprechen sich. Kollektive und fehlende Slots bleiben unberuehrt;
    ``_apply_documented_demographics`` bleibt als Absicherung nach der Generierung.
    """
    if slot is None or is_collective :
        return slot
    age =documented_age (attributes )
    gender =documented_gender (attributes )
    return dataclasses .replace (
    slot ,
    age =slot .age if age is None else age ,
    gender =slot .gender if gender is None else gender ,
    )


def _with_identity_block (
self: Any ,
binding :PersonaIdentityBinding ,
entity :EntityNode ,
slot :Optional [PersonaDemographicSlot ],
context :str ,
)->str :
    """Stellt den Quellenbindungs- bzw. Ergaenzungs-Baustein dem Kontext voran (#1833).

    Fuer Kollektive und erfundene Vertreter bleibt der Kontext unveraendert.
    """
    if binding .origin not in ("source_person","synthetic_supplement"):
        return context
    is_person =binding .origin =="source_person"
    block =build_identity_prompt_block (
    binding ,
    documented_age =documented_age (entity .attributes )if is_person else None ,
    documented_gender =source_gender (binding ,entity .attributes )if is_person else None ,
    age_hint =(
    role_compatible_age (slot .age ,binding .documented_function )
    if is_person and slot is not None
    else None
    ),
    mbti =slot .mbti if is_person and slot is not None else None ,
    language =self .language ,
    )
    return f"{block }\n\n{context }"if block else context


def _apply_source_person_demographics (
profile_data :dict [str ,Any ],
binding :PersonaIdentityBinding ,
attributes :Optional [Mapping [str ,Any ]],
slot :Optional [PersonaDemographicSlot ],
)->None :
    """Geschlecht nur aus der Quelle, MBTI aus dem Slot (#1833).

    Wert des Modells und Slot-Wert fuer das Geschlecht werden verworfen; aus dem
    Vornamen wird nichts abgeleitet. Das Alter folgt zuletzt (``_source_person_age``).
    """
    profile_data ["gender"]=source_gender (binding ,attributes )
    if slot is not None :
        profile_data ["mbti"]=slot .mbti


def _apply_source_person_text (
profile_data :dict [str ,Any ],
binding :PersonaIdentityBinding ,
entity :EntityNode ,
answer_from_model :bool ,
)->None :
    """Text und Beruf einer Quellperson (#1833).

    Auf dem regelbasierten Weg stammen Bio, Persona und Beruf nur aus der
    Quelle (kein erfundener Name, kein typabgeleiteter Beruf). Bei einer
    Modellantwort ist der Beruf bei belegter Funktion deren Wortlaut.
    """
    if not answer_from_model :
        profile_data .update (
        source_person_fallback_fields (binding ,entity .summary ,entity .affiliation )
        )
    elif binding .function_evidence =="attribute":
        profile_data ["profession"]=binding .documented_function


def _source_person_age (
attributes :Optional [Mapping [str ,Any ]],
profile_data :dict [str ,Any ],
slot :Optional [PersonaDemographicSlot ],
answer_from_model :bool ,
profession :Optional [str ],
bio :Optional [str ],
)->Optional [int ]:
    """Alter einer Quellperson: Beleg, sonst rollenverträgliches Modell- oder Slot-Alter (#1833)."""
    documented =documented_age (attributes )
    if documented is not None :
        return documented
    raw =profile_data .get ("age")if answer_from_model else None
    if isinstance (raw ,int )and not isinstance (raw ,bool )and 18 <=raw <=75 :
        candidate :Optional [int ]=raw
    else :
        candidate =slot .age if slot is not None else None
    if candidate is None :
        return None
    return role_compatible_age (candidate ," ".join (part for part in (profession ,bio )if part ))


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

    # Issue #1759 (A2): belegte Demografie schon im Prompt anfordern, nicht
    # erst nach der Generierung ueber den gewuerfelten Slot legen.
    is_collective =self ._is_group_entity (entity_type )
    demographic_slot =_slot_with_documented_demographics (
    demographic_slot ,entity .attributes ,is_collective
    )

    # Issue #1833: Die Identitaet, die die Quelle vergibt, hat Vorrang vor
    # Modellumbenennung und zufaelliger Demografie.
    binding =resolve_identity_binding (
    entity_uuid =entity .uuid ,
    entity_name =entity .name ,
    entity_type =entity_type ,
    attributes =entity .attributes ,
    summary =entity .summary ,
    is_collective_type =is_collective ,
    )
    is_source_person =binding .origin =="source_person"
    context =_with_identity_block (self ,binding ,entity ,demographic_slot ,context )

    if use_llm :
    # Use LLM to generate detailed persona. Fuer eine Quellperson ist der
    # gewuerfelte Slot keine Vorgabe: das Modell bekommt keinen Slot, und
    # die Antwort wird nicht damit ueberschrieben.
        profile_data =self ._generate_profile_with_llm (
        entity_name =name ,
        entity_type =entity_type ,
        entity_summary =entity .summary ,
        entity_attributes =entity .attributes ,
        context =context ,
        demographic_slot =None if is_source_person else demographic_slot ,
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
    persona_kind ="collective"if is_collective else "individual"
    answer_from_model =use_llm and profile_data .get ("generation_source","llm")!="rule_based"

    if is_collective :
        profile_data ["age"]=None
        profile_data ["gender"]=None
        profile_data ["mbti"]=None
        # Eine Kollektiv-Persona hat keinen Beruf. "Dozent und
        # Betriebsratsmitglied" war aus einem Bildungstraeger nicht
        # ableitbar, sondern eine plausible Vita.
        profile_data ["profession"]=None
    elif is_source_person :
        _apply_source_person_demographics (profile_data ,binding ,entity .attributes ,demographic_slot )
    elif demographic_slot is not None :
        profile_data ["age"]=demographic_slot .age
        profile_data ["gender"]=demographic_slot .gender
        profile_data ["mbti"]=demographic_slot .mbti
    _apply_documented_demographics (profile_data ,entity .attributes ,is_collective )
    if is_source_person :
        _apply_source_person_text (profile_data ,binding ,entity ,answer_from_model )

        # LLM/Rule-based darf display_name (echter Name) + handle (kurzes Social-Handle)
        # überschreiben. So wird aus Entity "GraphRAG" z.B. Person "Lena Hoffmann" mit
        # Handle "lena_hoffmann". Fuer Kollektive bleibt der Entitaetsname stehen:
        # der Traeger spricht als Traeger, nicht als erfundener Mitarbeiter.
        # Issue #1833: Eine Quellperson behaelt ihren Quellnamen.
    if not is_collective and not binding .name_is_locked :
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
    # Eine Quellperson auf dem regelbasierten Weg traegt nur Quellentext;
    # die Kohaerenzpruefung braucht dort keinen weiteren Modellaufruf.
    use_llm =use_llm and (answer_from_model or not is_source_person ),
    )
    profession =resolution .profession
    bio =resolution .bio
    persona_text =resolution .persona_text
    if is_source_person and binding .function_evidence =="attribute":
    # Die belegte Funktion ist der Beruf; eine Drift-Korrektur aendert das nicht.
        profession =binding .documented_function
    if not is_collective :
    # Die Korrektur kann den Eroeffnungsnamen des Freitexts veraendern;
    # dieselbe Angleichung wie bei der Erstgenerierung, idempotent wenn
    # sich nichts geaendert hat.
        persona_text =self ._align_persona_identity (persona_text ,name )
        # Issue #1759 (A2): grammatisches Gender der Berufsbezeichnung
        # (Chefaerztin/Chefarzt) schlaegt den gewuerfelten Slot-Wert; ein
        # im Dokument belegtes Geschlecht bleibt unangetastet.
        _apply_role_gender (profile_data ,entity .attributes ,profession ,bio )
    if is_source_person :
    # Zuletzt, mit endgueltigem Beruf und endgueltiger Bio: dieselben Eingaben
    # wie die Batch-Pruefung der Rollenplausibilitaet.
        profile_data ["age"]=_source_person_age (
        entity .attributes ,profile_data ,demographic_slot ,answer_from_model ,profession ,bio
        )
    generation_error =_merge_generation_error (
    profile_data .get ("generation_error"),resolution .generation_error
    )
    _legacy .logger .info (
    "persona identity: type=%s origin=%s function_evidence=%s gender_evidence=%s unverifiable=%s",
    entity_type ,
    binding .origin ,
    binding .function_evidence ,
    binding .gender_evidence ,
    ",".join (binding .unverifiable_reasons )or "-",
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
    # Issue #1759 (A7): das Register folgt der Rolle, ein widersprechendes
    # Modell-Register wird ueberschrieben.
    voice_register =resolve_voice_register (
    profile_data .get ("voice_register"),entity_type ,profession ,
    is_collective =is_collective ,seed =name ,
    ),
    # Issue #1029: Default "llm" — nur der regelbasierte Pfad setzt
    # den Schlüssel, und er setzt ihn immer.
    generation_source =profile_data .get ("generation_source","llm"),
    generation_error =generation_error ,
    identity_binding =binding .model_dump (mode ="json"),
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
