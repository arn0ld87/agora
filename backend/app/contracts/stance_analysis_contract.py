"""Haltung der Stimmen zur Streitfrage (Issue #1778, Schritt 1.8).

Vor dem Schreiben der Abschnitte wird jeder Simulationsbeitrag einmal nach
seiner Haltung zur Streitfrage klassifiziert. Daraus entstehen die
Positionierungsquote (Anteil der Stimmen, die in der Simulation Stellung
beziehen) und die Lagerverteilung. Das Ergebnis liegt als
``stance_analysis.json`` im Berichtsverzeichnis.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

#: Haltung zur Streitfrage. ``in_favour`` heißt: die Aussage soll eintreten.
StanceClass = Literal["in_favour", "opposed", "undecided"]


class ClassifiedContribution(BaseModel):
    """Ein Simulationsbeitrag mit seiner klassifizierten Haltung."""

    model_config = ConfigDict(extra="forbid")

    agent_id: int
    agent_name: str
    platform: str
    round_num: int
    action_type: str
    #: Identität des Beitrags, gleich dem ``producer_key`` seines Belegs.
    producer_key: str
    stance_class: StanceClass


class VoiceStance(BaseModel):
    """Haltung einer Stimme: Startwert, Beiträge und Interview."""

    model_config = ConfigDict(extra="forbid")

    voice_key: str
    agent_name: str
    role_family: Optional[str] = None
    #: Haltung aus der Simulationskonfiguration (``agent_configs[].stance``).
    start_class: StanceClass
    #: Klassifizierte Haltung je Beitrag, in der Reihenfolge der Beiträge.
    contribution_classes: list[StanceClass] = Field(default_factory=list)
    interview_class: Optional[StanceClass] = None


class StanceAnalysis(BaseModel):
    """Positionierungsquote und Lagerverteilung eines Laufs."""

    model_config = ConfigDict(extra="forbid")

    contested_statement: Optional[str] = None
    #: ``False``, wenn der Lauf keine Streitfrage hat.
    applicable: bool
    voices_total: int = Field(default=0, ge=0)
    #: Stimmen mit mindestens einem Beitrag ``in_favour`` oder ``opposed``.
    voices_positioned: int = Field(default=0, ge=0)
    positioning_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    camp_distribution: dict[StanceClass, int] = Field(default_factory=dict)
    voices: list[VoiceStance] = Field(default_factory=list)
    contributions: list[ClassifiedContribution] = Field(default_factory=list)
    #: Beiträge mit klassifizierter Haltung.
    classified_total: int = Field(default=0, ge=0)
    #: Beiträge, deren Klassifikation ausfiel.
    classification_failed: int = Field(default=0, ge=0)
