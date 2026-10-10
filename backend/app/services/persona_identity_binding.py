"""Quellenidentität einer Persona (Issue #1833).

Die Identität, die eine Quelle einer Person oder einem Kollektiv gibt, hat
Vorrang vor Modellumbenennung und zufälliger Demografie. Dieses Modul löst die
Herkunft einer Entität deterministisch auf (:func:`resolve_identity_binding`),
rendert den Prompt-Baustein dafür (:func:`build_identity_prompt_block`) und
liefert den Text einer Quellperson ohne Modell
(:func:`source_person_fallback_fields`).

Alle Regeln sind deterministisch und ohne Namensliste. Eine Quellperson wird
nur gesperrt, wenn zur Namensform mindestens ein positives Personensignal aus
der Quelle kommt; die Form allein genügt bewusst nicht („Sozialer Dienst“).
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from typing import Any, Optional

from ..contracts.persona_contract import (
    documented_age,
    documented_gender,
    gender_from_role_title,
    has_retirement_marker,
    role_titles_in,
)
from ..contracts.persona_identity_contract import (
    FUNCTION_ATTRIBUTE_KEYS,
    IDENTITY_ORIGIN_ATTRIBUTE,
    MAX_FUNCTION_CHARS,
    SYNTHETIC_SUPPLEMENT_MARKER,
    FunctionEvidence,
    GenderEvidence,
    PersonaIdentityBinding,
    PersonaIdentityBindingEntry,
    PersonaIdentityBindingManifest,
    UnverifiableReason,
)
from ..utils.json_io import write_json_atomic
from .entity_semantic_class import SemanticEntityClass, classify_entity

#: Obergrenze für den in den Prompt eingesetzten Quellnamen (Größenordnung der
#: Funktionsgrenze). Der Name stammt aus einem nicht vertrauenswürdigen Dokument.
MAX_PROMPT_NAME_CHARS = 200

#: Attribute, die einen Personennamen oder dessen Teile tragen.
_NAME_PART_ATTRIBUTE_KEYS = ("full_name", "first_name", "last_name", "vorname", "nachname")
#: Typnamen, die selbst eine Einzelperson benennen.
_PERSON_TYPE_SUFFIXES = ("person", "individual")

_TITLE_TOKEN = re.compile(
    r"^(?:prof\.|dr\.|dipl\.-\S*|mag\.|ing\.|med\.|h\.\s?c\.|herr|frau)(?:\s+|$)",
    re.IGNORECASE,
)
_NOBLE_PARTICLES = frozenset({"von", "van", "de", "der", "zu", "zur", "vom"})
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")
_QUOTE_CHARS = re.compile(r"[\"“”„‟«»]")
_WHITESPACE = re.compile(r"\s+")


def _strip_titles(name: str) -> tuple[str, bool]:
    """Zieht führende Titel und Anreden ab; zweiter Wert: ob welche da waren."""
    rest = name.strip()
    had_title = False
    while True:
        match = _TITLE_TOKEN.match(rest)
        if match is None:
            return rest, had_title
        had_title = True
        rest = rest[match.end():].lstrip()


def _is_capitalised_word(word: str) -> bool:
    parts = word.split("-")
    return all(
        len(part) >= 2
        and part[0].isupper()
        and part[1:].isalpha()
        and part[1:].islower()
        for part in parts
    )


def is_person_shaped_name(name: str) -> bool:
    """Zwei bis vier großgeschriebene Wörter nach Abzug von Titeln und Anreden."""
    bare, _ = _strip_titles(name or "")
    if not bare or any(char.isdigit() for char in bare):
        return False
    words = [w for w in bare.split() if w not in _NOBLE_PARTICLES]
    if not 2 <= len(words) <= 4:
        return False
    return all(_is_capitalised_word(word) for word in words)


def _attribute_value(attributes: Optional[Mapping[str, Any]], key: str) -> str:
    for attr_key, value in (attributes or {}).items():
        if str(attr_key).casefold() == key:
            text = str(value if value is not None else "").strip()
            if text:
                return text
    return ""


def _function_attribute(attributes: Optional[Mapping[str, Any]]) -> str:
    """Erster nichtleere Wert aus ``FUNCTION_ATTRIBUTE_KEYS`` (ohne Groß-/Kleinschreibung)."""
    for key in FUNCTION_ATTRIBUTE_KEYS:
        value = _attribute_value(attributes, key)
        if value:
            return _single_line(value)[:MAX_FUNCTION_CHARS]
    return ""


def _single_line(value: str) -> str:
    return _WHITESPACE.sub(" ", _CONTROL_CHARS.sub(" ", value)).strip()


def _has_person_signal(
    *,
    entity_name: str,
    entity_type: str,
    attributes: Optional[Mapping[str, Any]],
) -> bool:
    if (entity_type or "").casefold().endswith(_PERSON_TYPE_SUFFIXES):
        return True
    if _strip_titles(entity_name)[1]:
        return True
    if any(_attribute_value(attributes, key) for key in _NAME_PART_ATTRIBUTE_KEYS):
        return True
    if documented_age(attributes) is not None or documented_gender(attributes) is not None:
        return True
    return bool(role_titles_in(_function_attribute(attributes)))


def _origin_marked_as_supplement(attributes: Optional[Mapping[str, Any]]) -> bool:
    return (
        _attribute_value(attributes, IDENTITY_ORIGIN_ATTRIBUTE).casefold()
        == SYNTHETIC_SUPPLEMENT_MARKER
    )


def resolve_identity_binding(
    *,
    entity_uuid: Optional[str],
    entity_name: str,
    entity_type: str,
    attributes: Optional[Mapping[str, Any]],
    summary: Optional[str],
    is_collective_type: bool,
) -> PersonaIdentityBinding:
    """Löst die Herkunft einer Entität auf (Reihenfolge ist verbindlich).

    1. Marker ``identity_origin=synthetic_supplement`` → ``synthetic_supplement``.
    2. Kollektivtyp → ``source_collective``.
    3. Personenförmiger Name, Klasse ``person``/``other`` und mindestens ein
       positives Personensignal → ``source_person``.
    4. Sonst ``synthetic_representative``; sieht der Name wie ein Personenname
       aus, fehlt aber jedes Signal, kommt ``person_status_unconfirmed`` dazu.
    """
    name = (entity_name or "").strip() or "?"
    common: dict[str, Any] = {"source_entity_uuid": entity_uuid, "source_name": name}
    if _origin_marked_as_supplement(attributes):
        return PersonaIdentityBinding(origin="synthetic_supplement", **common)
    if is_collective_type:
        return PersonaIdentityBinding(origin="source_collective", **common)

    person_shaped = is_person_shaped_name(name)
    semantic_class = classify_entity(name, entity_type or "")
    has_signal = _has_person_signal(
        entity_name=name, entity_type=entity_type, attributes=attributes
    )
    if (
        person_shaped
        and semantic_class in (SemanticEntityClass.PERSON, SemanticEntityClass.OTHER)
        and has_signal
    ):
        return _source_person_binding(common, attributes, summary)

    reasons: list[UnverifiableReason] = []
    if person_shaped and not has_signal:
        reasons.append("person_status_unconfirmed")
    return PersonaIdentityBinding(
        origin="synthetic_representative", unverifiable_reasons=reasons, **common
    )


def _source_person_binding(
    common: dict[str, Any],
    attributes: Optional[Mapping[str, Any]],
    summary: Optional[str],
) -> PersonaIdentityBinding:
    reasons: list[UnverifiableReason] = []
    function = _function_attribute(attributes)
    function_evidence: FunctionEvidence = "attribute" if function else "none"
    if function:
        if not role_titles_in(function):
            reasons.append("role_check_not_possible")
    else:
        # Nur die eigene Zusammenfassung der Entität, nicht der weitere Kontext,
        # der fremde Rollen nennt.
        titles = role_titles_in(summary)
        if titles:
            function = ", ".join(titles)[:MAX_FUNCTION_CHARS]
            function_evidence = "summary"
        else:
            reasons.append("function_not_documented")

    gender_evidence: GenderEvidence = "none"
    if documented_gender(attributes) is not None:
        gender_evidence = "attribute"
    elif function_evidence == "attribute" and gender_from_role_title(function) == "female":
        gender_evidence = "role_title"
    else:
        reasons.append("gender_not_documented")

    return PersonaIdentityBinding(
        origin="source_person",
        documented_function=function or None,
        function_evidence=function_evidence,
        gender_evidence=gender_evidence,
        unverifiable_reasons=reasons,
        **common,
    )


def source_gender(
    binding: PersonaIdentityBinding, attributes: Optional[Mapping[str, Any]]
) -> Optional[str]:
    """Geschlecht einer Quellperson, nur aus der Quelle (sonst ``None``)."""
    if binding.gender_evidence == "attribute":
        return documented_gender(attributes)
    if binding.gender_evidence == "role_title":
        return "female"
    return None


def profile_name_is_locked(profile: Any) -> bool:
    """Ob die Bindung eines Profils (JSON-Dump) den Namen sperrt."""
    binding = getattr(profile, "identity_binding", None)
    return isinstance(binding, Mapping) and binding.get("origin") in (
        "source_person",
        "source_collective",
    )


# --------------------------------------------------------------------------
# Prompt-Bausteine
# --------------------------------------------------------------------------


def _prompt_value(value: str, limit: int) -> str:
    """Wert aus einem nicht vertrauenswürdigen Dokument: einzeilig, ohne
    Steuerzeichen, ohne doppelte Anführungszeichen, auf ``limit`` gekürzt."""
    cleaned = _single_line(value)
    return _QUOTE_CHARS.sub("'", cleaned)[:limit].strip()


_DE_LINES = {
    "heading": "### Quellenbindung (verbindlich)",
    "person": "- Diese Entität ist eine in der Quelle namentlich genannte Person.",
    "name": '- display_name: exakt "{source_name}". Kein anderer Name, keine Kurzform.',
    "profession_attribute": '- profession: exakt "{function}", so in der Quelle belegt.',
    "profession_summary": (
        "- Belegte Funktion laut Quelle: {function}. profession muss sie benennen."
    ),
    "profession_none": "- Die Quelle belegt keine Funktion. Erfinde keine Leitungs- oder Amtsrolle.",
    "no_other_role": (
        "- Schreibe der Person keine andere Rolle und keinen Ausbildungs-, "
        "Ruhestands- oder Ehemaligen-Status zu, den die Quelle nicht nennt."
    ),
    "age_documented": "- age: exakt {age}, in der Quelle belegt.",
    "age_hint": (
        "- age: nicht vorgegeben. Wähle ein Alter, das zur Funktion passt; "
        "Orientierungswert {age_hint}."
    ),
    "age_free": "- age: nicht vorgegeben. Wähle ein Alter, das zur Funktion passt.",
    "gender_documented": '- gender: exakt "{gender}", in der Quelle belegt.',
    "gender_free": (
        "- gender: in der Quelle nicht belegt. Dein Wert wird für diese Person "
        "nicht übernommen."
    ),
    "mbti": (
        '- mbti: exakt "{mbti}". Synthetischer Simulationsparameter, kein Quellenbeleg.'
    ),
    "closing": (
        "- Was die Quelle nicht nennt, bleibt synthetische Ausgestaltung und "
        "darf der Quelle nicht widersprechen."
    ),
    "supplement_heading": "### Synthetische Ergänzung",
    "supplement_voice": (
        '- Diese Persona ist eine zusätzliche synthetische Stimme aus dem Umfeld von "{source_name}".'
    ),
    "supplement_not": (
        '- Sie ist nicht "{source_name}" und keine in der Quelle genannte Person.'
    ),
    "supplement_name": '- display_name darf nicht "{source_name}" sein.',
}

_EN_LINES = {
    "heading": "### Source binding (mandatory)",
    "person": "- This entity is a person the source names explicitly.",
    "name": '- display_name: exactly "{source_name}". No other name, no short form.',
    "profession_attribute": '- profession: exactly "{function}", as documented in the source.',
    "profession_summary": (
        "- Function documented in the source: {function}. profession must name it."
    ),
    "profession_none": (
        "- The source documents no function. Do not invent a leadership or office role."
    ),
    "no_other_role": (
        "- Do not give the person another role or a trainee, retired or former "
        "status the source does not state."
    ),
    "age_documented": "- age: exactly {age}, documented in the source.",
    "age_hint": (
        "- age: not prescribed. Choose an age that fits the function; "
        "reference value {age_hint}."
    ),
    "age_free": "- age: not prescribed. Choose an age that fits the function.",
    "gender_documented": '- gender: exactly "{gender}", documented in the source.',
    "gender_free": "- gender: not documented in the source. Your value is not adopted for this person.",
    "mbti": (
        '- mbti: exactly "{mbti}". Synthetic simulation parameter, not a source fact.'
    ),
    "closing": (
        "- Whatever the source does not state remains synthetic elaboration and "
        "must not contradict the source."
    ),
    "supplement_heading": "### Synthetic supplement",
    "supplement_voice": (
        '- This persona is an additional synthetic voice from the environment of "{source_name}".'
    ),
    "supplement_not": '- It is not "{source_name}" and not a person named in the source.',
    "supplement_name": '- display_name must not be "{source_name}".',
}


def build_identity_prompt_block(
    binding: PersonaIdentityBinding,
    *,
    documented_age: Optional[int] = None,
    documented_gender: Optional[str] = None,
    age_hint: Optional[int] = None,
    mbti: Optional[str] = None,
    language: str = "de",
) -> str:
    """Prompt-Baustein für Quellperson und synthetische Ergänzung.

    Für ``source_collective`` und ``synthetic_representative`` leer. Die Werte
    aus der Quelle werden bereinigt; der Baustein behauptet nirgends, reales
    Verhalten vorherzusagen.
    """
    lines = _DE_LINES if language == "de" else _EN_LINES
    source_name = _prompt_value(binding.source_name, MAX_PROMPT_NAME_CHARS)
    if binding.origin == "synthetic_supplement":
        return "\n".join(
            [
                lines["supplement_heading"],
                lines["supplement_voice"].format(source_name=source_name),
                lines["supplement_not"].format(source_name=source_name),
                lines["supplement_name"].format(source_name=source_name),
            ]
        )
    if binding.origin != "source_person":
        return ""

    function = _prompt_value(binding.documented_function or "", MAX_FUNCTION_CHARS)
    out = [lines["heading"], lines["person"], lines["name"].format(source_name=source_name)]
    if binding.function_evidence == "attribute":
        out.append(lines["profession_attribute"].format(function=function))
    elif binding.function_evidence == "summary":
        out.append(lines["profession_summary"].format(function=function))
    else:
        out.append(lines["profession_none"])
    out.append(lines["no_other_role"])
    if documented_age is not None:
        out.append(lines["age_documented"].format(age=documented_age))
    elif age_hint is not None:
        out.append(lines["age_hint"].format(age_hint=age_hint))
    else:
        out.append(lines["age_free"])
    if documented_gender:
        out.append(lines["gender_documented"].format(gender=documented_gender))
    else:
        out.append(lines["gender_free"])
    if mbti:
        out.append(lines["mbti"].format(mbti=_prompt_value(mbti, 8)))
    out.append(lines["closing"])
    return "\n".join(out)


# --------------------------------------------------------------------------
# Text einer Quellperson ohne Modell
# --------------------------------------------------------------------------


def source_person_fallback_fields(
    binding: PersonaIdentityBinding,
    summary: Optional[str],
    affiliation: Optional[str],
) -> dict[str, Optional[str]]:
    """Bio, Persona und Beruf nur aus der Quelle (regelbasierter Weg).

    Der regelbasierte Pfad erfindet sonst einen DACH-Namen und einen
    typabgeleiteten Beruf. Für eine Quellperson trägt der Text ausschließlich
    Name, belegte Funktion, Zusammenfassung und Zugehörigkeit.
    """
    name = binding.source_name
    function = binding.documented_function
    clean_summary = (summary or "").strip()
    bio = clean_summary[:150] if clean_summary else (function or name)
    persona = f"{name} ist eine in der Quelle genannte Person."
    if function:
        persona += f" Belegte Funktion: {function}."
    if clean_summary:
        persona += f" {clean_summary}"
    if affiliation:
        bio = f"{bio} | Spricht für {affiliation}"
        persona += f" Spricht für {affiliation}."
    return {"bio": bio, "persona": persona, "profession": function}


# --------------------------------------------------------------------------
# Rollenabweichung der Modellantwort
# --------------------------------------------------------------------------

#: Ausbildungsstatus im Feld ``profession`` der Modellantwort.
_TRAINEE_STATUS = re.compile(
    r"\b(?:azubi|auszubildend\w*|in ausbildung|praktikant\w*|student\w*"
    r"|schüler\w*|schueler\w*|trainee\w*)",
    re.IGNORECASE,
)
_UMLAUT_FOLD = (
    ("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss"), ("ae", "a"), ("oe", "o"), ("ue", "u"),
)


def _fold_title(title: str) -> str:
    """Kleinschreibung, Umlautfaltung, ohne feminine Endung „in“."""
    folded = title.casefold()
    for source, target in _UMLAUT_FOLD:
        folded = folded.replace(source, target)
    if folded.endswith("in") and len(folded) > 4:
        folded = folded[:-2]
    return folded


def _titles_compatible(profession: str, function: str) -> bool:
    """Ein Titel der einen Seite steckt im Titel der anderen; nennt der Beruf
    keinen erkannten Titel, genügt ein belegter Titel als Teilwort. Kein
    Synonymwissen: „Oberarzt“ ist zu „Chefarzt“ eine Abweichung."""
    documented = [_fold_title(t) for t in role_titles_in(function)]
    claimed = [_fold_title(t) for t in role_titles_in(profession)]
    if claimed:
        return any(c in d or d in c for c in claimed for d in documented)
    folded_profession = _fold_title(profession)
    return any(d in folded_profession for d in documented)


def role_deviation_reason(
    *,
    binding: PersonaIdentityBinding,
    profession: Optional[str],
    source_summary: Optional[str],
) -> Optional[str]:
    """Grund, warum der Beruf der Modellantwort der Quelle widerspricht, sonst ``None``.

    Nur für ``source_person`` und nur auf dem Feld ``profession``. Zwei
    deterministische Regeln:

    * Statusregel: ein Ausbildungs- oder Ruhestands-/Ehemaligen-Status, den
      weder die belegte Funktion noch die eigene Zusammenfassung nennt.
    * Funktionsregel: die belegte Funktion trägt einen Rollentitel, der Beruf
      ist nicht leer, und kein belegter Titel verträgt sich mit dem Beruf.

    Ohne Rollentitel in der Funktion greift nur die Statusregel. Der Grund ist
    ein kurzer Satz ohne Personennamen.
    """
    if binding.origin != "source_person":
        return None
    claimed = _single_line(profession or "")
    if not claimed:
        return None
    known = " ".join(part for part in (binding.documented_function, source_summary) if part)
    if _TRAINEE_STATUS.search(claimed) and not _TRAINEE_STATUS.search(known):
        return "Beruf der Modellantwort nennt einen Ausbildungsstatus, den die Quelle nicht belegt."
    if has_retirement_marker(claimed) and not has_retirement_marker(known):
        return "Beruf der Modellantwort nennt einen Ruhestandsstatus, den die Quelle nicht belegt."
    function = binding.documented_function or ""
    if role_titles_in(function) and not _titles_compatible(claimed, function):
        return "Beruf der Modellantwort verträgt sich nicht mit der belegten Funktion."
    return None


# --------------------------------------------------------------------------
# Laufartefakt
# --------------------------------------------------------------------------

#: Dateiname des Laufartefakts neben den Profildateien.
IDENTITY_BINDING_MANIFEST_FILENAME = "persona_identity_bindings.json"


def build_identity_binding_manifest(
    simulation_id: str, profiles: Sequence[Any]
) -> PersonaIdentityBindingManifest:
    """Ein vertragsgeprüfter Eintrag je Profil mit Bindung; Profile ohne Bindung fehlen."""
    entries = [
        PersonaIdentityBindingEntry(
            user_id=profile.user_id,
            user_name=profile.user_name,
            persona_kind=profile.persona_kind,
            binding=PersonaIdentityBinding.model_validate(profile.identity_binding),
        )
        for profile in profiles
        if profile is not None and isinstance(getattr(profile, "identity_binding", None), Mapping)
    ]
    return PersonaIdentityBindingManifest(simulation_id=simulation_id, entries=entries)


def write_identity_binding_manifest(
    sim_dir: str, simulation_id: str, profiles: Sequence[Any]
) -> PersonaIdentityBindingManifest:
    """Schreibt ``persona_identity_bindings.json`` atomar; Schreibfehler werden nicht geschluckt."""
    manifest = build_identity_binding_manifest(simulation_id, profiles)
    write_json_atomic(
        os.path.join(sim_dir, IDENTITY_BINDING_MANIFEST_FILENAME),
        manifest.model_dump(mode="json"),
    )
    return manifest
