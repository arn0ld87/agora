"""Voice-Register an die Rolle koppeln, statt es dem Modell allein zu überlassen.

Issue #1759, Befund A7 („Alle Personas klingen gleich“). Im Referenzlauf trugen
60 Twitter-Kommentare im Schnitt 461 Zeichen, kein Ausrufezeichen und kein
emotionales Wort; ``voice_register`` kannte nur vier sachliche Register, und das
Modell wählte für fast jede Persona ``neutral-de``. Eine Patientin, die ihre
Geburtsstation verliert, schrieb wie ein Gutachter.

Die Zuordnung ist deshalb deterministisch und hängt an der Rolle:

========================  =====================================================
Rolle                     erlaubte Register (Default)
========================  =====================================================
``AFFECTED``              ``betroffen-de`` / ``emotional-de`` /
                          ``umgangssprachlich-de`` (nach Name gestreut)
``EXPERT``                ``technical-de``
``CRITICAL``              ``skeptisch-de`` / ``neutral-de`` (``skeptisch-de``)
``INSTITUTIONAL``         ``formal-de`` / ``neutral-de`` (``formal-de`` für
                          Behörden und Amtsträger, sonst ``neutral-de``)
``GENERAL``               alle sieben (``neutral-de``)
========================  =====================================================

Wer ein Kollektiv ist, entscheidet ausschließlich
:func:`persona_domain_coherence.is_collective_entity_type` bzw. das Ergebnis des
Aufrufers (``_is_group_entity``) — hier steht keine zweite Heuristik. Ein vom
Modell geliefertes Register, das außerhalb der erlaubten Menge der Rolle liegt,
wird überschrieben.
"""

from __future__ import annotations

import zlib
from enum import StrEnum
from typing import Dict, FrozenSet, Optional, Tuple

from ..contracts.persona_contract import VOICE_REGISTER_VALUES
from ..utils.logger import get_logger
from .persona_domain_coherence import is_collective_entity_type

logger = get_logger("agora.persona_voice_register")


class VoiceRole(StrEnum):
    """Sprecherrolle einer Persona, soweit sie das Register bestimmt."""

    AFFECTED = "affected"
    EXPERT = "expert"
    CRITICAL = "critical"
    INSTITUTIONAL = "institutional"
    GENERAL = "general"


#: Register der Betroffenen-Stimmen (Issue #1759, A7).
AFFECTED_REGISTERS: Tuple[str, ...] = ("betroffen-de", "emotional-de", "umgangssprachlich-de")

#: Schlüsselwörter, die direkt Betroffene und Privatpersonen kennzeichnen
#: (Teilstring-Treffer auf Typ + Beruf, casefold).
AFFECTED_KEYWORDS: Tuple[str, ...] = (
    "patient", "schwanger", "anwohner", "bewohner", "angehörig", "angehoerig",
    "eltern", "mutter", "vater", "betroffen", "beschäftigt", "beschaeftigt",
    "arbeitnehmer", "mieter", "rentner", "pflegebedürftig", "pflegebeduerftig",
    "versicherte", "bürger", "buerger", "employee", "citizen",
    "parent", "relative", "affected",
)

#: Amtsträger und Behörden: förmlicher Ton, auch wenn der Aufrufer sie als
#: Einzelperson führt.
OFFICIAL_KEYWORDS: Tuple[str, ...] = (
    "beamt", "jurist", "lawyer", "governmentagency", "official", "verwalt",
    "agency", "behörde", "behoerde", "authority", "ministeri", "ministry",
    "government", "regierung", "kommission", "commission", "parlament",
    "parliament", "bürgermeister", "buergermeister", "mayor", "landrat", "landrät",
    "landraet", "minister", "dezernent", "abgeordnet",
)

#: Fachrollen: präzise, knapp, ohne Gefühlsausdruck.
EXPERT_KEYWORDS: Tuple[str, ...] = (
    "develop", "entwickl", "engineer", "ingenieur", "devops", "software", "tech",
    "it_admin", "faculty", "expert", "wissenschaft", "researcher", "forscher",
    "analyst", "gutachter", "sachverständ", "sachverstaend", "ökonom",
    "oekonom", "economist", "professor",
)

#: Kritische Beobachter. ``ngo`` steht bewusst nicht hier: eine NGO ist ein
#: Kollektiv und bleibt förmlich/neutral.
CRITICAL_KEYWORDS: Tuple[str, ...] = (
    "activist", "aktivist", "journalist", "redakteur", "kritiker", "critic",
    "whistleblow",
)

#: Erlaubte Register je Rolle. ``GENERAL`` erlaubt jedes gültige Register.
ROLE_ALLOWED: Dict[VoiceRole, FrozenSet[str]] = {
    VoiceRole.AFFECTED: frozenset(AFFECTED_REGISTERS),
    VoiceRole.EXPERT: frozenset({"technical-de"}),
    VoiceRole.CRITICAL: frozenset({"skeptisch-de", "neutral-de"}),
    VoiceRole.INSTITUTIONAL: frozenset({"formal-de", "neutral-de"}),
    VoiceRole.GENERAL: frozenset(VOICE_REGISTER_VALUES),
}

_ROLE_DEFAULT: Dict[VoiceRole, str] = {
    VoiceRole.EXPERT: "technical-de",
    VoiceRole.CRITICAL: "skeptisch-de",
    VoiceRole.GENERAL: "neutral-de",
}


def _contains_any(text: str, keywords: Tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _keyword_role(text: str) -> Optional[VoiceRole]:
    """Rolle aus Schlüsselwörtern. Reihenfolge = Priorität (Amt vor Fach vor Kritik)."""
    if _contains_any(text, OFFICIAL_KEYWORDS):
        return VoiceRole.INSTITUTIONAL
    if _contains_any(text, EXPERT_KEYWORDS):
        return VoiceRole.EXPERT
    if _contains_any(text, CRITICAL_KEYWORDS):
        return VoiceRole.CRITICAL
    if _contains_any(text, AFFECTED_KEYWORDS):
        return VoiceRole.AFFECTED
    return None


def classify_voice_role(
    entity_type: str,
    profession: Optional[str] = None,
    *,
    is_collective: Optional[bool] = None,
) -> VoiceRole:
    """Ordnet eine Entität einer Sprecherrolle zu.

    ``is_collective`` übernimmt die Entscheidung des Aufrufers; ``None`` fragt
    die bestehende Kollektiv-Erkennung. Ein Kollektiv ohne Beruf ist immer
    ``INSTITUTIONAL``. Trägt ein Eintrag trotzdem einen Beruf (regelbasierter
    Pfad: Redakteurin einer ``MediaOutlet``), entscheidet der Beruf.
    """
    collective = is_collective_entity_type(entity_type) if is_collective is None else is_collective
    profession_text = (profession or "").strip()
    if collective and not profession_text:
        return VoiceRole.INSTITUTIONAL
    text = f"{entity_type} {profession_text}".casefold()
    role = _keyword_role(text)
    if role is not None:
        return role
    return VoiceRole.INSTITUTIONAL if collective else VoiceRole.GENERAL


def _spread(seed: str, choices: Tuple[str, ...]) -> str:
    """Stabile Streuung über ``choices``; ``crc32`` statt ``hash()`` (prozessfest)."""
    digest = zlib.crc32(seed.casefold().encode("utf-8"))
    return choices[digest % len(choices)]


def default_register_for_role(
    role: VoiceRole, entity_type: str = "", profession: Optional[str] = None, seed: str = ""
) -> str:
    """Deterministisches Register einer Rolle."""
    if role is VoiceRole.AFFECTED:
        return _spread(seed or f"{entity_type}|{profession or ''}", AFFECTED_REGISTERS)
    if role is VoiceRole.INSTITUTIONAL:
        text = f"{entity_type} {profession or ''}".casefold()
        return "formal-de" if _contains_any(text, OFFICIAL_KEYWORDS) else "neutral-de"
    return _ROLE_DEFAULT[role]


def resolve_voice_register(
    llm_register: Optional[str],
    entity_type: str,
    profession: Optional[str] = None,
    *,
    is_collective: Optional[bool] = None,
    seed: str = "",
) -> str:
    """Register einer Persona: das des Modells, sofern die Rolle es erlaubt.

    Fehlt das Register oder widerspricht es der Rolle (etwa ``neutral-de`` für
    eine Patientin, ``emotional-de`` für eine Behörde), gilt das Register der
    Rolle. Der Eingriff steht im Log, nicht in einer Degradation: das Register
    ist eine Stilvorgabe, kein Qualitätsverlust.
    """
    role = classify_voice_role(entity_type, profession, is_collective=is_collective)
    if llm_register in ROLE_ALLOWED[role]:
        return str(llm_register)
    resolved = default_register_for_role(role, entity_type, profession, seed)
    if llm_register is not None:
        logger.info(
            "voice_register %r widerspricht der Rolle %s (type=%s) -> %s",
            llm_register,
            role.value,
            entity_type,
            resolved,
        )
    return resolved


def rule_based_voice_register(entity_type: str, profession: Optional[str] = None, seed: str = "") -> str:
    """Register des regelbasierten Fallbacks — dieselbe Zuordnung wie beim LLM-Pfad."""
    return resolve_voice_register(None, entity_type, profession, seed=seed)


def role_hint_registers(entity_type: str) -> Tuple[str, ...]:
    """Register, die der Typ allein schon nahelegt (für den Prompt); sonst leer."""
    role = classify_voice_role(entity_type, None, is_collective=False)
    if role is VoiceRole.GENERAL:
        return ()
    return tuple(sorted(ROLE_ALLOWED[role]))


# ---------------------------------------------------------------------------
# Prompt-Bausteine
# ---------------------------------------------------------------------------

#: Wie jedes Register klingt: Satzlänge, Perspektive, Umgangssprache, Ausrufe.
REGISTER_STYLE_DE: Dict[str, str] = {
    "formal-de": (
        "gehoben, Sie-Form, Behörden-/Konzern-Ton, keine Anglizismen; lange, vollständige "
        "Sätze, Wir-/Dritte-Person-Perspektive, keine Ausrufezeichen "
        "(z. B. Beamtin, Juristin)."
    ),
    "neutral-de": (
        "alltagssprachlich, mittlere Satzlänge, sachlich-freundlich, keine Werbesprache, "
        "Ausrufe nur selten (z. B. Studierender, Sachbearbeiter)."
    ),
    "technical-de": (
        "präzise, Fachvokabular, knappe Sätze, kein Marketing, kaum Gefühlsausdruck "
        "(z. B. Senior-Entwicklerin, DevOps-Ingenieur)."
    ),
    "skeptisch-de": (
        "kritisch-distanziert, hinterfragend, Anführungszeichen für Buzzwords, rhetorische "
        "Fragen (z. B. Aktivistin, Journalist)."
    ),
    "betroffen-de": (
        "Ich-Perspektive, persönliche Betroffenheit, konkrete Alltagsfolgen (Wege, Zeit, "
        "Geld, Sorgen), kurze bis mittlere Sätze, offene Sorge statt Abwägung, Fragen "
        "erlaubt (z. B. Patientin, Schwangere, Anwohner, Angehörige, Beschäftigte)."
    ),
    "emotional-de": (
        "Gefühle offen ausgesprochen (Angst, Wut, Enttäuschung, Erleichterung), kurze Sätze, "
        "Ausrufe- und Fragezeichen erlaubt, Ich-Perspektive, kein „einerseits/andererseits“ "
        "(z. B. Mutter vor der Schließung, Pflegekraft in der Kündigungswelle)."
    ),
    "umgangssprachlich-de": (
        "Alltagssprache wie unter Nachbarn, Du-Form möglich, sehr kurze Sätze und "
        "Satzfragmente, Verkürzungen („ist halt so“, „krass“), Ausrufe erlaubt, keine "
        "Fachsprache (z. B. Anwohner, Schüler, Rentnerin)."
    ),
}

REGISTER_STYLE_EN: Dict[str, str] = {
    "formal-de": (
        "elevated style, formal address, bureaucratic tone, no anglicisms; long, complete "
        "sentences, we/third-person perspective, no exclamation marks (e.g. civil servant, lawyer)."
    ),
    "neutral-de": (
        "everyday language, medium sentence length, factual but friendly, no marketing "
        "speak, exclamations rarely (e.g. student, clerk)."
    ),
    "technical-de": (
        "precise, specialist vocabulary, short sentences, no marketing, little emotion "
        "(e.g. senior developer, DevOps engineer)."
    ),
    "skeptisch-de": (
        "critical, questioning, quotation marks for buzzwords, rhetorical questions "
        "(e.g. activist, journalist)."
    ),
    "betroffen-de": (
        "first person, personally affected, concrete everyday consequences (commute, time, "
        "money, worries), short to medium sentences, open worry instead of weighing, "
        "questions allowed (e.g. patient, expectant mother, neighbour, relative, employee)."
    ),
    "emotional-de": (
        "feelings said out loud (fear, anger, disappointment, relief), short sentences, "
        "exclamation and question marks allowed, first person, no 'on the one hand/on the "
        "other' (e.g. a mother facing the closure, a nurse in the layoff wave)."
    ),
    "umgangssprachlich-de": (
        "colloquial like between neighbours, informal address allowed, very short "
        "sentences and fragments, contractions and slang, exclamations allowed, no "
        "specialist language (e.g. neighbour, pupil, pensioner)."
    ),
}


def _style_for(language: str) -> Dict[str, str]:
    return REGISTER_STYLE_DE if language == "de" else REGISTER_STYLE_EN


def voice_register_prompt_block(
    language: str,
    entity_type: str = "",
    *,
    collective: bool = False,
    entity_name: str = "",
) -> str:
    """Prompt-Text für das Feld ``voice_register``: erlaubte Werte, Klang, Rollenhinweis.

    Kollektive sehen nur die Register, die ihre Rolle erlaubt; Individuen alle
    sieben, mit dem Hinweis, welche der Typ allein schon nahelegt.
    """
    allowed = ROLE_ALLOWED[VoiceRole.INSTITUTIONAL if collective else VoiceRole.GENERAL]
    registers = [r for r in VOICE_REGISTER_VALUES if r in allowed]
    styles = _style_for(language)
    choices = " | ".join(f'"{r}"' for r in registers)
    lines = "\n".join(f'    - "{r}": {styles[r]}' for r in registers)
    de = language == "de"
    if collective:
        intro = (
            f'Passend zu Auftrag und Kontext von "{entity_name}":'
            if de
            else f'Matching the mandate and context of "{entity_name}":'
        )
    else:
        intro = (
            "Wähle passend zu Rolle, Beruf und Betroffenheit der Persona. Direkt Betroffene "
            "und Privatpersonen sprechen NICHT im Gutachterton:"
            if de
            else "Choose to match the persona's role, profession and degree of being "
            "affected. People directly affected and private persons do NOT write like a "
            "report:"
        )
    block = f"{'Genau einer von' if de else 'Exactly one of'} {choices}.\n    {intro}\n{lines}"
    hint = () if collective else role_hint_registers(entity_type)
    if hint:
        hint_text = " | ".join(f'"{r}"' for r in hint)
        block += (
            f"\n    Für diesen Entitätstyp passend: {hint_text}."
            if de
            else f"\n    Suited to this entity type: {hint_text}."
        )
    return block
