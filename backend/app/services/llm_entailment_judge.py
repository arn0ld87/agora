"""LLM-Judge für das Evidence-Entailment (ADR-0002).

``classify_evidence(judge=...)`` in ``evidence_entailment.py`` befragt einen
optionalen LLM-Judge im qualitativen Pfad — also nur dann, wenn die
deterministischen Checks (Zahl, Bezugsgruppe, Mengenaussage) kein Urteil
fällen konnten. Dieser Builder verdrahtet ``LLMClient.chat_json`` als
Judge-Quelle, ohne einen neuen Provider-Pfad zu öffnen.

Seit #1357 darf der Judge in der Grauzone ein SUPPORTED **erzeugen**
(``docs/decisions/0002-supersedes.md``). Der alte Deckel war sinnvoll, solange
Regel 3 selbst großzügig SUPPORTED vergab; jetzt wäre er das Gegenteil — ohne
den Judge bliebe die Grauzone dauerhaft bei RELATED_ONLY, und Persona-Interviews,
deren lexikalische Deckung nie über 0.29 kommt, könnten nie binden.

Der Judge ist damit die einzige Stelle des Systems, die inhaltlich statt
lexikalisch urteilt — und deshalb bewusst konservativ instruiert. Die
deterministischen Regeln 1 und 2 (Zahl, Bezugsgruppe, Mengenaussage) bleiben
unberührt bindend; ein regelbasiertes CONTRADICTED erreicht den Judge nie.

Gefragt wird er nur in der Grauzone und nur für die höchstbewerteten
Retrieval-Kandidaten eines Claims — im Fließtext-Check gar nicht, weil dort
ausschließlich numerische Sätze geprüft werden.
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
        description="SUPPORTED, CONTRADICTED, RELATED_ONLY oder INSUFFICIENT."
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
    "Du wirst nur in Zweifelsfällen gefragt: die Wortüberschneidung reicht "
    "weder zum Beleg noch zum Ausschluss. Entscheide inhaltlich, nicht nach "
    "Wortgleichheit.\n\n"
    "Sei konservativ. SUPPORTED nur, wenn ein Leser die Aussage des Claims "
    "allein aus diesem Evidence-Text ableiten könnte. Trägt der Claim eine "
    "zusätzliche Behauptung, die im Text nicht steht — eine zweite Wirkung, "
    "eine Bewertung, eine Verallgemeinerung über die genannte Gruppe hinaus —, "
    "dann wähle RELATED_ONLY.\n\n"
    "Eine einzelne geäußerte Sicht belegt, dass diese Sicht geäußert wurde, "
    "nicht dass sie zutrifft. Behauptet der Claim eine Tatsache und nennt die "
    "Evidence nur eine Einschätzung dazu, ist das RELATED_ONLY."
)


#: Die vier Urteilsnamen, längster zuerst. ``RELATED_ONLY`` enthält kein
#: anderes Verdikt als Teilwort, aber die Reihenfolge hält die Suche auch
#: dann eindeutig, wenn die Enum wächst.
_VERDICT_NAMES = ("RELATED_ONLY", "CONTRADICTED", "INSUFFICIENT", "SUPPORTED")


def _verdict_from_prose(
    client: LLMClient,
    messages: List[Dict[str, str]],
    log: logging.Logger,
) -> str:
    """Zweiter Versuch als Freitext, wenn der Provider kein JSON liefert.

    Nicht jedes Modell hält sich an ein json_schema, und mit
    ``LLM_DISABLE_JSON_MODE`` fällt der erzwungene Modus ohnehin weg. Gemessen
    an den fünf im Entwicklungssetup verfügbaren Ollama-Cloud-Modellen
    antwortete genau eines strukturiert; die übrigen vier lieferten eine
    saubere, aber prosaische Begründung ("**Urteil:** RELATED_ONLY — die
    Evidence thematisiert zwar …"). Ohne diesen zweiten Versuch wäre der
    Judge in vier von fünf Konfigurationen dauerhaft im ``judge_failed``-Pfad
    und die Grauzone bliebe leer, obwohl das Modell inhaltlich korrekt
    geurteilt hat.

    Gelesen wird ausschließlich der Urteilsname. Die Begründung bleibt außen
    vor: sie wäre nicht validierbar und der Klassifikator führt seine eigene.
    Findet sich kein oder mehr als ein Name, wird nichts geraten — der
    Aufrufer sieht dann denselben Fehler wie zuvor und fällt auf den
    Regelpfad.
    """
    response = client.chat(
        messages=messages,
        temperature=0.0,
        # Großzügiger als der JSON-Weg: ein Reasoning-Modell verbraucht sein
        # Budget im Denkteil und liefert sonst eine leere Antwort, bevor das
        # Urteil überhaupt fällt.
        max_tokens=1024,
        force_no_thinking=True,
        enforce_token_floor=False,
    )
    upper = str(response or "").upper()
    found = [name for name in _VERDICT_NAMES if name in upper]
    if len(found) != 1:
        raise ValueError(
            "Judge-Antwort ohne eindeutiges Urteil "
            f"({len(found)} Treffer in {len(upper)} Zeichen)"
        )
    log.debug("Entailment-Judge: Urteil aus Freitext gelesen")
    return found[0]


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
            return _verdict_from_prose(client, messages, log)

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