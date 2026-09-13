"""Vertraege fuer den Interviewpfad (``app/services/graph/interview_helpers.py``).

Drei Datenquellen erreichten den Interviewpfad bisher ungeprueft:

1. die persistierte Profil-Datei (``reddit_profiles.json``) — mit ``json.load``
   gelesen und danach als ``List[Dict[str, Any]]`` behandelt. Eine Datei mit
   ``{"profiles": []}``, ``[null]`` oder ``[123]`` flog erst viel spaeter beim
   ersten ``profile.get(...)`` auseinander;
2. die LLM-Antwort der Panel-Auswahl — ``selected_indices`` wurde nur gegen die
   Profilgrenzen gefiltert. ``[true]`` passierte (``bool`` ist Subtyp von
   ``int``, also waehlte ``True`` den Agenten mit Index 1), ``[1, 1]``
   interviewte dieselbe Persona doppelt, ``["1"]`` liess die Schleife mit
   ``TypeError`` in den Fallback laufen;
3. die LLM-Antwort der Fragengenerierung — ``response.get("questions", …)``
   gab bei ``{"questions": null}`` ``None`` zurueck und bei
   ``{"questions": "Warum?"}`` einen String, ueber den der Aufrufer
   anschliessend zeichenweise iterierte.

Die Modelle hier sind Validierungs-Gates, keine Transformationsschicht: der
Profil-Vertrag laesst die Originaldicts unveraendert (siehe
``PersistedAgentProfiles``), damit die vorhandene Feld-Fallback-Kette
(``realname`` → ``username`` → ``Agent_<i>``) genau so weiterarbeitet wie
bisher.

Eine bewusste, eng begrenzte Ausnahme von der Gate-Regel (Review PR #1498):
``InterviewAgentSelection.selected_indices`` und ``InterviewQuestions.questions``
kappen auf ihre jeweilige Obergrenze, statt eine Antwort zu verwerfen, die
*ausschliesslich* zu viele ansonsten gueltige, eindeutige Eintraege enthaelt.
Das ist keine Transformation von Nutzdaten wie beim Profil-Vertrag, sondern
eine Mengenbegrenzung auf einer bereits vollstaendig validierten Auswahl —
siehe die Begruendung an den jeweiligen Validatoren.
"""

from __future__ import annotations

from typing import Any, List

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictInt,
    ValidationInfo,
    field_validator,
    model_validator,
)

DEFAULT_SELECTION_REASONING = "Automatically selected based on relevance"

MIN_INTERVIEW_QUESTIONS = 3
MAX_INTERVIEW_QUESTIONS = 5


class InterviewAgentProfile(BaseModel):
    """Ein persistiertes Agent-Profil — nur so streng wie noetig.

    ``extra="allow"`` ist Absicht: die Datei traegt je nach Plattform und
    Persona-Art unterschiedliche Zusatzfelder (``age``, ``mbti``, ``segment``,
    ``persona_kind`` …), und keines davon darf eine gueltige Bestandsdatei
    ungueltig machen. Erzwungen wird ausschliesslich, was der Interviewpfad
    tatsaechlich dereferenziert — ein ``bio`` als Zahl waere ein ``TypeError``
    beim ``[:200]``-Schnitt, ein Nicht-Objekt als Listenelement ein
    ``AttributeError`` beim ``.get``.
    """

    model_config = ConfigDict(extra="allow")

    # Default statt ``Optional``: ein *fehlendes* Feld ist unproblematisch — die
    # Fallbackkette des Interviewpfads (``realname`` → ``username`` →
    # ``Agent_<i>``) faengt es ab, und weil nur validiert und nicht umgeschrieben
    # wird, bleibt der Schluessel im Originaldict weiterhin abwesend.
    #
    # Ein ausdrueckliches ``null`` ist etwas anderes und wird abgelehnt:
    # ``profile.get("bio", "")[:200]`` liefert dafuer ``None[:200]`` und wirft
    # ``TypeError`` — und zwar ausserhalb des ``try`` von
    # ``select_agents_for_interview``, also mit Abbruch des gesamten
    # Interviewlaufs statt eines Fallbacks. Eine Datei mit ``null``-Feldern
    # gehoert deshalb in denselben CSV-/Leer-Pfad wie eine unlesbare.
    realname: str = ""
    username: str = ""
    name: str = ""
    profession: str = ""
    bio: str = ""
    persona: str = ""
    interested_topics: List[Any] = Field(default_factory=list)


class PersistedAgentProfiles(RootModel[List[InterviewAgentProfile]]):
    """Root-Vertrag der Profil-Datei: eine Liste von Profil-Objekten.

    Bewusst ein reines Gate. Die Aufrufer arbeiten nach erfolgreicher Pruefung
    mit den *Originaldicts* weiter, nicht mit ``model_dump()``: ein Dump wuerde
    nicht gesetzte Felder als ``None`` materialisieren, und
    ``profile.get("realname", profile.get("username", …))`` faende dann ein
    ``None`` vor, statt auf ``username`` durchzufallen — eine stille
    Verhaltensaenderung an einer Stelle, die dieser Vertrag gerade absichern
    soll.
    """

    root: List[InterviewAgentProfile]


class InterviewAgentSelection(BaseModel):
    """LLM-Antwort der Panel-Auswahl.

    ``StrictInt`` statt ``int``: Pydantic akzeptiert im Lax-Modus sowohl
    ``True`` als auch ``"1"`` als ``int``. Beides ist hier keine gueltige
    Auswahl, sondern eine kaputte Antwort.

    Grenz- und Kappungspruefung laufen ueber den Validierungskontext, weil
    Profilanzahl und ``max_agents`` erst am Aufrufort bekannt sind::

        InterviewAgentSelection.model_validate(
            payload, context={"profile_count": len(profiles), "max_agents": 5}
        )

    Ohne Kontext prueft das Modell nur Typ, Vorzeichen und Eindeutigkeit.

    Ueberschreitet ``max_agents`` (Review PR #1498, Befund): wird auf die
    ersten ``max_agents`` Indizes gekappt, nicht verworfen. Eine Antwort mit
    6 statt 5 eindeutigen, in-range Indizes ist keine kaputte Antwort — sie
    ueberschreitet nur das Cap. Ein fruehes ``raise`` hier landete im breiten
    ``except Exception`` von ``select_agents_for_interview`` und ersetzte die
    inhaltliche LLM-Auswahl durch den generischen "erste N Profile"-Fallback,
    also durch einen strikt schlechteren Ersatz fuer eine im Kern brauchbare
    Antwort. Ausserhalb des Cap-Falls bleibt jede sonstige Verletzung
    (falscher Typ, negative Indizes, Duplikate, Indizes ausserhalb des
    Profilarrays) eine echte Ablehnung.
    """

    model_config = ConfigDict(extra="ignore")

    selected_indices: List[StrictInt] = Field(default_factory=list)
    reasoning: str = DEFAULT_SELECTION_REASONING

    @field_validator("reasoning", mode="before")
    @classmethod
    def _default_missing_reasoning(cls, value: Any) -> Any:
        # Ein fehlendes ``reasoning`` ist kein Grund, eine brauchbare Auswahl zu
        # verwerfen — der dokumentierte Default greift, wie bisher auch.
        return DEFAULT_SELECTION_REASONING if value is None else value

    @field_validator("selected_indices")
    @classmethod
    def _reject_duplicates_and_negatives(cls, value: List[int]) -> List[int]:
        if any(index < 0 for index in value):
            raise ValueError("selected_indices enthaelt negative Indizes")
        if len(set(value)) != len(value):
            raise ValueError("selected_indices enthaelt Duplikate")
        return value

    @model_validator(mode="after")
    def _within_context_bounds(self, info: ValidationInfo) -> "InterviewAgentSelection":
        context = info.context or {}
        profile_count = context.get("profile_count")
        if profile_count is not None:
            out_of_range = [i for i in self.selected_indices if i >= profile_count]
            if out_of_range:
                raise ValueError(
                    f"selected_indices ausserhalb des Profilarrays ({profile_count} "
                    f"Profile): {out_of_range}"
                )
        max_agents = context.get("max_agents")
        if max_agents is not None and len(self.selected_indices) > max_agents:
            # Kappen statt verwerfen: an dieser Stelle ist die Auswahl bereits
            # typgeprueft, positiv, eindeutig und im Profilarray belegt — die
            # einzige verbleibende Abweichung ist die Laenge. Die ersten
            # ``max_agents`` vom Modell genannten Indizes zu behalten erhaelt
            # die inhaltliche Auswahl; ein ``ValueError`` hier wuerde sie
            # komplett wegwerfen (siehe Klassendocstring).
            self.selected_indices = self.selected_indices[:max_agents]
        return self


class InterviewQuestions(BaseModel):
    """LLM-Antwort der Fragengenerierung.

    Der Prompt verlangt 3–5 Fragen; ``max_length`` haelt diese Obergrenze im
    Modell fest, damit ``model_json_schema()`` sie providerseitig im
    Strict-JSON-Schema-Pfad mitdurchsetzt (``schema=InterviewQuestions`` in
    ``chat_json``). Trotzdem kann eine Antwort ankommen, die die Grenze
    verletzt — nicht jeder Provider erzwingt ``maxItems`` zuverlaessig.

    Zu WENIGE Fragen (< ``MIN_INTERVIEW_QUESTIONS``) bleiben eine echte
    Ablehnung: das ist eine kaputte Antwort, Kappen kann sie nicht reparieren.
    Zu VIELE gueltige, nichtleere Fragen sind das nicht — ``_cap_excess``
    kappt sie (Review PR #1498) auf die ersten ``MAX_INTERVIEW_QUESTIONS``,
    statt die komplette Antwort zu verwerfen und in den generischen
    Default-Fragensatz des Aufrufers zu fallen (eine einzige Frage statt
    fuenf inhaltlich passender).
    """

    model_config = ConfigDict(extra="ignore")

    questions: List[str] = Field(
        min_length=MIN_INTERVIEW_QUESTIONS,
        max_length=MAX_INTERVIEW_QUESTIONS,
    )

    @field_validator("questions", mode="before")
    @classmethod
    def _cap_excess_questions(cls, value: Any) -> Any:
        # ``mode="before"`` laeuft vor der ``max_length``-Pruefung von
        # ``Field`` — deshalb kappt dieser Validator, statt dass ``Field``
        # anschliessend verwirft. Nicht-Listen (z. B. ``None`` oder ein
        # blanker String) unveraendert durchreichen: die Typ-/Struktur-
        # pruefung dafuer bleibt Sache der Kernvalidierung weiter unten.
        if isinstance(value, list) and len(value) > MAX_INTERVIEW_QUESTIONS:
            return value[:MAX_INTERVIEW_QUESTIONS]
        return value

    @field_validator("questions")
    @classmethod
    def _reject_blank_questions(cls, value: List[str]) -> List[str]:
        if any(not question.strip() for question in value):
            raise ValueError("questions enthaelt leere Fragen")
        return value


__all__ = [
    "DEFAULT_SELECTION_REASONING",
    "MAX_INTERVIEW_QUESTIONS",
    "MIN_INTERVIEW_QUESTIONS",
    "InterviewAgentProfile",
    "InterviewAgentSelection",
    "InterviewQuestions",
    "PersistedAgentProfiles",
]
