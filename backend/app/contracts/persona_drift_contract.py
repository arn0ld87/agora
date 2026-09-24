"""Vertrag fuer die Persona-Drift-Korrektur (#1471, Nachtrag).

``PersonaDriftCorrectionSchema`` ist eine LLM-Antwort — sie wird an
``LLMClient.chat_json(schema=...)`` uebergeben (siehe
``app/services/oasis_profile_llm.py::_regenerate_persona_after_drift``) — und
gehoert damit nach Repo-Regel "Contracts-first" hierher statt in ein
Service-Modul. Bis zu diesem Slice lag sie in
``app/services/oasis_profile_models.py``, das weiterhin von dort reexportiert
(Codex-Finding F1 auf PR #1573).

Schlanker als ``PersonaProfileSchema`` in ``persona_contract.py``, weil Name,
Alter, Geschlecht und MBTI-Typ der Persona bei einer Drift-Korrektur
unveraendert bleiben und nicht neu angefordert werden.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .persona_contract import VoiceRegister

_STRICT = ConfigDict(extra="forbid")


class PersonaDriftCorrectionSchema(BaseModel):
    """Antwortvertrag für die Drift-Korrektur (#1471, Nachtrag).

    Bei erkannter Domänendrift leerte ``_persona_after_coherence_check``
    bisher nur ``profession``; Bio und Freitext behielten ihr fachfremdes
    Vokabular. Dieses Schema trägt die vom Modell korrigierte Fassung —
    schlanker als ``PersonaProfileSchema``, weil Name, Alter, Geschlecht und
    MBTI-Typ der Persona unverändert bleiben und nicht neu angefordert
    werden.
    """

    model_config = _STRICT

    bio: str = Field("", description="Korrigierte Social-Media-Bio, <=200 Zeichen")
    persona: str = Field("", description="Korrigierter Freitext, durchgehend Fließtext")
    profession: str = Field(
        "", description="Korrigierter Beruf; leerer String, wenn aus der Quelle keiner ableitbar ist"
    )
    voice_register: Optional[VoiceRegister] = Field(
        None, description="One of formal-de/neutral-de/technical-de/skeptisch-de"
    )


__all__ = ["PersonaDriftCorrectionSchema"]
