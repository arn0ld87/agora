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
"""

from __future__ import annotations

from typing import Any, List, Optional

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

    realname: Optional[str] = None
    username: Optional[str] = None
    name: Optional[str] = None
    profession: Optional[str] = None
    bio: Optional[str] = None
    persona: Optional[str] = None
    interested_topics: Optional[List[Any]] = None


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
            raise ValueError(
                f"selected_indices nennt {len(self.selected_indices)} Agenten, "
                f"erlaubt sind hoechstens {max_agents}"
            )
        return self


class InterviewQuestions(BaseModel):
    """LLM-Antwort der Fragengenerierung.

    Der Prompt verlangt 3–5 Fragen; der Vertrag haelt dieselbe Spanne fest,
    damit der Strict-JSON-Schema-Pfad sie bereits providerseitig durchsetzt.
    Eine Antwort ausserhalb der Spanne faellt in den bestehenden
    Default-Fragensatz statt still auf fuenf gekuerzt zu werden.
    """

    model_config = ConfigDict(extra="ignore")

    questions: List[str] = Field(
        min_length=MIN_INTERVIEW_QUESTIONS,
        max_length=MAX_INTERVIEW_QUESTIONS,
    )

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
