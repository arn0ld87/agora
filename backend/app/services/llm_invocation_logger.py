"""
LLM Invocation Logger.
Structured JSONL logging of LLM calls, ensuring secret hygiene.
"""

import os
import time
from typing import Optional
from ..contracts.llm_call_event_contract import LlmCallEvent
from ..utils.artifact_locator import ArtifactLocator
from .secret_resolver import SecretResolver

class LlmInvocationLogger:
    """Logs LLM invocation events to a structured JSONL file."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.log_path = os.path.join(ArtifactLocator.run_dir(run_id), "llm_call_events.jsonl")
        self.resolver = SecretResolver()

    def log_event(
        self,
        stage: str,
        provider_id: str,
        model: str,
        base_url: Optional[str],
        routing_version: int,
        latency_ms: float,
        success: bool,
        error_type: Optional[str] = None,
        http_status: Optional[int] = None,
        remote_request_id: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        reported_cost_micros: Optional[int] = None,
    ) -> None:
        """Append a call event to the log file.

        ``reported_cost_micros`` (f001, Slice `jev-budget`): fuer Aufrufer,
        die ihre Kosten bereits selbst — ueber dieselbe ``PricingRegistry`` —
        beziffert haben, aber auf dieser Schicht keine Rohtoken-Zahlen mehr
        kennen (z. B. ``DecisionResult.cost_micros`` eines Jev-Calls, siehe
        ``services/decisions/local_search_relevance.py``). ``run_usage_ledger
        ::_Bucket.add`` uebernimmt diesen Wert direkt statt ihn aus
        ``prompt_tokens``/``completion_tokens`` + Preistabelle zu
        rekonstruieren. ``None`` (Default) aendert nichts am bisherigen
        token-basierten Pfad.

        Codex-Review (PR #1742): die Zeile geht jetzt durch
        ``contracts.llm_call_event_contract.LlmCallEvent`` statt als
        handgeschriebenes Dict geschrieben zu werden — ein neues Feld auf
        dieser exportierten Grenze braucht damit ab sofort einen Vertrag
        statt eines weiteren ``event.get(...)`` beim Konsumenten.
        """
        event = LlmCallEvent(
            run_id=self.run_id,
            stage=stage,
            provider_id=provider_id,
            model=model,
            base_url_sanitized=self.resolver.sanitize_url(base_url),
            routing_version=routing_version,
            timestamp=time.time(),
            latency_ms=latency_ms,
            success=success,
            error_type=error_type,
            http_status=http_status,
            remote_request_id=remote_request_id,
            # Issue #764: Token-Usage fuer Budget-/Verbrauchsvertraege.
            # None = Provider hat keine Usage geliefert (ehrlich, nicht 0).
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reported_cost_micros=reported_cost_micros,
        )

        # Ensure log directory exists
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        with open(self.log_path, "a") as f:
            f.write(event.model_dump_json() + "\n")
