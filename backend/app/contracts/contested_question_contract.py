"""Streitfrage eines Laufs (siehe CONTEXT.md, Abschnitt Streitfrage)."""
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContestedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Bejah- oder verneinbare Aussage. ``None``, wenn der Lauf keine hat.
    statement: Optional[str] = Field(default=None, min_length=10, max_length=300)
    #: Wer die Streitfrage festgelegt hat.
    origin: Literal["assistant", "user", "none"] = "none"
    #: Begründung, wenn es keine Streitfrage gibt.
    absence_reason: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _consistent(self) -> "ContestedQuestion":
        if self.origin == "none" and self.statement is not None:
            raise ValueError("origin=none verlangt statement=None")
        if self.origin != "none" and self.statement is None:
            raise ValueError("origin assistant/user verlangt ein statement")
        return self
