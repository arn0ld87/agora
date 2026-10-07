"""Vertrag fuer Personasaetze (Issue #1807, Etappe 7).

Ein **Personasatz** ist eine benannte Sammlung synthetischer Personas, die in
der Bibliothek angelegt und in mehreren Laeufen verwendet werden kann. Er ist
ein Schnappschuss: ein Lauf bekommt eine **Kopie** der Personas, spaetere
Aenderungen am Satz veraendern bestehende Laeufe nicht.

Dieser Vertrag beschreibt Persistenz **und** API-Grenze. Er ist deshalb wie die
uebrigen Vertraege strikt (``extra="forbid"``) — im Gegensatz zu den reinen
Altbestandsvertraegen (``project_contract``, ``simulation_record_contract``),
die ``extra="ignore"`` tragen, weil sie Dateien frueherer Programmstaende
lesen. Personasaetze gibt es erst ab diesem Vertrag; ein unbekanntes Feld ist
ein Fehler, kein Altbestand.

``schema_version`` (#1663): Jeder neu geschriebene Satz traegt das Feld. Eine
unbekannte Version lehnt das ``Literal`` ab, statt sie still als Version 1 zu
lesen.

**Herkunft je Persona** (``PersonaOrigin``) steht am Eintrag, nicht am Profil.
``PersonaModel`` aus ``persona_contract.py`` traegt kein ``origin``; nur das
Laufprofil eines Laufs aus einem Satz fuehrt die Herkunft zusaetzlich als
``persona_set_origin`` (optional, additiv). Das Profil im Satz
(``PersonaSetProfile``) ist ein eigenes, strikt typisiertes Modell mit den
Feldern, die die Persona-Bibliothek (``persona_library._PROFILE_FIELDS``) und
der Weg ``create-from-personas`` (``persona_prepare_service``) heute tragen.
``user_id`` fehlt bewusst: sie wird erst beim Anlegen des Laufs vergeben.

**Sperre:** ``locked_at`` ist ``None``, solange der Satz bearbeitbar ist. Sobald
der erste Lauf aus dem Satz angelegt ist, steht dort der Zeitpunkt, und der
Satz ist nur noch duplizierbar. Durchgesetzt wird das im Service; der Vertrag
traegt es (``used_by_simulation_ids`` nicht leer => ``locked_at`` gesetzt).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from .pipeline_degradation_contract import PipelineDegradationReport

_STRICT = ConfigDict(extra="forbid")

#: Aktuelle Version des persistierten Satzformats (#1663).
PERSONA_SET_SCHEMA_VERSION: Literal[1] = 1

#: Obergrenzen. Sie schuetzen die Ablage (eine JSON-Datei bzw. eine JSONB-Zeile
#: je Satz) vor unbegrenztem Wachstum, nicht die Fachlichkeit.
PERSONA_SET_NAME_MAX_LENGTH = 120
PERSONA_SET_DESCRIPTION_MAX_LENGTH = 2000
PERSONA_SET_MAX_ENTRIES = 500

#: Herkunft einer Persona im Satz: aus dem Graphen gezogen, von Hand angelegt,
#: als KI-Entwurf erzeugt oder als regelbasierter Ersatz (Degradation, bleibt
#: sichtbar und wird nie als normaler Erfolg ausgegeben).
PersonaOrigin = Literal["graph", "manual", "ai_draft", "fallback"]

_Gender = Literal["male", "female", "nonbinary", "other"]
_Mbti = Literal[
    "INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP",
]

PersonaSetName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=PERSONA_SET_NAME_MAX_LENGTH,
    ),
]


def _iso_timestamp(value: str) -> str:
    """Prueft das Zeitstempelformat der Nachbarvertraege (ISO 8601, als Text).

    Der Wert bleibt die Zeichenkette, die er war: so steht er in der Ablage,
    und ein Umweg ueber ``datetime`` gaebe beim Zurueckschreiben eine andere.
    """
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"not an ISO-8601 timestamp: {value!r}") from exc
    return value


IsoTimestamp = Annotated[str, AfterValidator(_iso_timestamp)]


def _now() -> str:
    return datetime.now().isoformat()


class PersonaSetProfile(BaseModel):
    """Die Persona-Felder eines Satzeintrags.

    Entspricht der Feldliste der Persona-Bibliothek plus ``persona_kind``
    (Individual- vs. Kollektiv-Persona, #1246). Alles ausser ``username`` und
    ``name`` ist optional bzw. hat einen Vorgabewert: ein KI-Entwurf oder ein
    handgeschriebener Eintrag ist zunaechst unvollstaendig. Der Weg
    ``create-from-personas`` fuellt Luecken beim Anlegen des Laufs.
    """

    model_config = _STRICT

    username: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    bio: str = Field(default="", max_length=500)
    persona: str = Field(default="", max_length=12000)

    age: Optional[int] = Field(default=None, ge=0, le=120)
    gender: Optional[_Gender] = None
    mbti: Optional[_Mbti] = None
    country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    profession: Optional[str] = Field(default=None, max_length=200)
    interested_topics: list[str] = Field(default_factory=list, max_length=15)

    source_entity_type: Optional[str] = Field(default=None, max_length=120)
    persona_kind: Literal["individual", "collective"] = "individual"

    language: Optional[str] = Field(default=None, max_length=16)
    activity_level: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    time_zone: Optional[str] = Field(default=None, max_length=64)
    location: Optional[str] = Field(default=None, max_length=200)
    verified: bool = False


class PersonaSetEntry(BaseModel):
    """Eine Persona im Satz mit stabiler Kennung und Herkunft."""

    model_config = _STRICT

    entry_id: str = Field(min_length=1, max_length=64)
    origin: PersonaOrigin
    profile: PersonaSetProfile
    source_entity_uuid: Optional[str] = Field(default=None, max_length=128)
    created_at: IsoTimestamp = Field(default_factory=_now)
    updated_at: IsoTimestamp = Field(default_factory=_now)


class PersonaSetRecord(BaseModel):
    """Ein gespeicherter Personasatz mit allen Eintraegen.

    ``graph_id`` und ``project_id`` sind nur Verweise auf den Ursprungsgraphen;
    der Satz haengt nicht davon ab und ueberlebt dessen Loeschung. Es gibt
    keinen Fremdschluessel.
    """

    model_config = _STRICT

    id: str = Field(min_length=1, max_length=64)
    name: PersonaSetName
    description: str = Field(default="", max_length=PERSONA_SET_DESCRIPTION_MAX_LENGTH)
    graph_id: Optional[str] = Field(default=None, max_length=128)
    project_id: Optional[str] = Field(default=None, max_length=128)
    entries: list[PersonaSetEntry] = Field(
        default_factory=list, max_length=PERSONA_SET_MAX_ENTRIES
    )
    locked_at: Optional[IsoTimestamp] = None
    used_by_simulation_ids: list[str] = Field(default_factory=list)
    created_at: IsoTimestamp = Field(default_factory=_now)
    updated_at: IsoTimestamp = Field(default_factory=_now)
    schema_version: Literal[1] = Field(
        default=PERSONA_SET_SCHEMA_VERSION,
        description=(
            "Version des Satzformats (#1663). Eine unbekannte Version wird "
            "abgelehnt."
        ),
    )

    @model_validator(mode="after")
    def _check_invariants(self) -> "PersonaSetRecord":
        entry_ids = [entry.entry_id for entry in self.entries]
        if len(set(entry_ids)) != len(entry_ids):
            raise ValueError("entry_id must be unique within a persona set")
        used = self.used_by_simulation_ids
        if any(not simulation_id for simulation_id in used):
            raise ValueError("used_by_simulation_ids must not contain empty ids")
        if len(set(used)) != len(used):
            raise ValueError("used_by_simulation_ids must not contain duplicates")
        if used and self.locked_at is None:
            raise ValueError(
                "a persona set used by a simulation must be locked (locked_at)"
            )
        return self


class PersonaSetSummary(BaseModel):
    """Kachel-Sicht auf einen Satz: ohne Eintraege, mit Zaehlern."""

    model_config = _STRICT

    id: str
    name: str
    description: str
    graph_id: Optional[str] = None
    project_id: Optional[str] = None
    entry_count: int = Field(ge=0)
    locked: bool
    locked_at: Optional[str] = None
    usage_count: int = Field(ge=0)
    created_at: str
    updated_at: str
    schema_version: Literal[1] = PERSONA_SET_SCHEMA_VERSION

    @classmethod
    def from_record(cls, record: PersonaSetRecord) -> "PersonaSetSummary":
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            graph_id=record.graph_id,
            project_id=record.project_id,
            entry_count=len(record.entries),
            locked=record.locked_at is not None,
            locked_at=record.locked_at,
            usage_count=len(record.used_by_simulation_ids),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class PersonaSetCreate(BaseModel):
    """Anlegen eines leeren Satzes. Die Kennung vergibt der Server."""

    model_config = _STRICT

    name: PersonaSetName
    description: str = Field(default="", max_length=PERSONA_SET_DESCRIPTION_MAX_LENGTH)
    graph_id: Optional[str] = Field(default=None, max_length=128)
    project_id: Optional[str] = Field(default=None, max_length=128)


class PersonaSetUpdate(BaseModel):
    """Name und/oder Beschreibung aendern. Mindestens ein Feld ist Pflicht."""

    model_config = _STRICT

    name: Optional[PersonaSetName] = None
    description: Optional[str] = Field(
        default=None, max_length=PERSONA_SET_DESCRIPTION_MAX_LENGTH
    )

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "PersonaSetUpdate":
        if self.name is None and self.description is None:
            raise ValueError("at least one of name, description is required")
        return self


class PersonaSetDuplicate(BaseModel):
    """Duplizieren: die Kopie ist bearbeitbar und traegt den neuen Namen."""

    model_config = _STRICT

    name: PersonaSetName


class PersonaSetEntryCreate(BaseModel):
    """Eintrag hinzufuegen. ``entry_id`` und Zeitstempel vergibt der Server."""

    model_config = _STRICT

    origin: PersonaOrigin
    profile: PersonaSetProfile
    source_entity_uuid: Optional[str] = Field(default=None, max_length=128)


class PersonaSetEntryUpdate(BaseModel):
    """Eintrag aendern. Mindestens ``origin`` oder ``profile`` ist Pflicht.

    ``profile`` ersetzt das Profil als Ganzes; es gibt kein Teil-Profil-Update,
    weil ein fehlendes Feld sonst nicht von einem zu loeschenden zu
    unterscheiden waere.
    """

    model_config = _STRICT

    origin: Optional[PersonaOrigin] = None
    profile: Optional[PersonaSetProfile] = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "PersonaSetEntryUpdate":
        if self.origin is None and self.profile is None:
            raise ValueError("at least one of origin, profile is required")
        return self


class PersonaSetEntriesDelete(BaseModel):
    """Mehrfachauswahl zum Loeschen. Alles oder nichts.

    Ist eine Kennung dem Satz unbekannt, aendert die Anfrage nichts und
    antwortet 404. Doppelte Kennungen zaehlen einmal.
    """

    model_config = _STRICT

    entry_ids: list[str] = Field(
        min_length=1, max_length=PERSONA_SET_MAX_ENTRIES
    )


class PersonaSetListResponse(BaseModel):
    """Antwort von ``GET /api/persona-sets``: Kacheln, neuester Satz zuerst."""

    model_config = _STRICT

    count: int = Field(ge=0)
    sets: list[PersonaSetSummary]


class PersonaSetDeleteResponse(BaseModel):
    """Antwort von ``DELETE /api/persona-sets/<set_id>``."""

    model_config = _STRICT

    removed: str


class PersonaSetEntriesDeleteResponse(BaseModel):
    """Antwort auf das Loeschen von Eintraegen: Kennungen und neuer Stand."""

    model_config = _STRICT

    removed_entry_ids: list[str]
    set: PersonaSetSummary


class CreateFromPersonasResponse(BaseModel):
    """Antwort (201) von ``POST /api/simulation/create-from-personas``.

    Gilt fuer alle drei Quellen. ``persona_set_id`` und ``degradations`` gibt es
    nur bei einem Lauf aus einem Personasatz; ohne Satz fehlen beide Schluessel
    in der Antwort (``exclude_if``), damit die Form der Bibliotheks- und
    Inline-Wege byte-identisch zur frueheren Antwort bleibt.

    ``degradations`` ist der Befundbericht der Vorbereitung (z. B. regelbasierte
    Fallback-Personas, #1807). Ein Lauf aus einem Satz traegt ihn immer, eine
    leere Liste heisst: nichts ist still ausgefallen.
    """

    model_config = _STRICT

    simulation_id: str
    project_id: str
    persona_count: int = Field(ge=0)
    persona_set_id: Optional[str] = Field(
        default=None, exclude_if=lambda value: value is None
    )
    degradations: Optional[PipelineDegradationReport] = Field(
        default=None, exclude_if=lambda value: value is None
    )


QualitySeverity = Literal["error", "warning", "info"]


class PersonaSetQualityIssue(BaseModel):
    """Ein Qualitaetshinweis (Code und Schwere wie ``PersonaQualityService``)."""

    model_config = _STRICT

    code: str
    severity: QualitySeverity
    detail: Optional[dict[str, Any]] = None


class PersonaSetQualityPersona(BaseModel):
    """Hinweise zu einem Eintrag. Die Reihenfolge ist die der Eintraege im Satz."""

    model_config = _STRICT

    entry_id: str
    username: str
    issues: list[PersonaSetQualityIssue]


class PersonaSetQualitySummary(BaseModel):
    """Verteilungskennzahlen des Satzes (ohne Review-Zaehler: Saetze kennen kein Review)."""

    model_config = _STRICT

    total: int = Field(ge=0)
    role_diversity: float = Field(ge=0.0)
    mbti_diversity: float = Field(ge=0.0)
    distinct_roles: list[str]
    distinct_mbti: list[str]


class PersonaSetQualityReport(BaseModel):
    """Antwort von ``GET /api/persona-sets/<set_id>/quality``.

    Reine Heuristik ohne LLM-Aufruf und ohne Simulation. Hinweise sind
    Hinweise: sie sperren nichts.
    """

    model_config = _STRICT

    set_id: str
    summary: PersonaSetQualitySummary
    global_issues: list[PersonaSetQualityIssue]
    personas: list[PersonaSetQualityPersona]
