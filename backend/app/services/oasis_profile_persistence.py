"""Implementation helpers extracted from OasisProfileGenerator.

The public compatibility surface remains app.services.oasis_profile_generator.
"""

from __future__ import annotations

from typing import Any

from . import oasis_profile_generator as _legacy
from ..contracts.persona_contract import PERSONA_SCHEMA_VERSION
import csv
import json
from typing import Dict, List, Optional, Sequence
from .oasis_profile_models import OasisAgentProfile

def _print_generated_profile (self: Any ,entity_name :str ,entity_type :str ,profile :OasisAgentProfile ):
    """Log generated persona details at INFO level (visible in default log config)."""
    topics_str =', '.join (profile .interested_topics )if profile .interested_topics else 'None'
    _legacy .logger .info (
    "[Generated] %s (%s) → %s | age=%s gender=%s mbti=%s profession=%s topics=%s",
    entity_name ,
    entity_type ,
    profile .user_name ,
    profile .age ,
    profile .gender ,
    profile .mbti ,
    profile .profession ,
    topics_str ,
    )


def save_profiles (
self: Any ,
profiles :List [OasisAgentProfile ],
file_path :str ,
platform :str ="reddit"
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
    if platform =="twitter":
        self ._save_twitter_csv (profiles ,file_path )
    else :
        self ._save_reddit_json (profiles ,file_path )


#: Kopfzeile der Twitter-CSV, wie OASIS sie liest (``pd.read_csv``, Zugriff
#: ueber Spaltennamen; zusaetzliche Spalten stoeren dort nicht).
#: ``schema_version``: Issue #1663. ``voice_register``: Issue #1759 (A7), damit
#: der Parallel-Runner die Laengengrenze pro Register setzen kann.
#: ``source_user_id``: Issue #1778 — ``user_id`` ist die Zeilenposition (so
#: liest OASIS die CSV), ``source_user_id`` traegt die Nummer des Agenten in
#: der Simulationskonfiguration
#: (``simulation_agent_identity.align_config_to_profiles``).
TWITTER_CSV_HEADERS =['user_id','name','username','user_char','description','schema_version','voice_register','source_user_id']


def write_twitter_csv (
file_path :str ,
profiles :List [Dict [str ,Any ]],
extra_columns :Sequence [str ]=(),
)->None :
    """Schreibt ``twitter_profiles.csv`` im OASIS-Format.

    Einziger Schreiber dieses Formats: ``OasisProfileGenerator`` und der Pfad
    ``create-from-personas`` (``persona_prepare_service``) rufen beide hier
    hinein. ``profiles`` sind Dicts mit ``name``, ``username``, ``bio``,
    ``persona`` und optional ``voice_register``/``user_id``.

    - ``user_char``: bio + persona ohne Zeilenumbrueche (LLM-System-Prompt)
    - ``description``: bio ohne Zeilenumbrueche (oeffentliche Kurzvita)

    ``extra_columns`` haengt weitere Profilschluessel als Spalten an.
    """
    with open (file_path ,'w',newline ='',encoding ='utf-8')as f :
        writer =csv .writer (f )
        writer .writerow ([*TWITTER_CSV_HEADERS ,*extra_columns ])

        for idx ,profile in enumerate (profiles ):
            bio =profile .get ("bio")or ""
            persona =profile .get ("persona")
            user_char =bio
            if persona and persona !=bio :
                user_char =f"{bio } {persona }"
            user_char =user_char .replace ('\n',' ').replace ('\r',' ')
            description =bio .replace ('\n',' ').replace ('\r',' ')
            source_user_id =profile .get ("user_id")

            writer .writerow ([
            idx ,# user_id: Sequential ID starting from 0
            profile .get ("name"),
            profile .get ("username"),
            user_char ,
            description ,
            PERSONA_SCHEMA_VERSION ,
            profile .get ("voice_register")or "",
            source_user_id if source_user_id is not None else idx ,
            *[profile .get (column ,"")for column in extra_columns ],
            ])


def _save_twitter_csv (self: Any ,profiles :List [OasisAgentProfile ],file_path :str ):
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
    # Ensure file extension is .csv
    if not file_path .endswith ('.csv'):
        file_path =file_path .replace ('.json','.csv')

    write_twitter_csv (
    file_path ,
    [
    {
    "name":profile .name ,
    "username":profile .user_name ,
    "bio":profile .bio ,
    "persona":profile .persona ,
    "voice_register":profile .voice_register ,
    "user_id":profile .user_id ,
    }
    for profile in profiles
    ],
    )

    _legacy .logger .info (f"Saved {len (profiles )} Twitter profiles to {file_path } (OASIS CSV format)")


def _normalize_gender (self: Any ,gender :Optional [str ])->str :
    """
    Normalize gender field to OASIS required English format

    OASIS requires: male, female, other
    """
    if not gender :
        return "other"

    gender_lower =gender .lower ().strip ()

    # Gender mapping
    gender_map ={
    "male":"male",
    "female":"female",
    "other":"other",
    }

    return gender_map .get (gender_lower ,"other")


def _save_reddit_json (self: Any ,profiles :List [OasisAgentProfile ],file_path :str ):
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
    data =[]
    for idx ,profile in enumerate (profiles ):
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
        item =profile .to_reddit_format ()
        item .update ({
        "user_id":profile .user_id if profile .user_id is not None else idx ,
        "bio":profile .bio [:150 ]if profile .bio else f"{profile .name }",
        "persona":profile .persona or f"{profile .name } is a participant in social discussions.",
        "karma":profile .karma if profile .karma else 1000 ,
        "country":profile .country if profile .country else "US",
        })
        # Issue #1246 (CodeRabbit PR #1257): Die OASIS-Defaults gelten nur
        # fuer Individuen. Vorher fuellte dieser Block Alter, Geschlecht und
        # MBTI unbedingt auf — und schrieb damit genau die erfundene
        # Demografie zurueck in reddit_profiles.json, die der Kollektivzweig
        # entfernt. Die Realtime-Datei war korrekt, der finale Save
        # ueberschrieb sie. Persona-Galerie und Simulation lesen diese Datei.
        if profile .persona_kind !="collective":
            item .update ({
            "age":profile .age if profile .age else 30 ,
            "gender":self ._normalize_gender (profile .gender ),
            "mbti":profile .mbti if profile .mbti else "ISTJ",
            })

        data .append (item )

    with open (file_path ,'w',encoding ='utf-8')as f :
        json .dump (data ,f ,ensure_ascii =False ,indent =2 )

    _legacy .logger .info (f"Saved {len (profiles )} Reddit profiles to {file_path } (JSON format, includes user_id field)")


def save_profiles_to_json (
self: Any ,
profiles :List [OasisAgentProfile ],
file_path :str ,
platform :str ="reddit"
):
    """[Deprecated] Please use save_profiles() method"""
    _legacy .logger .warning ("save_profiles_to_json is deprecated, please use save_profiles method")
    self .save_profiles (profiles ,file_path ,platform )
