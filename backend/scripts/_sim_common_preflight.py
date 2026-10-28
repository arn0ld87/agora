"""Preflight chat completion model probe before agent fan-out."""

import logging
import os
import time
from typing import Any

logger = logging.getLogger("agora._sim_common")

_PERMANENT_STATUS = {401, 403, 404}
_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 599}


def _should_skip_preflight() -> bool:
    """True, wenn der Preflight-Probe per AGORA_SKIP_PREFLIGHT=1 deaktiviert ist."""
    return os.environ.get("AGORA_SKIP_PREFLIGHT", "0") == "1"


def preflight_model_probe(
    model: Any,
    *,
    max_retries: int = 3,
    backoff_base: float = 0.2,
) -> None:
    """Führt vor der Simulation eine kleine Chat-Completion-Probe für das Modell aus."""
    if _should_skip_preflight():
        logger.warning(
            "preflight probe skipped via AGORA_SKIP_PREFLIGHT",
            extra={"event": "preflight_skipped", "env": "AGORA_SKIP_PREFLIGHT"},
        )
        return

    import openai

    probe_messages = [{"role": "user", "content": "ping"}]
    for attempt in range(max_retries + 1):
        try:
            model.run(probe_messages)
            return
        except openai.APIStatusError as exc:
            status = getattr(exc, "status_code", None)
            if status in _PERMANENT_STATUS:
                raise ValueError(
                    f"OASIS-Preflight: permanenter Provider-Fehler "
                    f"(HTTP {status}) für die aufgelöste Route — Simulation "
                    f"vor dem Fan-out abgelehnt. Ursache: {exc}"
                ) from exc
            if status in _TRANSIENT_STATUS and attempt < max_retries:
                time.sleep(backoff_base * (2 ** attempt))
                continue
            raise ValueError(
                f"OASIS-Preflight: Provider-Fehler (HTTP {status}) ließ sich "
                f"nach {attempt + 1} Versuch(en) nicht beheben — Simulation "
                f"vor dem Fan-out abgelehnt. Ursache: {exc}"
            ) from exc
