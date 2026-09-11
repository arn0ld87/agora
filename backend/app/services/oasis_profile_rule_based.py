"""Implementation helpers extracted from OasisProfileGenerator.

The public compatibility surface remains app.services.oasis_profile_generator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from .degradation_collector import DegradationCollector
import random
from typing import Dict, List, Optional
from .oasis_profile_models import OasisAgentProfile, PersonaDemographicSlot
from ..contracts.pipeline_degradation_contract import DegradationKind, DegradationSeverity

def _rule_based_voice_register (entity_type :str ,profession :str ="")->str :
    """Minimale Heuristik: leite voice_register aus entity_type/profession ab."""
    combined =(entity_type +" "+profession ).lower ()
    if any (k in combined for k in ("beamt","jurist","lawyer","governmentagency","official","verwalt")):
        return "formal-de"
    if any (k in combined for k in ("develop","engineer","devops","software","tech","it_admin","faculty")):
        return "technical-de"
    if any (k in combined for k in ("activist","journalist","ngo","redakteur","aktivist")):
        return "skeptisch-de"
    return "neutral-de"


def _report_persona_degradation (
self: Any ,
profiles :List [Optional [OasisAgentProfile ]],
degradations :"DegradationCollector",
)->None :
    """Meldet Platzhalterprofile einmal für die ganze Runde (Issue #1029).

    Ein einzelner Fallback ist unauffällig; erst die Anzahl zeigt, ob
    die Runde überhaupt echte Stimmen hervorgebracht hat.

    Die Meldung hängt an ``generation_error``, nicht an
    ``generation_source``: Bei ``use_llm=False`` ist der regelbasierte
    Pfad die bewusste Wahl und keine Degradierung.
    """
    present =[p for p in profiles if p ]
    failed =[p for p in present if p .generation_error ]
    if not failed :
        return 

    first_error =failed [0 ].generation_error or "unbekannt"
    # Issue #1419: Faellt jede einzelne Persona aus, gibt es keine echte
    # Stimme mehr — die Runde koennte nur noch Platzhalter befragen. Das
    # ist kein Qualitaetsverlust, das ist ein leerer Lauf, und er darf
    # ``bereit`` nicht erreichen. Solange eine echte Persona dabei ist,
    # bleibt der Lauf verwertbar: die Platzhalter sind einzeln
    # gekennzeichnet, der Leser kann sie gewichten.
    severity =(
    DegradationSeverity .BLOCKING 
    if len (failed )==len (present )
    else DegradationSeverity .WARNING 
    )
    degradations .record (
    kind =DegradationKind .PERSONA_RULE_BASED_FALLBACK ,
    severity =severity ,
    detail =(
    f"{len (failed )} von {len (present )} Personas konnten nicht vom "
    "Modell erzeugt werden und sind regelbasierte Platzhalter. "
    "Ihre Beiträge tragen keine belastbaren Aussagen. "
    f"Erste Ursache: {first_error }"
    ),
    context ={
    "fallback_personas":len (failed ),
    "total_personas":len (present ),
    },
    )


def _generate_profile_rule_based (
self: Any ,
entity_name :str ,
entity_type :str ,
entity_summary :str ,
entity_attributes :Dict [str ,Any ],
generation_error :Optional [str ]=None ,
demographic_slot :Optional [PersonaDemographicSlot ]=None ,
)->Dict [str ,Any ]:
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
    payload =self ._build_rule_based_payload (
    entity_name ,entity_type ,entity_summary ,entity_attributes ,demographic_slot 
    )
    payload ["generation_source"]="rule_based"
    if generation_error :
        payload ["generation_error"]=generation_error 
    return payload


def _build_collective_payload (
self: Any ,
entity_name :str ,
entity_type :str ,
entity_summary :str ,
)->Dict [str ,Any ]:
    """Regelbasierte Kollektiv-Persona fuer Gruppen-Entitaeten (#1246).

    Bewusst eine eigene Methode und kein Zweig im Personen-Pfad: Alter,
    Geschlecht, Persoenlichkeitstyp und Beruf sind die vier Felder, die es
    an einer Institution nicht zu wissen gibt. Wer sie hier fuellt,
    erfindet — genau so wurde aus einem Bildungstraeger ein "Dozent und
    Betriebsratsmitglied".
    """
    return {
    "display_name":entity_name ,
    "handle":self ._generate_username (entity_name ),
    "bio":(entity_summary [:150 ]if entity_summary else entity_name ),
    "persona":(
    f"{entity_name } ist eine {entity_type }-Entität im Szenario und "
    f"äußert sich als Organisation, nicht als Einzelperson. "
    f"{entity_summary }"
    ).strip (),
    "age":None ,
    "gender":None ,
    "mbti":None ,
    "country":"DE",
    "profession":None ,
    "interested_topics":["Organisation","Positionen"],
    "voice_register":self ._rule_based_voice_register (entity_type .lower (),""),
    }


def _build_rule_based_payload (
self: Any ,
entity_name :str ,
entity_type :str ,
entity_summary :str ,
entity_attributes :Dict [str ,Any ],
demographic_slot :Optional [PersonaDemographicSlot ]=None ,
)->Dict [str ,Any ]:
    """Generate basic persona using rules"""

    # Generate different personas based on entity type
    entity_type_lower =entity_type .lower ()
    assigned_gender =(
    demographic_slot .gender if demographic_slot is not None else self ._pick_individual_gender ()
    )
    assigned_age =demographic_slot .age if demographic_slot is not None else None 
    assigned_mbti =demographic_slot .mbti if demographic_slot is not None else None 

    # Issue #1246: Kollektiv-Fallback. Sichtbar vor allen Personenzweigen,
    # damit eine Organisation gar nicht erst in einen Pfad geraet, der ihr
    # eine Vita andichtet.
    if self ._is_group_entity (entity_type_lower ):
        return self ._build_collective_payload (entity_name ,entity_type ,entity_summary )

        # Personen-Fallback: echter DACH-Name + breite Altersstreuung + realistisches Gender.
    if entity_type_lower in ["student","alumni"]:
        dach =self ._pick_dach_name (assigned_gender )
        return {
        "display_name":dach ,
        "handle":dach .lower ().replace (" ","_"),
        "bio":f"{entity_type } with interests in academics and social issues.",
        "persona":f"{dach } ist {entity_type .lower ()} und aktiv in akademischen und sozialen Diskussionen. Teilt Perspektiven und vernetzt sich mit Peers.",
        "age":assigned_age if assigned_age is not None else random .randint (18 ,32 ),
        "gender":assigned_gender ,
        "mbti":assigned_mbti or random .choice (self .MBTI_TYPES ),
        "country":"DE",
        "profession":"Student",
        "interested_topics":["Bildung","Gesellschaft","Technologie"],
        "voice_register":self ._rule_based_voice_register (entity_type_lower ,"Student"),
        }

    elif entity_type_lower in ["publicfigure","expert","faculty"]:
        dach =self ._pick_dach_name (assigned_gender )
        profession_str =entity_attributes .get ("occupation","Fachexpertin/Fachexperte")
        return {
        "display_name":dach ,
        "handle":dach .lower ().replace (" ","_"),
        "bio":"Expert and thought leader in their field.",
        "persona":f"{dach } ist eine anerkannte Fachperson und teilt Einschätzungen zu relevanten Themen. Bekannt für Expertise und Einfluss im öffentlichen Diskurs.",
        "age":assigned_age if assigned_age is not None else random .randint (32 ,68 ),
        "gender":assigned_gender ,
        "mbti":assigned_mbti or random .choice (["ENTJ","INTJ","ENTP","INTP"]),
        "country":"DE",
        "profession":profession_str ,
        "interested_topics":["Politik","Wirtschaft","Gesellschaft"],
        "voice_register":self ._rule_based_voice_register (entity_type_lower ,profession_str ),
        }

        # Institutionen-Fallback: ECHTE PERSON als Repräsentant/in der Organisation.
    elif entity_type_lower in ["mediaoutlet","socialmediaplatform"]:
        dach =self ._pick_dach_name (assigned_gender )
        return {
        "display_name":dach ,
        "handle":dach .lower ().replace (" ","_"),
        "bio":f"Redaktion bei {entity_name } | Nachrichten, Analysen, Einordnung",
        "persona":f"{dach } arbeitet als Redakteur:in bei {entity_name } und teilt berufliche Einschätzungen zu aktuellen Themen sowie gelegentlich persönliche Meinungen.",
        "age":assigned_age if assigned_age is not None else random .randint (28 ,58 ),
        "gender":assigned_gender ,
        "mbti":assigned_mbti or random .choice (self .MBTI_TYPES ),
        "country":"DE",
        "profession":f"Redakteur:in bei {entity_name }",
        "interested_topics":["Nachrichten","Aktuelles","Öffentlichkeit"],
        "voice_register":self ._rule_based_voice_register (entity_type_lower ,"journalist"),
        }

    elif entity_type_lower in ["university","governmentagency","ngo","organization"]:
        dach =self ._pick_dach_name (assigned_gender )
        return {
        "display_name":dach ,
        "handle":dach .lower ().replace (" ","_"),
        "bio":f"Mitarbeiter:in bei {entity_name } | spricht aus der Praxis",
        "persona":f"{dach } ist bei {entity_name } beschäftigt und vertritt die Organisation öffentlich — mal mit offizieller Position, mal mit persönlicher Sicht aus dem Arbeitsalltag.",
        "age":assigned_age if assigned_age is not None else random .randint (25 ,62 ),
        "gender":assigned_gender ,
        "mbti":assigned_mbti or random .choice (self .MBTI_TYPES ),
        "country":"DE",
        "profession":f"Mitarbeiter:in bei {entity_name }",
        "interested_topics":["Politik","Community","Arbeit"],
        "voice_register":self ._rule_based_voice_register (entity_type_lower ,""),
        }

    else :
        return self ._build_generic_person_payload (
        entity_name =entity_name ,
        entity_type =entity_type ,
        entity_summary =entity_summary ,
        assigned_gender =assigned_gender ,
        assigned_age =assigned_age ,
        assigned_mbti =assigned_mbti ,
        )


def _build_generic_person_payload (
self: Any ,
*,
entity_name :str ,
entity_type :str ,
entity_summary :str ,
assigned_gender :str ,
assigned_age :Optional [int ],
assigned_mbti :Optional [str ],
)->Dict [str ,Any ]:
    """Default-Pfad: Entitaet ohne eigenen Zweig wird Person mit breiter Streuung.

    Issue #1246: Zwei Defekte sassen hier. Der Personatext war die blanke
    ``entity_summary`` — ohne den Namen, unter dem die Persona auftritt; der
    Interview-Prompt setzte damit "Du bist Maria Martin" und eine
    Beschreibung zusammen, die niemanden benennt. Und ``profession`` trug
    den Entitaetstyp, was Berufsbezeichnungen wie "AIProvider" oder
    "WorkingGroup" ergab. Wo nichts abzuleiten ist, bleibt das Feld leer.
    """
    dach =self ._pick_dach_name (assigned_gender )
    persona =(
    f"{dach } steht im Szenario für „{entity_name }“. {entity_summary }".strip ()
    if entity_summary 
    else f"{dach } nimmt aktiv an sozialen Diskussionen teil."
    )
    return {
    "display_name":dach ,
    "handle":dach .lower ().replace (" ","_"),
    "bio":entity_summary [:150 ]if entity_summary else f"{entity_type }: {entity_name }",
    "persona":persona ,
    "age":assigned_age if assigned_age is not None else random .randint (20 ,70 ),
    "gender":assigned_gender ,
    "mbti":assigned_mbti or random .choice (self .MBTI_TYPES ),
    "country":"DE",
    "profession":None ,
    "interested_topics":["Allgemein","Gesellschaft"],
    "voice_register":self ._rule_based_voice_register (
    entity_type .lower (),entity_type 
    ),
    }
