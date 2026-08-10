"""Auflösung des Completion-Token-Limits (``max_tokens``) je Call.

Gegenstück zu :mod:`app.llm.context`, das dasselbe für Ollamas ``num_ctx``
tut. Hier geht es um das Ausgabelimit.

Hintergrund: Die Aufrufer im Backend hatten ihr ``max_tokens`` einzeln
gesetzt — 4096 für die Report-Sections, 16384 für das Outline, 1024 für
Interviews. Vier Kilotoken reichen für einen Abschnitt mit Belegen nicht,
und ein am Cap abgeschnittener Abschnitt ist als solcher im Report nicht
erkennbar. Deshalb hebt ein zentraler Boden alle generativen Calls an.

Zwei Grenzen, die der Boden respektieren muss:

1. **Das Ausgabelimit des Modells.** Ein Kontextfenster ist nicht das
   Ausgabelimit: ``gpt-4o`` nimmt 128k Tokens entgegen, gibt aber höchstens
   16.384 zurück und antwortet auf mehr mit ``400``. Der Boden wird deshalb
   pro Modell gedeckelt.
2. **Ollamas ``num_ctx``.** Dort ist ``max_tokens`` das ``num_predict`` und
   liegt im *selben* Fenster wie der Prompt. Ein Boden ohne mitziehendes
   ``num_ctx`` verdrängt den Prompt, statt mehr Ausgabe zu erlauben — siehe
   :func:`resolve_num_ctx_for_output`.

Abschalten: ``LLM_MAX_TOKENS_FLOOR=0`` stellt das alte Verhalten her
(jeder Aufrufer bekommt genau das, was er anfordert).
"""

from __future__ import annotations

import json
import os
from typing import Optional

from ..utils.logger import get_logger
from .context import heuristic_num_ctx_for_model

logger = get_logger("agora.llm_client")

#: Boden für generative Calls, wenn ``LLM_MAX_TOKENS_FLOOR`` nichts anderes sagt.
DEFAULT_MAX_TOKENS_FLOOR = 32768

#: Reserve für den Prompt, wenn ``num_ctx`` wegen eines hohen ``max_tokens``
#: angehoben wird. Deckt System-Prompt, Evidence-Kontext und Historie ab.
PROMPT_HEADROOM_TOKENS = 8192

#: Bekannte **Ausgabe**-Limits, nicht Kontextfenster — best effort per
#: Substring-Match wie in :mod:`app.llm.context`. Nur Modellfamilien, bei
#: denen ein zu hohes ``max_tokens`` ein hartes ``400`` produziert. Die
#: OpenAI-Reasoning-Familie (o1/o3/o4, GPT-5) steht bewusst nicht hier: ihre
#: Limits liegen weit über jedem realistischen Boden, ein Eintrag würde nur
#: Fehlmatch-Risiko ohne Nutzen einbringen.
#: Override per ``LLM_MODEL_OUTPUT_LIMITS_JSON`` (exakter Modellname → Limit).
_MODEL_OUTPUT_LIMITS: tuple[tuple[str, int], ...] = (
    ("gpt-4.1", 32_768),
    ("gpt-4o", 16_384),
    ("gpt-4-turbo", 4_096),
    ("gemini-3", 65_536),
    ("gemini-2.5", 65_536),
    ("gemini-2.0-flash", 8_192),
    ("claude-opus-4", 32_000),
    ("claude-sonnet-4", 64_000),
    ("claude-haiku-4", 64_000),
)


def model_output_limit(model: Optional[str]) -> Optional[int]:
    """Bekanntes Ausgabelimit für *model*, sonst ``None`` (kein Deckel).

    ``None`` heißt „unbekannt", nicht „unbegrenzt". Für lokale Modelle über
    Ollama ist das der Normalfall — dort begrenzt ``num_ctx``, nicht ein
    serverseitiges Ausgabelimit.
    """
    if not model:
        return None

    raw_per_model = os.environ.get("LLM_MODEL_OUTPUT_LIMITS_JSON", "").strip()
    if raw_per_model:
        try:
            parsed = json.loads(raw_per_model)
            if isinstance(parsed, dict) and model in parsed:
                return int(parsed[model])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    needle = model.lower()
    for prefix, limit in _MODEL_OUTPUT_LIMITS:
        if prefix in needle:
            return limit
    return None


def resolve_max_tokens_floor() -> int:
    """Aktiver Boden aus ``LLM_MAX_TOKENS_FLOOR``; ``0`` schaltet ihn ab."""
    raw = os.environ.get("LLM_MAX_TOKENS_FLOOR")
    if raw is None or not raw.strip():
        return DEFAULT_MAX_TOKENS_FLOOR
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "LLM_MAX_TOKENS_FLOOR=%r ist keine Zahl — nutze Default %d.",
            raw,
            DEFAULT_MAX_TOKENS_FLOOR,
        )
        return DEFAULT_MAX_TOKENS_FLOOR
    return max(0, value)


def resolve_max_tokens(
    requested: int,
    *,
    model: Optional[str],
    enforce_floor: bool = True,
) -> int:
    """Effektives ``max_tokens`` für einen Call.

    Hebt *requested* auf den Boden an und deckelt das Ergebnis am bekannten
    Ausgabelimit des Modells. Der Deckel greift auch bei
    ``enforce_floor=False`` — ein Aufrufer, der von sich aus mehr anfordert,
    als das Modell liefern kann, bekommt sonst ein ``400`` statt einer
    Antwort.

    ``enforce_floor=False`` ist für Calls gedacht, deren enges Limit Absicht
    ist: Klassifikation, Label-Ausgabe, Ein-Wort-Antworten. Dort erlaubt ein
    hoher Boden nur zusätzliches Geschwafel.
    """
    effective = int(requested)
    if enforce_floor:
        effective = max(effective, resolve_max_tokens_floor())

    limit = model_output_limit(model)
    if limit is not None and effective > limit:
        logger.debug(
            "resolve_max_tokens: %d auf Ausgabelimit %d gedeckelt (model=%s).",
            effective,
            limit,
            model,
        )
        effective = limit

    return max(1, effective)


def resolve_num_ctx_for_output(
    num_ctx: Optional[int],
    max_tokens: int,
    *,
    model: Optional[str],
) -> Optional[int]:
    """Hebt ``num_ctx`` an, damit *max_tokens* Ausgabe überhaupt Platz hat.

    Bei Ollama teilen Prompt und Ausgabe ein Fenster. Ein ``num_predict`` nahe
    ``num_ctx`` lässt keinen Platz für den Prompt — das Ergebnis ist ein
    stillschweigend abgeschnittener Kontext, nicht mehr Ausgabe.

    Angehoben wird auf ``max_tokens + PROMPT_HEADROOM_TOKENS``, gedeckelt am
    bekannten Kontextfenster des Modells. Ein bereits größeres ``num_ctx``
    bleibt unangetastet, ``None``/``0`` ebenso — dort entscheidet der
    Aufrufer bewusst nichts.
    """
    if not num_ctx:
        return num_ctx

    needed = int(max_tokens) + PROMPT_HEADROOM_TOKENS
    ctx_limit = heuristic_num_ctx_for_model(model or "")
    if ctx_limit is not None:
        needed = min(needed, ctx_limit)
    return max(int(num_ctx), needed)
