"""LLM-Judge für das Evidence-Entailment (ADR-0002).

``classify_evidence(judge=...)`` in ``evidence_entailment.py`` befragt einen
optionalen LLM-Judge im qualitativen Pfad — also nur dann, wenn die
deterministischen Checks (Zahl, Bezugsgruppe, Mengenaussage) kein Urteil
fällen konnten. Dieser Builder verdrahtet ``LLMClient.chat_json`` als
Judge-Quelle, ohne einen neuen Provider-Pfad zu öffnen.

ADR-0002-Anker (im Regelpfad von ``classify_evidence`` bereits erzwungen):
Der Judge darf ein SUPPORTED nur **abschwächen**, nie erzeugen. ``chat_json``
liefert strukturierte Verdicts; ``classify_evidence`` wandelt ein
Judge-SUPPORTED in RELATED_ONLY um. Dieser Builder erzwingt das nicht erneut —
die Verteidigungslinie liegt im Klassifikator, nicht im Judge.

Bewusst optional und nicht in der Report-Pipeline voreingestellt: ein
Judge-Call pro qualitativem Evidence-Item ist teuer. Die Verdrahtung ist ein
Konfigurationsschritt, nicht Default (Issue #931-Kontext: Kosten-, Token- und
Zeitbudgets stehen auf der 0.9→0.10-Roadmap).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ..llm.client import LLMClient
from .evidence_entailment import EntailmentJudge, EntailmentVerdict

logger = logging.getLogger(__name__)


class EntailmentJudgeVerdict(BaseModel):
    """Strukturiertes Judge-Output-Schema für ``chat_json``."""

    verdict: EntailmentVerdict = Field(
        description=(
            "SUPPORTED, CONTRADICTED, RELATED_ONLY oder INSUFFICIENT. "
            "SUPPORTED wird vom Klassifikator auf RELATED_ONLY abgeschwächt "
            "(ADR-0002: Judge darf SUPPORTED nie erzeugen)."
        )
    )
    reason: str = Field(
        default="",
        description="Kurze Begründung des Urteils (ein Satz).",
    )


_JUDGE_SYSTEM_PROMPT = (
    "Du bist ein strenger Entailment-Judge. Du erhältst einen Claim und einen "
    "Evidence-Text. Entscheide, ob die Evidence den Claim *trägt* — nicht nur, "
    "ob sie thematisch verwandt sind.\n\n"
    "Urteile:\n"
    "- SUPPORTED: Die Evidence belegt den Claim vollständig (Zahl, "
    "Bezugsgruppe, Aussage).\n"
    "- CONTRADICTED: Die Evidence widerspricht dem Claim (falsche Zahl, "
    "gegenläufige Richtung, andere Bezugsgruppe).\n"
    "- RELATED_ONLY: Gleiche Thema, aber kein Beleg.\n"
    "- INSUFFICIENT: Zu wenig Überschneidung für ein Urteil.\n\n"
    "Sei konservativ: wenn die Evidence eine Zusatzbehauptung trägt, die der "
    "Claim nicht abdeckt, wähle RELATED_ONLY oder CONTRADICTED — nie SUPPORTED."
)


def build_llm_judge(
    client: LLMClient,
    *,
    logger: Optional[logging.Logger] = None,
) -> EntailmentJudge:
    """Baut einen ``EntailmentJudge`` aus einem ``LLMClient``.

    Der Judge ist ein Callable ``(claim, evidence_text) -> verdict_name``. Er
    nutzt ``chat_json`` mit dem ``EntailmentJudgeVerdict``-Schema, damit der
    Provider strukturiert antwortet und Pydantic den Verdict-Wert validiert.

    Raises werden im Klassifikator gefangen (``judge_failed``-Check), der
    Builder selbst liefert immer ein Callable — fehlerhafte Calls fallen
    kontrolliert auf den Regelpfad zurück.
    """

    log = logger or logging.getLogger(__name__)

    def judge(claim: str, evidence_text: str) -> str:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Claim: {claim}\n\n"
                    f"Evidence: {evidence_text}\n\n"
                    "Urteil (verdict) und kurze Begründung (reason)."
                ),
            },
        ]
        try:
            result = client.chat_json(
                messages=messages,
                schema=EntailmentJudgeVerdict,
                schema_name="entailment_judge_verdict",
                context="report",
                temperature=0.0,
                max_tokens=256,
                # Der Judge gibt ein Label plus eine kurze Begründung zurück.
                # Ein hoher Token-Boden erlaubt hier nur Geschwafel und kostet
                # bei lokalen Modellen Laufzeit — enges Limit ist Absicht.
                enforce_token_floor=False,
            )
        except Exception as exc:  # noqa: BLE001 — Judge-Fehler fallen auf Regelpfad
            # Nur den Exception-Typ loggen: repr(exc) kann Provider-Response-
            # oder Prompt-Fragmente in die Logs ziehen.
            log.debug(
                "Entailment-Judge: chat_json fehlgeschlagen (%s)",
                type(exc).__name__,
            )
            raise

        # chat_json mit Pydantic-Schema liefert ein validiertes Dict. Je nach
        # Serialization-Mode kann verdict ein EntailmentVerdict-Enum (python)
        # oder ein String (json) sein. Beide Fälle abdecken.
        verdict_raw = result.get("verdict") if isinstance(result, dict) else None
        if verdict_raw is None:
            raise ValueError(f"Judge-Antwort ohne 'verdict': {result!r}")
        if isinstance(verdict_raw, EntailmentVerdict):
            return verdict_raw.value
        return str(verdict_raw)

    return judge


__all__ = ["EntailmentJudgeVerdict", "build_llm_judge"]