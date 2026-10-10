"""PersonaIdentityBinding-Contract v1 (Pydantic v2) — Issue #1833.

Die Identität, die eine Quelle einer Person oder einem Kollektiv gibt, hat
Vorrang vor Modellumbenennung und zufälliger Demografie. Dieser Vertrag hält
fest, *woher* die Identität einer Persona stammt:

* ``source_person``: in der Quelle namentlich genannte Person. Name und belegte
  Funktion sind gesperrt, Geschlecht stammt nur aus der Quelle.
* ``source_collective``: in der Quelle genannte Organisation oder Gruppe. Der
  Entitätsname bleibt, es gibt keine Demografie.
* ``synthetic_representative``: ein erfundener Vertreter für eine Entität, die
  keine namentlich genannte Person ist.
* ``synthetic_supplement``: eine ausdrücklich synthetische Zusatzstimme
  (Quoten- oder Floor-Replikat), nie die Quellperson selbst.

Das Modell ist ein Backend-internes Artefakt (Laufdatei neben den
Profildateien). ``PersonaModel`` und alle API-Antworten bleiben unverändert.

Kein Import aus ``app.services``.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

PersonaIdentityOrigin = Literal[
    "source_person",
    "source_collective",
    "synthetic_representative",
    "synthetic_supplement",
]
FunctionEvidence = Literal["attribute", "summary", "none"]
GenderEvidence = Literal["attribute", "role_title", "none"]
UnverifiableReason = Literal[
    "person_status_unconfirmed",
    "function_not_documented",
    "role_check_not_possible",
    "gender_not_documented",
]

#: Entitätsattribut, das eine ausdrücklich synthetische Ergänzung kennzeichnet.
IDENTITY_ORIGIN_ATTRIBUTE = "identity_origin"
#: Wert des Attributs ``identity_origin`` für Quoten- und Floor-Replikate.
SYNTHETIC_SUPPLEMENT_MARKER = "synthetic_supplement"
#: Graph-Attribute, die eine Funktion oder Rolle tragen. ``position`` (Haltung)
#: und ``title`` (akademischer Titel) gehören bewusst nicht dazu.
FUNCTION_ATTRIBUTE_KEYS: tuple[str, ...] = (
    "current_role",
    "role",
    "function",
    "funktion",
    "occupation",
    "profession",
    "beruf",
    "job_title",
    "amt",
)

#: Obergrenze für Funktion und Abweichungsgrund; deckt sich mit
#: ``PersonaModel.generation_error``.
MAX_FUNCTION_CHARS = 200


class PersonaIdentityBinding(BaseModel):
    """Herkunft und Belegstand der Identität einer Persona."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: PersonaIdentityOrigin
    source_entity_uuid: Optional[str] = None
    source_name: str = Field(..., min_length=1)
    documented_function: Optional[str] = Field(default=None, max_length=MAX_FUNCTION_CHARS)
    function_evidence: FunctionEvidence = "none"
    gender_evidence: GenderEvidence = "none"
    unverifiable_reasons: list[UnverifiableReason] = Field(default_factory=list)
    role_deviation: Optional[str] = Field(default=None, max_length=MAX_FUNCTION_CHARS)

    @model_validator(mode="after")
    def _enforce_invariants(self) -> "PersonaIdentityBinding":
        has_function = self.documented_function is not None
        if has_function != (self.function_evidence != "none"):
            raise ValueError(
                "documented_function ist genau dann gesetzt, wenn function_evidence "
                "nicht 'none' ist"
            )
        if self.origin != "source_person" and (
            has_function
            or self.gender_evidence != "none"
            or self.role_deviation is not None
        ):
            raise ValueError(
                "Funktion, Geschlechtsevidenz und Rollenabweichung gibt es nur bei "
                "der Herkunft 'source_person'"
            )
        return self

    @property
    def name_is_locked(self) -> bool:
        """Name gehört der Quelle: kein Umbenennen durch Modell oder Dedup."""
        return self.origin in ("source_person", "source_collective")

    @property
    def is_verifiable(self) -> bool:
        """Keine offenen Gründe, die eine Prüfung der Bindung verhindern."""
        return not self.unverifiable_reasons
