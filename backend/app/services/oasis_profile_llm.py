"""Implementation helpers extracted from OasisProfileGenerator.

The public compatibility surface remains app.services.oasis_profile_generator.
"""

from __future__ import annotations

from typing import Any

from . import oasis_profile_generator as _legacy
import json
from typing import Dict, List, Optional
from .oasis_profile_models import CollectivePersonaSchema, PersonaDemographicSlot, PersonaProfileSchema
from .run_budget import BudgetExceededError
from .oasis_profile_generator import VOICE_REGISTERS

def _generate_profile_with_llm (
self: Any ,
entity_name :str ,
entity_type :str ,
entity_summary :str ,
entity_attributes :Dict [str ,Any ],
context :str ,
demographic_slot :Optional [PersonaDemographicSlot ]=None ,
)->Dict [str ,Any ]:
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
    is_individual =not self ._is_group_entity (entity_type )
    detail_level =_legacy ._resolve_persona_detail_level ()
    max_tokens =detail_level ['max_tokens']

    if is_individual :
        prompt =self ._build_individual_persona_prompt (
        entity_name ,entity_type ,entity_summary ,entity_attributes ,context ,
        detail_level =detail_level ,demographic_slot =demographic_slot ,
        )
    else :
        prompt =self ._build_group_persona_prompt (
        entity_name ,entity_type ,entity_summary ,entity_attributes ,context ,
        detail_level =detail_level ,demographic_slot =demographic_slot ,
        )

        # Issue #1247: Einmal angehaengt statt in beide Prompts kopiert — es ist
        # dieselbe Frage, unabhaengig davon, ob die Entitaet als Individuum oder
        # als Kollektiv gefuehrt wird.
    prompt =f"{prompt }\n\n{self ._build_eligibility_prompt_block (entity_name ,entity_type )}"

    # Try multiple times until successful or max retry attempts reached
    max_attempts =3 
    last_error =None 

    # LLMClient statt rohem OpenAI-Client: kapselt Provider-Detection
    # (MiniMax-thinking-extra_body), strict json_schema-Mode und zentrale
    # JSON-Repair-Logik. force_no_thinking=True deaktiviert M3-Reasoning,
    # das ohne diese Verdrahtung bis zu 63 % des Token-Budgets als
    # lesbaren Text in den content emittiert → kaputtes JSON → Retry-Loop.
    from ..llm .client import LLMClient as _LLMClient 

    llm =_LLMClient (
    api_key =self .api_key ,
    base_url =self .base_url ,
    model =self .model_name ,
    # Budget-Enforcement (#984): ohne run_id gibt es keinen Enforcer —
    # Persona-Generierung liefe am harten Run-Budget vorbei.
    run_id =self .run_id ,
    # Issue #1418: ohne provider_type erkennt LLMClient codex_cli
    # nicht als Subprozess-Provider und versucht einen HTTP-Call.
    provider_type =self .provider_type ,
    )
    messages =[
    {"role":"system","content":self ._get_system_prompt (is_individual )},
    {"role":"user","content":prompt },
    ]

    for attempt in range (max_attempts ):
        try :
        # Strict-json_schema-Mode + force_no_thinking: M3 liefert
        # gültiges JSON nach Schema, ohne Reasoning-Text im content.
            result =llm .chat_json (
            messages =messages ,
            temperature =0.7 -(attempt *0.1 ),
            max_tokens =max_tokens ,
            # Issue #1246: Der Kollektiv-Prompt fordert die
            # Personenfelder nicht an — mit dem Individuen-Schema
            # scheiterte jede Gruppen-Entitaet dreimal und fiel auf
            # den regelbasierten Pfad zurueck.
            schema =PersonaProfileSchema if is_individual else CollectivePersonaSchema ,
            schema_name ="persona_profile"if is_individual else "collective_persona",
            context ="persona",
            force_no_thinking =True ,
            )

            # chat_json validiert bereits gegen das Pydantic-Schema; die
            # nachfolgenden Fallbacks (bio, persona, voice_register)
            # bleiben als Defensive-Programmierung bestehen.
            if demographic_slot is not None :
                result ["age"]=demographic_slot .age 
                result ["gender"]=demographic_slot .gender 
                result ["mbti"]=demographic_slot .mbti 
            if not result .get ("bio"):
                result ["bio"]=entity_summary [:200 ]if entity_summary else f"{entity_type }: {entity_name }"
            if not result .get ("persona"):
                result ["persona"]=entity_summary or f"{entity_name } is a {entity_type }."

                # voice_register: Fallback vor allgemeiner Validation (kein Retry nötig)
            vr_value =result .get ("voice_register")
            if vr_value not in VOICE_REGISTERS :
                _legacy .logger .warning (
                "voice_register fehlt oder ungültig: %r → fallback neutral-de",vr_value 
                )
                result ["voice_register"]="neutral-de"

            missing_fields =self ._validate_profile_metadata (
            result ,is_collective =not is_individual 
            )
            if missing_fields :
                last_error =ValueError (
                f"Missing required persona metadata: {', '.join (missing_fields )}"
                )
                _legacy .logger .warning (
                f"LLM persona missing required metadata (attempt {attempt +1 }): "
                f"{', '.join (missing_fields )}"
                )
                continue 

            return result 

        except BudgetExceededError :
        # Codex-Finding P2 auf PR #1461: ein hartes Budget muss
        # durchschlagen. Ohne diese Klausel faengt der breite Handler
        # darunter ``BudgetExceededError`` ab, schlaeft drei Versuche
        # lang und liefert am Ende ein regelbasiertes Profil.
        # Bei erschoepftem Budget haette eine 30-Personen-Vorbereitung
        # so rund 180 Sekunden mit garantiert abgelehnten Calls
        # verbracht und die Stufe ohne Budget-Abbruch verlassen.
            raise 
        except Exception as e :# noqa: BLE001 — exception is logged; swallowed intentionally
            _legacy .logger .warning (f"LLM call failed (attempt {attempt +1 }): {str (e )[:80 ]}")
            last_error =e 
            import time 
            time .sleep (1 *(attempt +1 ))# Exponential backoff

    _legacy .logger .warning (f"LLM persona generation failed ({max_attempts } attempts): {last_error }, using rule-based generation")
    # Issue #1029: Der Ausfall wandert mit ins Profil. Ohne ihn ist ein
    # Platzhalterprofil nach dem Erzeugungszeitpunkt nicht mehr von
    # einem echten zu unterscheiden.
    return self ._generate_profile_rule_based (
    entity_name ,
    entity_type ,
    entity_summary ,
    entity_attributes ,
    generation_error =(
    f"LLM-Generierung nach {max_attempts } Versuchen fehlgeschlagen: "
    f"{str (last_error )[:160 ]}"
    ),
    )


def _validate_profile_metadata (
self: Any ,result :Dict [str ,Any ],*,is_collective :bool =False 
)->List [str ]:
    """Validate and normalize structured fields that OASIS actually consumes.

    Issue #1246 (CodeRabbit PR #1257): Fuer Kollektive pruefen nur die
    Felder, die eine Organisation ueberhaupt haben kann. Alter, Geschlecht,
    MBTI und Berufsbezeichnung als fehlend zu melden hiesse, eine
    vollstaendige Antwort dreimal zu verwerfen und auf den regelbasierten
    Pfad zu fallen — dieselbe Falle wie beim Schema.
    """
    missing_fields =[]

    if is_collective :
        country =result .get ("country")
        if not isinstance (country ,str )or not country .strip ():
            missing_fields .append ("country")
        register =result .get ("voice_register")
        if not isinstance (register ,str )or register .strip ()not in VOICE_REGISTERS :
            missing_fields .append ("voice_register")
        return missing_fields 

    age =result .get ("age")
    if isinstance (age ,str )and age .strip ().isdigit ():
        age =int (age .strip ())
        result ["age"]=age 
    if not isinstance (age ,int )or age <18 or age >75 :
        missing_fields .append ("age")

    gender =result .get ("gender")
    if isinstance (gender ,str ):
        normalized_gender =gender .strip ().lower ()
        if normalized_gender in self .VALID_PROFILE_GENDERS :
            result ["gender"]=normalized_gender 
        else :
            missing_fields .append ("gender")
    else :
        missing_fields .append ("gender")

    mbti =result .get ("mbti")
    if isinstance (mbti ,str ):
        normalized_mbti =mbti .strip ().upper ()
        if normalized_mbti in self .MBTI_TYPES :
            result ["mbti"]=normalized_mbti 
        else :
            missing_fields .append ("mbti")
    else :
        missing_fields .append ("mbti")

    country =result .get ("country")
    if isinstance (country ,str )and country .strip ():
        country_map ={
        "germany":"DE",
        "deutschland":"DE",
        "united states":"US",
        "usa":"US",
        }
        country_value =country .strip ()
        result ["country"]=country_map .get (country_value .lower (),country_value .upper ())
    else :
        missing_fields .append ("country")

    vr =result .get ("voice_register")
    if vr is not None and vr not in VOICE_REGISTERS :
        missing_fields .append (f"voice_register: invalid value '{vr }'")

    return missing_fields


def _try_fix_json (self: Any ,content :str ,entity_name :str ,entity_type :str ,entity_summary :str ="")->Dict [str ,Any ]:
    """Try to fix corrupted JSON"""
    import re 

    # 1. First try to fix truncated case via the centralized repair helper
    # (Issue #869). Returns the repaired payload or None when no
    # structural recovery is possible — in which case we keep the
    # original content and let the regex/json.loads fallbacks below
    # attempt their own recovery (newline sanitization, partial-field
    # extraction, etc.).
    repaired =_legacy ._try_repair_truncated_json (content )
    if repaired is not None :
        content =repaired 

        # 2. Try to extract JSON portion
    json_match =re .search (r'\{[\s\S]*\}',content )
    if json_match :
        json_str =json_match .group ()

        # 3. Handle newline issues in strings
        # Find all string values and replace newlines
        def fix_string_newlines (match ):
            s =match .group (0 )
            # Replace actual newlines in string with spaces
            s =s .replace ('\n',' ').replace ('\r',' ')
            # Replace excess spaces
            s =re .sub (r'\s+',' ',s )
            return s 

            # Match JSON string values
        json_str =re .sub (r'"[^"\\]*(?:\\.[^"\\]*)*"',fix_string_newlines ,json_str )

        # 4. Try to parse
        try :
            result =json .loads (json_str )
            result ["_fixed"]=True 
            return result 
        except json .JSONDecodeError :
        # 5. If still failed, try more aggressive fix
            try :
            # Remove all control characters
                json_str =re .sub (r'[\x00-\x1f\x7f-\x9f]',' ',json_str )
                # Replace all consecutive whitespace
                json_str =re .sub (r'\s+',' ',json_str )
                result =json .loads (json_str )
                result ["_fixed"]=True 
                return result 
            except (json .JSONDecodeError ,ValueError ,TypeError ):
                pass 

                # 6. Try to extract partial information from content
    bio_match =re .search (r'"bio"\s*:\s*"([^"]*)"',content )
    persona_match =re .search (r'"persona"\s*:\s*"([^"]*)',content )# May be truncated

    bio =bio_match .group (1 )if bio_match else (entity_summary [:200 ]if entity_summary else f"{entity_type }: {entity_name }")
    persona =persona_match .group (1 )if persona_match else (entity_summary or f"{entity_name } is a {entity_type }.")

    # If extracted meaningful content, mark as fixed
    if bio_match or persona_match :
        _legacy .logger .info ("Extracted partial information from corrupted JSON")
        return {
        "bio":bio ,
        "persona":persona ,
        "_fixed":True 
        }

        # 7. Complete failure, return basic structure
    _legacy .logger .warning ("JSON fix failed, returning basic structure")
    return {
    "bio":entity_summary [:200 ]if entity_summary else f"{entity_type }: {entity_name }",
    "persona":entity_summary or f"{entity_name } is a {entity_type }."
    }
