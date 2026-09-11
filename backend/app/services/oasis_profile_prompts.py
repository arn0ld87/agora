"""Implementation helpers extracted from OasisProfileGenerator.

The public compatibility surface remains app.services.oasis_profile_generator.
"""

from __future__ import annotations

from typing import Any

from . import oasis_profile_generator as _legacy
import json
from typing import Dict, Optional
from .oasis_profile_models import PersonaDemographicSlot
from .persona_demographics import build_name_quota_prompt_block, build_name_quota_prompt_block_en
from .persona_quota_defaults import build_industry_quota_prompt_block, build_industry_quota_prompt_block_en

def _get_system_prompt (self: Any ,is_individual :bool )->str :
    """Get system prompt — language-aware (de/en)."""
    if self .language =="de":
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


def _build_individual_persona_prompt (
    self: Any ,
    entity_name :str ,
    entity_type :str ,
    entity_summary :str ,
    entity_attributes :Dict [str ,Any ],
    context :str ,
    detail_level :Optional [dict ]=None ,
    demographic_slot :Optional [PersonaDemographicSlot ]=None ,
    )->str :
        """Build detailed persona prompt for individual entities — language-aware."""

        detail =detail_level if detail_level is not None else _legacy ._resolve_persona_detail_level ()
        attrs_str =json .dumps (entity_attributes ,ensure_ascii =False )if entity_attributes else "Keine"
        context_str =context [:detail ['context_limit']]if context else "Keine zusätzlichen Informationen"

        _quota_block_de =build_name_quota_prompt_block ()
        _industry_block_de =build_industry_quota_prompt_block (self ._industry_quota_plan )
        _slot_block =(
        self ._build_demographic_slot_prompt_block (demographic_slot )
        if demographic_slot is not None 
        else ""
        )

        if self .language =="de":
            return f"""Erzeuge eine detaillierte Social-Media-Persona für die folgende Entität. Bleibe nah an der bekannten Realität.

Name der Entität: {entity_name }
Typ: {entity_type }
Zusammenfassung: {entity_summary }
Attribute: {attrs_str }

Kontext:
{context_str }

{_quota_block_de }

{_industry_block_de }

{_slot_block }

Antworte als JSON mit folgenden Feldern:

1. display_name: Echter Vor- und Nachname einer Person im DACH-Raum — entsprechend der obigen Namensverteilung. WICHTIG: Nur dann den tatsächlichen Namen einer realen Person nehmen, wenn "{entity_name }" selbst bereits ein Personenname ist UND diese Person in der Realität so heißt. Bei Rollen ("IT-Umschüler"), Themen ("GraphRAG"), Produkten ("Agora") oder Berufsbezeichnungen IMMER einen anderen, frei gewählten Namen nehmen — nicht den Namen einer im Kontext erwähnten Person übernehmen. Jede Persona soll einen EIGENEN Namen haben.
2. handle: Kurzes Social-Media-Handle in Kleinbuchstaben ohne Leerzeichen (z. B. "lena_hoffmann" oder "marcelschmitz"). Keine Zahlen anhängen — das passiert später.
3. bio: Social-Media-Bio, max. 200 Zeichen, auf Deutsch.
4. persona: Ausführliche Personenbeschreibung ({detail ['word_count_de']}, durchgehend Fließtext, auf Deutsch). Enthalten muss sein:
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
8. country: ISO-Land in Englisch (z. B. "DE", "AT", "CH")
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

        _quota_block_en =build_name_quota_prompt_block_en ()
        _industry_block_en =build_industry_quota_prompt_block_en (self ._industry_quota_plan )

        return f"""Generate a detailed social media user persona for the entity, maximizing restoration of existing reality.

Entity Name: {entity_name }
Entity Type: {entity_type }
Entity Summary: {entity_summary }
Entity Attributes: {attrs_str }

Context Information:
{context_str }

{_quota_block_en }

{_industry_block_en }

{_slot_block }

Please generate JSON containing the following fields:

1. display_name: Realistic first + last name of a person — following the name distribution above (DACH Mikrozensus 2024). IMPORTANT: Only use a real person's actual name if "{entity_name }" itself IS a personal name AND matches reality. For roles, topics, products, or job titles ALWAYS pick a different, freshly chosen name — do NOT reuse names of people mentioned in the context. Every persona must have its own unique name.
2. handle: Short lowercase social handle without spaces (e.g. "lena_hoffmann"). Do not append digits.
3. bio: Social media bio, 200 characters
4. persona: Detailed persona description ({detail ['word_count_en']} of pure text), must include:
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
8. country: Country ISO code (e.g., "DE", "AT", "CH")
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


def _build_group_persona_prompt (
    self: Any ,
    entity_name :str ,
    entity_type :str ,
    entity_summary :str ,
    entity_attributes :Dict [str ,Any ],
    context :str ,
    detail_level :Optional [dict ]=None ,
    demographic_slot :Optional [PersonaDemographicSlot ]=None ,
    )->str :
        """Build the collective persona prompt for group/institutional entities.

        Issue #1246: Dieser Prompt forderte bis zu diesem Slice einen erfundenen
        **Menschen** als Repraesentant der Organisation an — mit Alter,
        Geschlecht, MBTI-Typ, Bildungsweg und "praegenden Erfahrungen". Eine
        gGmbH hat davon nichts. Der Generator musste all das erfinden, und
        genau so entstand aus dem Bildungstraeger "Nordharz Bildungswerk gGmbH"
        ein "Juergen Hartmann, 57, Dozent fuer IT-Umschulungen und
        Betriebsratsmitglied" — weder "Dozent" noch "Betriebsratsmitglied" war
        aus der Quellentitaet ableitbar.

        Der Prompt beschreibt jetzt das Kollektiv selbst: Auftrag, Interessen,
        Positionen, Kommunikationsstil. Eine Kollektiv-Persona hat keine Vita,
        also nichts, was erfunden werden koennte. Der Demografie-Slot wird
        bewusst nicht eingespielt.

        Das ist eine Darstellungs-, keine Architekturaenderung: Der
        Simulations-Agent bleibt ein Agent und fuehrt weiterhin individuelle
        Aktionen aus. Was sich aendert, ist die Selbstbeschreibung.
        """

        detail =detail_level if detail_level is not None else _legacy ._resolve_persona_detail_level ()
        attrs_str =json .dumps (entity_attributes ,ensure_ascii =False )if entity_attributes else "Keine"
        context_str =context [:detail ['context_limit']]if context else "Keine zusätzlichen Informationen"

        if self .language =="de":
            return f"""Beschreibe die folgende Organisation / Gruppe als **kollektive Stimme** im Szenario. Sie äußert sich als Organisation — nicht als erfundene Einzelperson. Erfinde KEINE Person, KEINEN Namen, KEINEN Lebenslauf.

Organisation/Gruppe: {entity_name }
Typ: {entity_type }
Zusammenfassung: {entity_summary }
Attribute: {attrs_str }

Kontext:
{context_str }

Antworte als JSON mit folgenden Feldern:

1. bio: Kurzbeschreibung der Organisation, max. 200 Zeichen, Deutsch. Was sie ist und wofür sie steht.
2. persona: Ausführliche Beschreibung der Organisation ({detail ['word_count_de']}, Fließtext, Deutsch). Enthalten:
   - Auftrag und Zuständigkeit (wofür ist sie da, woran wird sie gemessen)
   - Verhältnis zum Szenario (was betrifft sie daran konkret)
   - Interessenlage (was gewinnt sie, was verliert sie)
   - Bekannte Positionen und typische Argumentationslinien
   - Kommunikationsverhalten (wie äußert sie sich öffentlich, wie förmlich, wie schnell)
   - Konfliktlinien zu anderen Beteiligten
   Schreibe durchgehend über die Organisation ("Der Träger…", "Die Kammer…"), nie über eine Einzelperson.
3. country: ISO-Land in Englisch (z. B. "DE", "AT", "CH")
4. interested_topics: Array deutscher Themen-Strings
5. voice_register: Genau einer von "formal-de" | "neutral-de" | "technical-de" | "skeptisch-de".
    Passend zu Auftrag und Kontext von "{entity_name }":
    - "formal-de": gehoben, Sie-Form, Behörden-/Konzern-Ton, keine Anglizismen.
    - "neutral-de": alltagssprachlich, Du-Form möglich, keine Werbesprache.
    - "technical-de": präzise, Fachvokabular, knapp, kein Marketing.
    - "skeptisch-de": kritisch-distanziert, hinterfragend, Anführungszeichen für Buzzwords.

Wichtig:
- Antworte ausschließlich mit JSON.
- Texte auf Deutsch.
- Keine unescapten Zeilenumbrüche.
- KEIN Alter, KEIN Geschlecht, KEIN MBTI-Typ, KEINE Berufsbezeichnung — eine Organisation hat davon nichts.
- KEIN erfundener Personenname. Die Organisation spricht unter ihrem eigenen Namen.
- voice_register MUSS eines der vier exakten Werte sein.
"""

        return f"""Describe the following organization/group as a **collective voice** in the scenario. It speaks as an organization — not as an invented individual. Do NOT invent a person, a name, or a biography.

Organization/Group: {entity_name }
Entity Type: {entity_type }
Entity Summary: {entity_summary }
Entity Attributes: {attrs_str }

Context Information:
{context_str }

Please generate JSON containing the following fields:

1. bio: Short description of the organization, 200 characters. What it is and what it stands for.
2. persona: Detailed description of the organization ({detail ['word_count_en']} of pure text), must include:
   - Mandate and remit (what it exists for, what it is measured on)
   - Relationship to the scenario (what concretely affects it)
   - Interests (what it stands to gain or lose)
   - Known positions and typical lines of argument
   - Communication behaviour (how it speaks publicly, how formal, how fast)
   - Lines of conflict with other participants
   Write throughout about the organization, never about an individual.
3. country: Country ISO code (e.g., "DE", "AT", "CH")
4. interested_topics: Array of topics
5. voice_register: Exactly one of "formal-de" | "neutral-de" | "technical-de" | "skeptisch-de".
    Choose based on the mandate of "{entity_name }":
    - "formal-de": elevated style, formal address, bureaucratic tone, no anglicisms.
    - "neutral-de": everyday language, casual address, no marketing speak.
    - "technical-de": precise, specialist vocabulary, concise, no marketing.
    - "skeptisch-de": critical, questioning, uses quotation marks for buzzwords.

Important:
- All field values must be strings or arrays, no null values allowed
- NO age, NO gender, NO MBTI type, NO profession — an organization has none of these.
- NO invented personal name. The organization speaks under its own name.
- persona must be coherent, no newlines.
- voice_register MUST be one of the four exact values listed above.
- Use English."""
