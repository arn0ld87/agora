"""
Persona-Contract v2 (Pydantic v2).

Code-verifiziert gegen:
- backend/app/services/oasis_profile_generator.py (OasisAgentProfile-Felder)

Ergänzt PersonaQuotaPlan, der heute fehlt — siehe ChatGPT-Audit
'Persona-Erzeugung ist nicht an Segment-Plan gebunden'.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


_STRICT = ConfigDict(extra="forbid")


#: Aktuelle Version des persistierten Persona-Formats (#1663). Der Personasatz
#: liegt als ``reddit_profiles.json`` (Liste) und ``twitter_profiles.csv`` vor.
#: Beide Formate liest OASIS direkt, eine Hülle um die Liste gibt es nicht.
#: Deshalb steht die Version an jedem Eintrag bzw. als eigene CSV-Spalte.
PERSONA_SCHEMA_VERSION: Literal[1] = 1


# DACH-Voice-Register (für Layer 2)
VoiceRegister = Literal["formal-de", "neutral-de", "technical-de", "skeptisch-de"]


class PersonaModel(BaseModel):
    """1:1-Spiegel von OasisAgentProfile, aber typsicher."""
    model_config = _STRICT

    # Issue #1663: Formatversion des persistierten Eintrags. Profile von vor
    # #1663 tragen das Feld nicht und gelten als Version 1. Eine unbekannte
    # Version wird abgelehnt, statt still als Version 1 durchzulaufen.
    schema_version: Literal[1] = PERSONA_SCHEMA_VERSION

    # Pflichtfelder aus OasisAgentProfile
    user_id: int = Field(ge=1)
    user_name: str = Field(min_length=3, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=3)
    bio: str = Field(min_length=10, max_length=200)
    persona: str = Field(min_length=300, max_length=12000)

    # Reddit/Twitter-spezifisch
    karma: int = Field(default=1000, ge=0)
    friend_count: int = Field(default=100, ge=0)
    follower_count: int = Field(default=150, ge=0)
    statuses_count: int = Field(default=500, ge=0)

    # Persona-Demografie
    age: Optional[int] = Field(default=None, ge=18, le=99)
    gender: Optional[Literal["male", "female", "nonbinary", "other"]] = None
    mbti: Optional[Literal[
        "INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP",
    ]] = None
    country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    profession: Optional[str] = None
    interested_topics: list[str] = Field(default_factory=list, max_length=15)

    # Quelle in Knowledge-Graph
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None

    # Issue #1713/#1470: Eine Person, die laut Graph-Relation (z. B.
    # WORKS_FOR/REPRESENTS, Vertreter/Sprecher/Leitung/Vorsitz) eine
    # Organisation vertritt, bleibt der Agent — die Organisation wird nicht
    # zusätzlich als eigener Agent geführt. ``affiliation`` traegt den
    # Organisationsnamen als Kontext, damit die Person nicht als "die
    # Organisation" spricht und Selbstreferenzen wie "wir, <Organisation>"
    # nicht als Rollenvertauschung (Role-Leakage) fehlklassifiziert werden.
    affiliation: Optional[str] = None

    # Issue #1246: "individual" oder "collective". Das Modell ist ein 1:1-
    # Spiegel von ``OasisAgentProfile`` und ``extra="forbid"`` — ohne dieses
    # Feld wuerde jedes serialisierte Profil, das ``persona_kind`` traegt, von
    # vertragspruefenden Konsumenten abgelehnt (CodeRabbit PR #1257).
    # Optional mit Default, damit Profile aus Laeufen vor diesem Slice
    # unveraendert validieren.
    persona_kind: Optional[Literal["individual", "collective"]] = "individual"

    # Review-Status (kommt aus persona_review_service.py)
    review_status: Optional[Literal["pending", "approved", "rejected"]] = None
    is_manual: Optional[bool] = False

    # Layer 2: DACH-Voice — Default neutral-de; None bleibt zulässig für alte Daten
    voice_register: Optional[VoiceRegister] = "neutral-de"

    # Layer 1: Segment-Zuordnung — neu, Pflicht ab Persona-Quoten-Vertrag
    segment: Optional[str] = Field(default=None, min_length=1, max_length=64)

    # Herkunft des Profils (Issue #1029). Regelbasierte Profile entstehen
    # entweder bewusst (use_llm=False) oder nach drei gescheiterten
    # LLM-Versuchen; sie nehmen regulär an der Simulation teil. Ohne dieses
    # Feld sind ihre Beiträge im Report nicht von denen echter Personas zu
    # unterscheiden, und die Oberfläche kann sie nicht kennzeichnen.
    #
    # Additiv mit Default: persistierte Personas von vor #1029 tragen es
    # nicht und validieren unverändert weiter — sie gelten als "llm",
    # was ihrem damaligen Regelfall entspricht.
    generation_source: Literal["llm", "rule_based"] = "llm"
    # Nur bei einem Ausfall gesetzt, nicht bei bewusst regelbasierter
    # Erzeugung.
    generation_error: Optional[str] = Field(default=None, max_length=200)


def persona_name_identity_reason(name: str, persona_text: str) -> Optional[str]:
    """Liefert den Ablehnungsgrund, wenn der Anzeigename im Freitext fehlt.

    Issue #1759 (A1): Der Generierungs-Dedup benannte kollidierende Profile
    um, ohne den ``persona``-Fließtext nachzuziehen — im Referenzlauf
    ``sim_3d3d8b2d8342`` hieß derselbe Agent im Handle ``valentina_ferrari_302``
    und im eigenen Profiltext ``Maren Hoffmann``. Der Interview-Prompt setzt
    beides zusammen, die Persona laeuft unter zwei Identitaeten.

    Diese Pruefung ist die letzte Verteidigungslinie NACH der
    Umbenennungs-Synchronisation im Generator: Taucht der Anzeigename
    (voll oder als Namensbestandteil ab drei Zeichen, case-insensitiv,
    wortgrenzgenau) nicht im Freitext auf, wird das Profil abgelehnt statt
    still durchgewunken. Kollektive nehmen nicht teil — sie sprechen als
    Träger, nicht als erfundene Person.

    Returns
    -------
    Optional[str]
        ``None``, wenn die Identitaet im Freitext wiedererkennbar ist
        (oder kein Anzeigename gesetzt ist), sonst ein Grund-String, der
        den Namen und den Befund traegt und im Prepare-Status sichtbar ist.
    """
    normalized = (name or "").strip().casefold()
    if not normalized:
        return None
    text_normalized = (persona_text or "").casefold()
    if re.search(rf"\b{re.escape(normalized)}\b", text_normalized):
        return None
    for part in normalized.split():
        if len(part) >= 3 and re.search(rf"\b{re.escape(part)}\b", text_normalized):
            return None
    return (
        f"Anzeigename '{name}' fehlt im persona-Freitext: Die simulierte "
        "Person wuerde unter zwei Namen laufen. Profil abgelehnt (#1759 A1)."
    )


#: Gesetzliche Regelaltersgrenze, ab der angestellte Rollen (Betriebsrat,
#: Klinikärzte, Sachbearbeitung) ohne Ruhestands-Hinweis nicht mehr plausibel
#: sind (Issue #1759, A2).
RETIREMENT_AGE = 65

_GenderName = Literal["male", "female"]

#: (Muster, Mindestalter) je Rolle. Greift auf Berufsbezeichnung oder Bio.
#: Werte sind bewusst konservativ: Facharztausbildung, Leitungslaufbahn.
_ROLE_MIN_AGE: tuple[tuple[re.Pattern[str], int], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), minimum)
    for pattern, minimum in (
        (r"chef(?:arzt|ärztin|aerztin)|ärztliche[rn]? direktor", 36),
        (r"ober(?:arzt|ärztin|aerztin)", 32),
        (r"fach(?:arzt|ärztin|aerztin)", 30),
        (r"klinikdirektor|verwaltungsdirektor|krankenhausdirektor", 35),
        (r"professor", 30),
        (r"landrat|landrätin", 30),
        (r"geschäftsführ|geschaeftsfuehr|vorstand", 28),
        (r"bürgermeister", 25),
    )
)

_EMPLOYEE_ROLE = re.compile(
    r"betriebsrat|personalrat|chef(?:arzt|ärztin|aerztin)|ober(?:arzt|ärztin|aerztin)"
    r"|fach(?:arzt|ärztin|aerztin)|sachbearbeit|pflegekraft|referent",
    re.IGNORECASE,
)
_RETIRED_MARKER = re.compile(
    r"pensionier|ruhestand|rentner|emerit|\ba\. ?d\.|retired|ehemalig|außer dienst",
    re.IGNORECASE,
)
_FEMALE_TITLE = re.compile(
    r"\w*(?:ärztin|aerztin|leiterin|direktorin|geschäftsführerin|bürgermeisterin"
    r"|sprecherin|professorin|landrätin|pflegerin)\b|\bhebamme\b|\bkrankenschwester\b",
    re.IGNORECASE,
)
_MALE_TITLE = re.compile(
    r"\w*(?:arzt|leiter|direktor|geschäftsführer|bürgermeister|sprecher|professor"
    r"|landrat|pfleger|vorsitzender)\b",
    re.IGNORECASE,
)
_GENDER_VALUES: dict[str, _GenderName] = {
    "male": "male", "männlich": "male", "maennlich": "male", "m": "male",
    "female": "female", "weiblich": "female", "w": "female", "f": "female",
}
_ATTRIBUTE_AGE_KEYS = ("age", "alter")
_ATTRIBUTE_GENDER_KEYS = ("gender", "geschlecht")


def documented_age(attributes: Optional[Mapping[str, Any]]) -> Optional[int]:
    """Im Dokument belegtes Alter (Graph-Attribut), sonst ``None`` (#1759 A2).

    Dokument-Belege haben Vorrang vor gewürfelten Slot-Werten.
    """
    for key in _ATTRIBUTE_AGE_KEYS:
        value = (attributes or {}).get(key)
        if isinstance(value, bool):
            continue
        try:
            age = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if 18 <= age <= 99:
            return age
    return None


def documented_gender(attributes: Optional[Mapping[str, Any]]) -> Optional[_GenderName]:
    """Im Dokument belegtes Geschlecht (``male``/``female``), sonst ``None``."""
    for key in _ATTRIBUTE_GENDER_KEYS:
        value = str((attributes or {}).get(key) or "").strip().casefold()
        if value in _GENDER_VALUES:
            return _GENDER_VALUES[value]
    return None


def gender_from_role_title(*texts: Optional[str]) -> Optional[_GenderName]:
    """Grammatisches Gender der Berufsbezeichnung, nur wenn eindeutig (A2).

    ``Chefärztin`` → ``female``, ``Chefarzt`` → ``male``. Trägt der Text beide
    Formen („Hebamme und Verbandssprecher“) oder keine, bleibt es bei ``None``
    — dann wird nicht korrigiert.
    """
    text = next((t for t in texts if t and t.strip()), "")
    female = bool(_FEMALE_TITLE.search(text))
    male = bool(_MALE_TITLE.search(_FEMALE_TITLE.sub(" ", text)))
    if female == male:
        return None
    return "female" if female else "male"


def role_corrected_gender(
    gender: Optional[str], profession: Optional[str], bio: Optional[str]
) -> Optional[str]:
    """Gender, korrigiert auf die Berufsbezeichnung, wenn diese eindeutig ist."""
    if gender is None:
        return None
    title_gender = gender_from_role_title(profession, bio)
    if title_gender is None or title_gender == gender:
        return gender
    return title_gender


def _role_min_age_reason(age: int, role_text: str) -> Optional[str]:
    for pattern, minimum in _ROLE_MIN_AGE:
        if pattern.search(role_text) and age < minimum:
            return f"Alter {age} liegt unter dem Mindestalter {minimum} für die Rolle"
    return None


def _retirement_reason(age: int, role_text: str) -> Optional[str]:
    if age < RETIREMENT_AGE or not _EMPLOYEE_ROLE.search(role_text):
        return None
    if _RETIRED_MARKER.search(role_text):
        return None
    return f"Alter {age} liegt im Rentenalter (ab {RETIREMENT_AGE}) für eine angestellte Rolle"


def persona_role_plausibility_reason(
    age: Optional[int], profession: Optional[str], bio: Optional[str]
) -> Optional[str]:
    """Ablehnungsgrund, wenn das Alter nicht zur Rolle passt (Issue #1759, A2).

    Referenzlauf ``sim_3d3d8b2d8342``: Chefärztin mit 28, Chefarzt mit 25,
    Betriebsratsvorsitzender mit 65 — das Alter kam aus einem rollenblind
    gewürfelten Slot. Geprüft werden Mindestalter für Leitungs- und
    Facharztrollen sowie das Rentenalter für angestellte Rollen.

    Returns
    -------
    Optional[str]
        ``None`` bei plausibler oder nicht prüfbarer Kombination (kein Alter,
        keine erkennbare Rolle), sonst ein Grund-String für den Prepare-Status.
    """
    if age is None:
        return None
    role_text = " ".join(part for part in (profession, bio) if part)
    reason = _role_min_age_reason(age, role_text) or _retirement_reason(age, role_text)
    if reason is None:
        return None
    return f"{reason} ('{(profession or bio or '').strip()[:80]}'). Profil abgelehnt (#1759 A2)."


class PersonaQuotaPlan(BaseModel):
    """
    Soll-Plan für Persona-Generation. Erzwingt exakte Counts pro Segment.
    Adressiert ChatGPT-Audit: 'Persona-Erzeugung ist nicht an Segment-Plan gebunden'.
    """
    model_config = _STRICT

    # z. B. {"kmu_ceo": 8, "it_admin": 6, ...}
    targets: dict[str, Annotated[int, Field(ge=1, le=200)]]
    total: int = Field(ge=1, le=500)

    @model_validator(mode="after")
    def total_matches_sum(self) -> "PersonaQuotaPlan":
        s = sum(self.targets.values())
        if s != self.total:
            raise ValueError(
                f"PersonaQuotaPlan.total={self.total} != sum(targets)={s}. "
                f"Soll-Plan ist inkonsistent."
            )
        return self


class PersonaQuotaActual(BaseModel):
    """Ist-Verteilung nach Generation. Wird gegen Plan validiert."""
    model_config = _STRICT

    plan: PersonaQuotaPlan
    actual_counts: dict[str, Annotated[int, Field(ge=0)]]
    tolerance: Annotated[int, Field(ge=0, le=10)] = 0  # default: exakt

    @model_validator(mode="after")
    def actual_within_tolerance(self) -> "PersonaQuotaActual":
        for segment, target in self.plan.targets.items():
            actual = self.actual_counts.get(segment, 0)
            if abs(actual - target) > self.tolerance:
                raise ValueError(
                    f"Segment '{segment}': Soll={target}, Ist={actual}, "
                    f"Toleranz={self.tolerance} überschritten."
                )
        # Keine unbekannten Segmente
        unknown = set(self.actual_counts) - set(self.plan.targets)
        if unknown:
            raise ValueError(
                f"Unbekannte Segmente in actual_counts: {sorted(unknown)}"
            )
        return self
