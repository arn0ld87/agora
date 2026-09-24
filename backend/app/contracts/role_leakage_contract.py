"""Role-Leakage-Contract v1 (Pydantic v2).

Modelle für den Audit von Rollenvertauschungen in Simulationsaktionen.
Erstellt im Rahmen von Issue #1323 (Slice 5.1 — Simulationstreue).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


_STRICT = ConfigDict(extra="forbid")


class RoleConflict(BaseModel):
    """Eine einzelne erkannte Rollenvertauschung in einer Aktion."""

    model_config = _STRICT

    platform: str = Field(description="'twitter' oder 'reddit'")
    round: int = Field(ge=0, description="Simulationsrunde")
    agent_id: int = Field(description="Numerische Agent-ID aus dem Log")
    agent_name: str = Field(description="Name des Agenten aus dem Log")
    action_type: str = Field(description="z.B. CREATE_POST, CREATE_COMMENT, QUOTE_POST")
    excerpt: str = Field(
        max_length=200,
        description="Ausschnitt aus dem Aktionstext (max. 200 Zeichen)",
    )
    self_reference: str = Field(
        description="Extrahierte Selbstreferenz-Phrase aus dem Text"
    )
    matched_role: Optional[str] = Field(
        default=None,
        description="Fremde Rolle/Name, gegen die gematcht wurde (None bei unmatched_self_reference)",
    )
    reason: Literal["foreign_role", "foreign_name_signature", "unmatched_self_reference"] = Field(
        description=(
            "foreign_role: Selbstreferenz trifft fremde Persona-Rolle;\n"
            "foreign_name_signature: Namens-Signatur einer fremden Persona;\n"
            "unmatched_self_reference: Selbstreferenz, die weder eigene noch fremde Rolle trifft."
        )
    )


class RoleLeakagePlatformSummary(BaseModel):
    """Zusammenfassung je Plattform."""

    model_config = _STRICT

    platform: str
    text_actions: int = Field(ge=0, description="Texttragende Aktionen gesamt")
    conflicts: int = Field(ge=0, description="Erkannte Konflikte")
    rate: float = Field(ge=0.0, le=1.0, description="Konflikt-Rate (conflicts / text_actions)")
    by_reason: dict[str, int] = Field(
        default_factory=dict,
        description="Konfliktanzahl je reason-Kategorie",
    )


class RoleLeakageSummary(BaseModel):
    """Gesamtzusammenfassung eines Audit-Laufs."""

    model_config = _STRICT

    sim_dir: str = Field(description="Analysiertes Simulationsverzeichnis")
    text_actions: int = Field(ge=0, description="Texttragende Aktionen gesamt (alle Plattformen)")
    conflicts: int = Field(ge=0, description="Erkannte Konflikte gesamt")
    rate: float = Field(ge=0.0, le=1.0, description="Gesamt-Konflikt-Rate")
    by_reason: dict[str, int] = Field(
        default_factory=dict,
        description="Konfliktanzahl je reason-Kategorie (alle Plattformen)",
    )
    per_platform: list[RoleLeakagePlatformSummary] = Field(
        default_factory=list,
        description="Aufschlüsselung je Plattform",
    )
    examples: list[RoleConflict] = Field(
        default_factory=list,
        description="Ausgewählte Beispiele (bis max_examples)",
    )
