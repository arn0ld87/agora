"""Aktivitätsmodell einer Simulation (Issue #1779, Schritt 2.4).

Die Simulation entscheidet je Runde, welche Agenten schreiben. Bisher stand
dafür ein Zufallsmodell ohne Bezug zu beobachteten Raten (``activity_level``,
``agents_per_hour_min/max``). Das Aktivitätsmodell ersetzt es durch Tagesraten
je Akteursklasse und ein Stundenprofil. Die Zahlen und ihre Quellen stehen in
``app/services/simulation_activity_model.py`` und in
``docs/research/simulation-aktivitaet-belege.md``.

Das serialisierte Modell steht in ``simulation_config.json`` unter
``time_config.activity_model``. Fehlt das Feld (Konfigurationen vor diesem
Schritt), gilt der bisherige Auswahlpfad unverändert.

Das Modell beschreibt eine Annahme über Schreibraten, keine Vorhersage
menschlichen Verhaltens.
"""

from enum import Enum
from typing import Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: Ein Tag hat 24 Stunden; das Stundenprofil trägt je Stunde ein Gewicht.
HOURS_PER_DAY = 24
#: Zulässige Abweichung der Gewichtssumme von 1,0.
HOURLY_WEIGHT_SUM_TOLERANCE = 1e-6


class ActivityMode(str, Enum):
    """Satz der Tagesraten, den eine Simulation verwendet.

    Beide Modi rechnen mit einer Stunde je Runde und demselben Stundenprofil;
    sie unterscheiden sich nur im Satz der Tagesraten.
    """

    #: Möglichst realistisch, an belegten Mittelwerten ausgerichtet.
    REALISTIC = "realistic"
    #: Aktive Akteure: Raten am oberen Ende der belegten Spanne.
    ACTIVE = "active"


class ActorClass(str, Enum):
    """Akteursklasse eines Agenten; sie bestimmt seine Tagesrate."""

    INDIVIDUAL = "individual"
    POLITICIAN = "politician"
    AUTHORITY = "authority"
    ORGANISATION = "organisation"
    MEDIA = "media"


class ActivityModelConfig(BaseModel):
    """Aktivitätsmodell: Tagesraten je Akteursklasse, Stundenprofil, Obergrenzen."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    mode: ActivityMode
    #: Höchstzahl Textaktionen (Beitrag, Kommentar, Zitat) je Aktivierung.
    max_text_actions_per_activation: int = Field(ge=1)
    #: Höchstzahl Reaktionen (Like, Dislike, Repost, Follow, Mute) je Aktivierung.
    max_reactions_per_activation: int = Field(ge=0)
    #: Textbeiträge je Tag und Akteur; der Satz des gewählten Modus.
    text_posts_per_day: Dict[ActorClass, float]
    #: Anteil der Tagesrate je Ortszeit-Stunde 0 bis 23; Summe 1,0.
    hourly_weights: List[float]

    @field_validator("text_posts_per_day")
    @classmethod
    def _rates_cover_all_classes_and_are_non_negative(
        cls, value: Dict[ActorClass, float]
    ) -> Dict[ActorClass, float]:
        missing = [item.value for item in ActorClass if item not in value]
        if missing:
            raise ValueError(f"text_posts_per_day fehlt für: {', '.join(missing)}")
        negative = [item.value for item, rate in value.items() if rate < 0]
        if negative:
            raise ValueError(f"text_posts_per_day darf nicht negativ sein: {', '.join(negative)}")
        return value

    @model_validator(mode="after")
    def _hourly_weights_form_a_day(self) -> "ActivityModelConfig":
        if len(self.hourly_weights) != HOURS_PER_DAY:
            raise ValueError(
                f"hourly_weights braucht genau {HOURS_PER_DAY} Werte, "
                f"gefunden {len(self.hourly_weights)}"
            )
        if any(weight < 0 for weight in self.hourly_weights):
            raise ValueError("hourly_weights darf keine negativen Werte enthalten")
        total = sum(self.hourly_weights)
        if abs(total - 1.0) > HOURLY_WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"hourly_weights muss die Summe 1,0 ergeben, gefunden {total!r}")
        return self
