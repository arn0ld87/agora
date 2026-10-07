"""KI-Entwurf einer Persona fuer einen Personasatz (Issue #1807, Slice 7c).

Der einzige LLM-Aufruf der Etappe 7. Er steht bewusst **nicht** in
``persona_set_service`` — dort steht im Modulkopf „Kein LLM-Aufruf in diesem
Modul", und das ist eine Grenze, keine Zufallsgrenze: Sperre, Eindeutigkeit
und Schnappschuss brauchen keinen Anbieter und sollen pruefbar bleiben, ohne
dass ein Test ein Modell braucht. Hierher gehoert alles, was einen Anbieter
braucht; zurueck kommt ein fertiges Profil.

**Verrechnung.** Jeder Entwurf laeuft als eigener Job (``run_type="persona_draft"``)
in der ``RunRegistry``. Das ist keine Beobachtung am Rand: ``LLMClient`` holt
seinen ``RunBudgetEnforcer`` aus genau dieser ``run_id`` (#984). Ohne den Job
wuerde ein Entwurf am harten Run-Budget vorbeikommen und in keiner
Aktivitaetsliste auftauchen — ein Aufruf ohne Spur.

**Fehler.** Anders als bei der Persona-Erzeugung im Prepare-Pfad faellt der
Entwurf hier **nicht** auf einen regelbasierten Ersatz zurueck. Eine erfundene
Persona, die als Entwurf auf der Kachel steht, waere schlimmer als eine
sichtbare Fehlermeldung: Der Aufrufer entscheidet, ob er ohne Entwurf weiter
arbeitet oder den Satz von Hand befuellt. Ein ``BudgetExceededError`` wird
ebenso durchgereicht wie beim Prepare-Pfad (PR #1461) — er darf nicht in einen
regelbasierten Eintrag mit ``origin="fallback"`` verwandelt werden.

**Was das Modell nicht entscheidet.** Die Herkunft vergibt der Dienst
(``origin="ai_draft"``), nicht der Aufruf und nicht das Modell: sie ist eine
Tatsache ueber den Entwurfungsweg, und genau diese Zuschreibung will die
Herkunftsplakette in der Oberflaeche (#4.1) erhalten. Laengenbegrenzungen und
die ``PersonaSetProfile``-Form setzt der Dienst ebenfalls, sonst traegt der
Editor Felder, die er nicht anzeigen kann.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, cast, get_args

from pydantic import BaseModel, Field, ValidationError

from ..contracts import persona_set_contract as _set_contract
from ..contracts.persona_set_contract import (
    PERSONA_DRAFT_BIO_MAX_LENGTH,
    PERSONA_DRAFT_EXAMPLE_POST_MAX_LENGTH,
    PERSONA_DRAFT_PERSONA_MAX_LENGTH,
    PersonaDraftExamplePost,
    PersonaDraftRequest,
    PersonaSetProfile,
)
from ..services.run_budget import BudgetExceededError
from ..services.run_registry import RunRegistry
from ..utils.logger import get_logger

#: Die beiden Vertrags-Enums als Aliase. Sie kommen aus dem Vertragsmodul
#: statt als eigene Liste: zwei Namen fuer dieselbe Menge waere eine Stelle,
#: an der Vertrag und Dienst auseinanderlaufen.
_Gender = _set_contract._Gender
_Mbti = _set_contract._Mbti

logger = get_logger("agora.persona_sets.draft")

#: Versuche, bis das Modell ein verwertbares Profil liefert. Zwei sind genug:
#: ein dritter Versuch kostet Tokens ohne neue Information — der Brief ist
#: derselbe, und was beim zweiten Mal fehlt, fehlt auch beim dritten.
MAX_DRAFT_ATTEMPTS = 2

#: Job-Typ im RunRegistry. Eigener Typ, damit die Aktivitaet den Entwurf von
#: einem Lauf unterscheidet und die Stop-Regel der Simulation (die nur
#: ``simulation_run`` kennt) nicht auf einen Entwurf greift.
DRAFT_RUN_TYPE = "persona_draft"

#: Die 16 MBTI-Typen. Aus ``persona_set_contract`` bezogen statt hier
#: abgeschrieben: eine zweite Liste waere eine Stelle, an der Vertrag und
#: Dienst auseinanderlaufen — ein Wert, den der Vertrag kennt, den der Dienst
#: verwirft, oder umgekehrt.
_MBTI_TYPES = frozenset(get_args(_set_contract._Mbti))

#: Geschlechter des Vertrags. Aus demselben Grund wie die MBTI-Menge: eine
#: zweite Liste waere eine Stelle, an der Vertrag und Dienst auseinanderlaufen.
_GENDERS = frozenset(get_args(_set_contract._Gender))

#: Angefragtes Token-Limit. Der Entwurf ist eine kurze Vita plus ein Beitrag;
#: mehr Token laesst das Modell Fuelltext statt Inhalt produzieren.
DRAFT_MAX_TOKENS = 1200


class PersonaDraftError(Exception):
    """Der Entwurf ist gescheitert.

    Bewusst kein ``ValueError`` und keine ``ValidationError``: beides faengt der
    API-Envelope als 400 und wuerde einen Anbieterfehler als Fehler der Anfrage
    ausgeben. Die Oberflaeche muss unterscheiden koennen, ob ihr Brief oder der
    Anbieter schuld war (#1807).
    """


class PersonaDraftUnavailable(PersonaDraftError):
    """Es ist kein Anbieter konfiguriert oder erreichbar."""


class PersonaDraftRequestModel(BaseModel):
    """Antwort des Modells.

    Bewusst ein eigenes Modell statt des Zod-/Pydantic-Spiegels
    ``PersonaSetProfile``: das Modell liefert eine Auswahl, keine vollstaendige
    Vita. ``extra="ignore"`` ist hier richtig — unbekannte Felder verwerfen wir,
    statt die Antwort zu verwerfen.

    Enge Laengen: der Dienst kuerzt danach hart, damit ein Entwurf den Editor
    und die Bibliothekskachel nicht sprengt.
    """

    # Bewusst KEINE Laengenobergrenzen und kein Country-Muster: ``chat_json``
    # validiert die Antwort gegen dieses Modell, bevor der Dienst sie sieht.
    # Eine Grenze im Schema wuerde eine zu lange Antwort als Fehlschlag
    # ausgeben und den zweiten Versuch mit demselben Brief erneut scheitern
    # lassen — ein Entwurf, der nur zu lang ist, waere damit nie moeglich.
    # Begrenzt wird stattdessen in ``_build_profile``.
    username: str = Field(min_length=1)
    name: str = Field(min_length=1)
    bio: str = ""
    persona: str = ""
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: list[str] = Field(default_factory=list)
    language: Optional[str] = None
    activity_level: Optional[float] = None
    time_zone: Optional[str] = None
    location: Optional[str] = None
    example_post: Optional[str] = None
    example_network: str = "twitter"


_SYSTEM_PROMPT = (
    "Du entwirfst eine einzelne synthetiche Person fuer eine "
    "Simulation sozialer Netzwerke. Du schreibst knapp und konkret.\n"
    "\n"
    "Regeln:\n"
    "- Eine Person, keine Gruppe und keine Organisation.\n"
    "- 'username' ohne Leerzeichen, ohne @, im Stil sozialer Netzwerke.\n"
    "- 'bio' ist ein Satz, 'persona' ist der Freitext im Ich-Stil: "
    "Interessen, Haltung, Redeweise.\n"
    "- Du erfindest keine Organisation und keinen realen Menschen.\n"
    "- 'example_post' ist ein einzelner kurzer Beitrag, den diese Person "
    "in einem Netzwerk schreiben wuerde — nicht ueber sich selbst.\n"
    "- Leere Felder sind erlaubt. Erfinde lieber nichts als Fuelltext.\n"
    "\n"
    "Antworte ausschliesslich mit JSON in der verlangten Form."
)

_USER_PROMPT = (
    "Beschreibung der Rolle:\n{brief}\n\n"
    "Schreibe die Person und einen Beispielbeitrag. "
    "Antwortsprache fuer alle Texte: {language}."
)


def _job_messages(request: PersonaDraftRequest) -> list[Dict[str, str]]:
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _USER_PROMPT.format(
                brief=request.brief, language=request.language
            ),
        },
    ]


def _clip(value: Optional[str], limit: int) -> str:
    """Schneidet hart an der Grenze; ein halber Satz schlaegt ein fehlender."""
    if not value:
        return ""
    return value.strip()[:limit]


#: Laender, die der Vertrag als Kuerzel traegt. Nur die, die OASIS/Agora heute
#: in den Personas als zweistelliges Land sieht — eine Liste, keine Regel.
_COUNTRY_CODES = {
    "DE": "DE", "GERMANY": "DE", "DEUTSCHLAND": "DE", "AT": "AT",
    "AUSTRIA": "AT", "ÖSTERREICH": "AT", "CH": "CH", "SWITZERLAND": "CH",
    "SCHWEIZ": "CH", "NL": "NL", "NETHERLANDS": "NL", "FR": "FR",
    "FRANCE": "FR", "US": "US", "USA": "US", "UNITED STATES": "US",
}


def _normalise_country(value: Optional[str]) -> Optional[str]:
    """Laendername oder Kuerzel auf das zweistellige Kuerzel.

    Ein Land, das nicht in der Liste steht, faellt weg. Ein falsches Kuerzel
    waere eine Behauptung ueber die Herkunft der Person — stiller als ein
    fehlendes Feld, und der Vertrag traegt es nicht.
    """
    if not value:
        return None
    key = value.strip().upper()
    if len(key) == 2 and key.isalpha():
        return key
    return _COUNTRY_CODES.get(key)


def _normalise_gender(value: Optional[str]) -> Optional[_Gender]:
    """``male``/``female``/``nonbinary``/``other``, alles andere faellt weg.

    Ein stilles ``None`` statt eines geratenen Werts: das Feld ist optional,
    und eine falsche Angabe waere schlimmer als eine fehlende. Das Modell
    bekommt die Auswahl im Prompt, aber ein Anbieter kann sie ignorieren.
    """
    if not value:
        return None
    normalised = value.strip().lower()
    if normalised in _GENDERS:
        return cast(_Gender, normalised)
    return None


def _normalise_mbti(value: Optional[str]) -> Optional[_Mbti]:
    """MBTI auf die 16 Typen des Vertrags.

    Vier Buchstaben sind nicht genug: „INTX" sieht wohlgeformt aus und ist
    keiner der 16 Typen. Genau solche Werte liefert ein Modell, wenn es die
    Liste nicht kennt — sie durchzulassen hiesse, dem Vertrag einen Wert
    zuzumuten, den es gar nicht gibt (und ``PersonaSetProfile`` lehnte ihn
    ab, was den ganzen Entwurf statt des einen Feldes kippen wuerde).
    """
    if not value:
        return None
    normalised = value.strip().upper()
    return cast(_Mbti, normalised) if normalised in _MBTI_TYPES else None


def _build_profile(
    draft: PersonaDraftRequestModel, language: str
) -> PersonaSetProfile:
    """Setzt das Modellergebnis in die Vertragsform.

    Jeder Schritt ist eine Begrenzung, keine Verzierung: Felder kuerzen auf die
    Vertragsgrenze, ``country`` auf zwei Zeichen, Enums normalisieren oder
    verwerfen. Was der Vertrag nicht traegt, faellt weg statt den Editor zu
    sprengen — die Oberflaeche fragt bei einem fehlenden Feld nach, bei einem
    zu langen Feld nicht.
    """
    # Laendername auf das Kuerzel: das Modell liefert gern "Deutschland" oder
    # "Germany", der Vertrag traegt genau zwei Zeichen. Ein Land, das nicht
    # aufloesbar ist, faellt weg, statt geraten zu werden.
    country = _normalise_country(draft.country)
    return PersonaSetProfile(
        username=draft.username.strip()[:64],
        name=draft.name.strip()[:120],
        bio=_clip(draft.bio, PERSONA_DRAFT_BIO_MAX_LENGTH),
        persona=_clip(draft.persona, PERSONA_DRAFT_PERSONA_MAX_LENGTH),
        age=draft.age,
        gender=_normalise_gender(draft.gender),
        mbti=_normalise_mbti(draft.mbti),
        country=country,
        profession=_clip(draft.profession, 200) or None,
        interested_topics=[t.strip() for t in draft.interested_topics if t.strip()][:15],
        language=(draft.language or language).strip()[:16],
        activity_level=draft.activity_level,
        time_zone=draft.time_zone,
        location=draft.location,
        verified=False,
    )


def _build_example_post(
    draft: PersonaDraftRequestModel,
) -> Optional[PersonaDraftExamplePost]:
    """Der Beispielbeitrag ist optional: fehlt er, bleibt die Vorschau leer.

    Leises Weglassen statt Erfinden: ein Beispielbeitrag, den der Dienst selbst
    formuliert, waere eine erfundene Aeusserung einer erfundenen Person — zwei
    Erfindungen uebereinander. Entweder das Modell liefert einen, oder die
    Vorschau bleibt leer und die Oberflaeche sagt das.
    """
    content = _clip(draft.example_post, PERSONA_DRAFT_EXAMPLE_POST_MAX_LENGTH)
    if not content:
        return None
    network = (draft.example_network or "twitter").strip().lower()
    return PersonaDraftExamplePost(
        content=content,
        network="reddit" if network == "reddit" else "twitter",
    )


def _run_job(set_id: str, request: PersonaDraftRequest) -> str:
    """Legt den Job an und gibt seine ``run_id`` zurueck.

    Die ``run_id`` ist keine Beobachtungsnummer: ``LLMClient`` leitet daraus
    den ``RunBudgetEnforcer`` ab. Ohne sie laeuft der Entwurf am Budget vorbei.
    """
    run = RunRegistry().create_run(
        run_type=DRAFT_RUN_TYPE,
        entity_id=set_id,
        status="running",
        progress=0,
        message=f"KI-Entwurf fuer Personasatz {set_id}",
        linked_ids={"persona_set_id": set_id},
        metadata={"brief_length": len(request.brief), "language": request.language},
    )
    return str(run["run_id"])


def _finish_job(
    run_id: str, *, set_id: str, entry_id: Optional[str], error: Optional[str]
) -> None:
    """Schliesst den Job ab — auch im Fehlerfall.

    Ohne Abschluss bleibt der Entwurf in der Aktivitaet ewig „laeuft", und der
    naechste Blick auf die Liste zeigt einen Aufruf, den niemand gemacht hat.
    """
    try:
        if error is None:
            RunRegistry().update_run(
                run_id,
                status="completed",
                progress=100,
                message=f"KI-Entwurf im Personasatz {set_id} angelegt",
                completed_at=True,
            )
        else:
            RunRegistry().update_run(
                run_id,
                status="failed",
                message=f"KI-Entwurf fuer Personasatz {set_id} fehlgeschlagen",
                error=error[:500],
                termination_reason="error",
            )
    except Exception as exc:  # noqa: BLE001 — die Fertigmeldung darf nie den Entwurf kippen
        logger.warning(
            "persona_draft.job_finish_failed", extra={"run_id": run_id, "error": str(exc)}
        )


def _client(run_id: str):
    """Der Client aus der aktiven Konfiguration, gebunden an den Job.

    Ohne ``run_id`` haette ``LLMClient`` keinen Enforcer (#984). Modell und
    Anbieter kommen aus der aktiven LLM-Auswahl, damit ein Entwurf mit dem
    Modell entsteht, das auch die Simulation benutzt.
    """
    from ..llm.client import LLMClient

    return LLMClient(run_id=run_id)


def _validate_draft(payload: Dict[str, Any]) -> PersonaDraftRequestModel:
    """Verlangt ein verwertbares Profil; ein unbrauchbares ist ein Fehlschlag.

    ``username`` und ``name`` sind Pflicht, weil ohne sie kein Eintrag entsteht,
    an dem man ihn erkennen koennte. Fehlen sie, ist die Antwort kein Entwurf,
    sondern Text — und der Aufrufer soll das wissen statt einen leeren Eintrag
    zu bekommen.
    """
    try:
        return PersonaDraftRequestModel.model_validate(payload)
    except ValidationError as exc:
        raise PersonaDraftError(
            "Das Modell lieferte kein verwertbares Profil: "
            + "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}"
                for error in exc.errors()[:3]
            )
        ) from exc


def draft_persona_entry(
    *,
    set_id: str,
    brief: str,
    language: str = "de",
) -> Dict[str, Any]:
    """Entwirft eine Persona und liefert Profil und Beispielbeitrag.

    Legt **nichts** im Satz an: der Dienst entscheidet nicht, ob der Entwurf
    in den Satz gehoert. Das macht ``PersonaSetService.add_entry`` — dort
    liegen Sperre und ``username``-Eindeutigkeit, und ein zweiter Pfad an der
    Herkunft vorbei waere genau die Art Umweg, die die Herkunftsplakette
    spaeter nicht mehr traegt.

    Rueckgabe ist ein dict, kein Vertragsmodell: die Antwort setzt der Dienst
    aus ``PersonaSetEntryCreate`` zusammen, damit die Herkunft nicht vom
    Aufrufer kommt.
    """
    try:
        request = PersonaDraftRequest(brief=brief, language=language)
    except ValidationError as exc:
        raise PersonaDraftError(
            "Der Auftrag an das Modell ist unvollstaendig"
        ) from exc

    run_id = _run_job(set_id, request)
    messages = _job_messages(request)
    # Ein Client fuer beide Versuche: der Budget-Enforcer liest das Ledger,
    # und der Weg ist derselbe. Nur die Temperatur sinkt pro Versuch.
    client = _client(run_id)
    last_error: Optional[Exception] = None

    for attempt in range(MAX_DRAFT_ATTEMPTS):
        try:
            result = client.chat_json(
                messages=messages,
                temperature=0.7 - (attempt * 0.2),
                max_tokens=DRAFT_MAX_TOKENS,
                schema=PersonaDraftRequestModel,
                schema_name="persona_draft",
                context="persona",
                force_no_thinking=True,
                enforce_token_floor=False,
            )
            draft = _validate_draft(result)
            profile = _build_profile(draft, request.language)
            example_post = _build_example_post(draft)
            _finish_job(run_id, set_id=set_id, entry_id=None, error=None)
            return {
                "profile": profile.model_dump(mode="json"),
                "example_post": (
                    example_post.model_dump(mode="json") if example_post else None
                ),
            }
        except BudgetExceededError:
            # Wie im Prepare-Pfad (PR #1461): ein hartes Budget muss
            # durchschlagen. Ohne diese Klausel wuerde der breite Handler
            # darunter drei Versuche lang erneut aufrufen und am Ende einen
            # regelbasierten Eintrag als „Entwurf" ausgeben.
            _finish_job(run_id, set_id=set_id, entry_id=None, error="budget exceeded")
            raise
        except PersonaDraftError:
            _finish_job(
                run_id, set_id=set_id, entry_id=None, error="unusable draft"
            )
            raise
        except Exception as exc:  # noqa: BLE001 — jeder Anbieterfehler wird sichtbar
            last_error = exc
            logger.warning(
                "persona_draft.attempt_failed",
                extra={
                    "run_id": run_id,
                    "set_id": set_id,
                    "attempt": attempt + 1,
                    "error": str(exc)[:160],
                },
            )

    _finish_job(run_id, set_id=set_id, entry_id=None, error=str(last_error))
    raise PersonaDraftUnavailable(
        f"Der Entwurf ist nach {MAX_DRAFT_ATTEMPTS} Versuchen gescheitert: "
        f"{str(last_error)[:200]}"
    ) from last_error


__all__ = [
    "DRAFT_RUN_TYPE",
    "MAX_DRAFT_ATTEMPTS",
    "PersonaDraftError",
    "PersonaDraftRequestModel",
    "PersonaDraftUnavailable",
    "draft_persona_entry",
]
