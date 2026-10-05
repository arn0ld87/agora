from __future__ import annotations

from typing import Literal, Any
from pydantic import BaseModel, Field, field_validator, model_validator

from ..contracts.simulation_activity_contract import ActorClass
from .simulation_activity_model import coerce_actor_class


def get_time_config_schema(num_entities: int) -> type[BaseModel]:
    class TimeConfigResponse(BaseModel):
        # #1772: Standard 24 h; kuerzere Laeufe sind erlaubt. Antworten ueber der
        # konfigurierten Obergrenze kommen hier noch durch und werden danach in
        # ``_parse_time_config`` sichtbar geklemmt (statt die ganze Antwort zu verwerfen).
        total_simulation_hours: int = Field(default=24, ge=1, le=168)
        minutes_per_round: int = Field(default=60, ge=30, le=120)
        agents_per_hour_min: int = Field(default=5, ge=1)
        agents_per_hour_max: int = Field(default=20, ge=1)
        peak_hours: list[int] = Field(default_factory=lambda: [18, 19, 20, 21, 22])
        off_peak_hours: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
        morning_hours: list[int] = Field(default_factory=lambda: [6, 7, 8])
        work_hours: list[int] = Field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16])
        reasoning: str = Field(default="")

        @model_validator(mode="after")
        def validate_agent_limits(self) -> TimeConfigResponse:
            # Verify and correct: ensure not exceeding total agents
            if self.agents_per_hour_min > num_entities:
                self.agents_per_hour_min = max(1, num_entities // 10)

            if self.agents_per_hour_max > num_entities:
                self.agents_per_hour_max = max(self.agents_per_hour_min + 1, num_entities // 2)

            # Ensure min < max
            if self.agents_per_hour_min >= self.agents_per_hour_max:
                self.agents_per_hour_min = max(1, self.agents_per_hour_max // 2)

            return self

    return TimeConfigResponse


class InitialPostSchema(BaseModel):
    content: str
    poster_type: str
    # Position des Posts zum Streitgegenstand (Issue #1759, A6). Optional:
    # fehlt sie, wird der Post beim Stance-Abgleich nicht geprüft.
    stance: Literal["supportive", "opposing", "neutral"] | None = None

    @field_validator("stance", mode="before")
    @classmethod
    def _normalize_stance(cls, value: Any) -> Any:
        """Freitext-Stance tolerant lesen; Unlesbares wird ``None``, nie ein Fehler.

        Ein ungültiger Wert dürfte nicht die gesamte Event-Config kippen
        (Fallback auf Default-Config), nur weil das optionale Feld abweicht.
        """
        if not isinstance(value, str):
            return None
        lowered = value.lower().strip()
        if "support" in lowered or lowered == "pro":
            return "supportive"
        if "oppos" in lowered or "skeptic" in lowered:
            return "opposing"
        if "neutral" in lowered:
            return "neutral"
        return None


class EventConfigResponse(BaseModel):
    hot_topics: list[str] = Field(default_factory=list)
    narrative_direction: str = Field(default="")
    initial_posts: list[InitialPostSchema] = Field(default_factory=list)
    reasoning: str = Field(default="")


class AgentActivityConfigSchema(BaseModel):
    agent_id: int
    activity_level: float = Field(default=0.5, ge=0.0, le=1.0)
    posts_per_hour: float = Field(default=1.0, ge=0.0)
    comments_per_hour: float = Field(default=2.0, ge=0.0)
    active_hours: list[int] = Field(default_factory=lambda: list(range(8, 23)))
    response_delay_min: int = Field(default=5, ge=0)
    response_delay_max: int = Field(default=60, ge=0)
    sentiment_bias: float = Field(default=0.0, ge=-1.0, le=1.0)
    stance: Literal["supportive", "opposing", "neutral", "observer"] = Field(default="neutral")
    influence_weight: float = Field(default=1.0, ge=0.0)
    # Akteursklasse (#1779). Fehlend oder ungültig wird ``None``, nie ein Fehler:
    # ein unlesbarer Wert dürfte nicht die ganze Antwort des Assistenten kippen.
    # ``_generate_agent_configs_batch`` setzt dann den Regel-Fallback und
    # protokolliert ihn. Die Raten setzt nie das Modell, nur die Klasse.
    actor_class: ActorClass | None = None

    @field_validator("actor_class", mode="before")
    @classmethod
    def _normalize_actor_class(cls, value: Any) -> ActorClass | None:
        return coerce_actor_class(value)

    @model_validator(mode="before")
    @classmethod
    def sanitize_stance(cls, data: Any) -> Any:
        if isinstance(data, dict):
            stance = data.get("stance")
            if isinstance(stance, str):
                stance_lower = stance.lower().strip()
                if "support" in stance_lower:
                    data["stance"] = "supportive"
                elif "oppos" in stance_lower or "skeptic" in stance_lower:
                    data["stance"] = "opposing"
                elif "observ" in stance_lower:
                    data["stance"] = "observer"
                else:
                    data["stance"] = "neutral"
        return data

    @model_validator(mode="after")
    def validate_delays(self) -> AgentActivityConfigSchema:
        if self.response_delay_min > self.response_delay_max:
            self.response_delay_min, self.response_delay_max = self.response_delay_max, self.response_delay_min
        return self


class AgentConfigsResponse(BaseModel):
    agent_configs: list[AgentActivityConfigSchema] = Field(default_factory=list)


class ContestedQuestionResponse(BaseModel):
    """LLM-Antwortschema für die Streitfrage des Laufs (Issue #1778, Schritt 1.4)."""

    has_contested_question: bool
    statement: str | None = None
    absence_reason: str | None = None
