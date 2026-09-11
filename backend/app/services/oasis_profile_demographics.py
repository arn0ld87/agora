"""Implementation helpers extracted from OasisProfileGenerator.

The public compatibility surface remains app.services.oasis_profile_generator.
"""

from __future__ import annotations

from typing import Any

import random
from typing import List, Optional
from .entity_reader import EntityNode
from .oasis_profile_models import PersonaDemographicSlot
from .persona_demographics import DACH_NAME_ORIGIN_QUOTAS, filter_first_names_for_gender

def _pick_dach_name (gender :Optional [str ]=None )->str :
    """Wählt einen Vor- und Nachnamen gewichtet nach DACH-Mikrozensus-Quoten.

    Nutzt DACH_NAME_ORIGIN_QUOTAS als Single Source of Truth statt eines
    statischen deutschen Namenspools.
    """
    weights =[q .share for q in DACH_NAME_ORIGIN_QUOTAS ]
    bucket =random .choices (DACH_NAME_ORIGIN_QUOTAS ,weights =weights ,k =1 )[0 ]
    first =random .choice (filter_first_names_for_gender (bucket .first_names ,gender ))
    last =random .choice (bucket .last_names )
    return f"{first } {last }"


def _last_name (name :str )->Optional [str ]:
    parts =(name or "").strip ().split ()
    if len (parts )<2 :
        return None 
    return parts [-1 ].lower ()


def _pick_individual_gender ()->str :
# ~47% male, ~47% female, ~6% nonbinary (statistisch grob realistisch, genug Varianz)
    return random .choices (["male","female","nonbinary"],weights =[47 ,47 ,6 ],k =1 )[0 ]


def _largest_remainder_counts (weighted_values :tuple [tuple [object ,float ],...],total :int )->list [int ]:
    raw =[share *total for _ ,share in weighted_values ]
    counts =[int (value )for value in raw ]
    remainder =total -sum (counts )
    ranked =sorted (
    ((raw [idx ]-counts [idx ],idx )for idx in range (len (weighted_values ))),
    reverse =True ,
    )
    for _ ,idx in ranked [:remainder ]:
        counts [idx ]+=1 
    return counts


def _build_weighted_slots (cls: Any ,weighted_values :tuple [tuple [str ,float ],...],total :int )->list [str ]:
    slots :list [str ]=[]
    for (value ,_share ),count in zip (
    weighted_values ,
    cls ._largest_remainder_counts (weighted_values ,total ),
    ):
        slots .extend ([value ]*count )
    random .shuffle (slots )
    return slots


def _build_age_slots (
cls: Any ,
weighted_bands :tuple [tuple [tuple [int ,int ],float ],...],
total :int ,
)->list [int ]:
    ages :list [int ]=[]
    for (age_range ,_share ),count in zip (
    weighted_bands ,
    cls ._largest_remainder_counts (weighted_bands ,total ),
    ):
        start ,end =age_range 
        band_ages =list (range (start ,end +1 ))
        random .shuffle (band_ages )
        ages .extend (band_ages [idx %len (band_ages )]for idx in range (count ))
    random .shuffle (ages )
    return ages


def _build_demographic_slots (self: Any ,entities :List [EntityNode ])->list [PersonaDemographicSlot ]:
    total =len (entities )
    if total ==0 :
        return []

    genders =self ._build_weighted_slots (self .PERSONA_GENDER_WEIGHTS ,total )
    mbtis =self ._build_weighted_slots (self .PERSONA_MBTI_WEIGHTS ,total )

    age_by_index :list [Optional [int ]]=[None ]*total 
    individual_indices :list [int ]=[]
    group_indices :list [int ]=[]
    for idx ,entity in enumerate (entities ):
        entity_type =entity .get_entity_type ()or "Entity"
        if self ._is_group_entity (entity_type ):
            group_indices .append (idx )
        else :
            individual_indices .append (idx )

    if individual_indices :
        for idx ,age in zip (
        individual_indices ,
        self ._build_age_slots (self .INDIVIDUAL_AGE_BANDS ,len (individual_indices )),
        ):
            age_by_index [idx ]=age 
    if group_indices :
        for idx ,age in zip (
        group_indices ,
        self ._build_age_slots (self .GROUP_AGE_BANDS ,len (group_indices )),
        ):
            age_by_index [idx ]=age 

    if any (age is None for age in age_by_index ):
        raise AssertionError ("Demographic slot planning left at least one age unassigned.")

    slots :list [PersonaDemographicSlot ]=[]
    for idx in range (total ):
        assigned_age =age_by_index [idx ]
        assert assigned_age is not None # guarded above; keeps the invariant explicit for type-checkers
        slots .append (
        PersonaDemographicSlot (
        age =assigned_age ,
        gender =genders [idx ],
        mbti =mbtis [idx ],
        )
        )
    return slots


def _build_demographic_slot_prompt_block (
self: Any ,
demographic_slot :PersonaDemographicSlot ,
)->str :
    if self .language =="de":
        return (
        "### Zugewiesener Demografie-Slot (verbindlich)\n"
        f"- age: exakt {demographic_slot .age }\n"
        f"- gender: exakt \"{demographic_slot .gender }\"\n"
        f"- mbti: exakt \"{demographic_slot .mbti }\"\n"
        "- Diese drei Felder sind vorgegeben und müssen unverändert ins JSON übernommen werden.\n"
        "- display_name muss zu diesem Gender passen."
        )
    return (
    "### Assigned demographic slot (mandatory)\n"
    f"- age: exactly {demographic_slot .age }\n"
    f"- gender: exactly \"{demographic_slot .gender }\"\n"
    f"- mbti: exactly \"{demographic_slot .mbti }\"\n"
    "- These three fields are fixed and must be copied into the JSON unchanged.\n"
    "- display_name must match this gender."
    )
