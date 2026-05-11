"""
LLM Invocation Logger.
Structured JSONL logging of LLM calls, ensuring secret hygiene.
"""

import os
import json
import time
from typing import Optional, Dict, Any
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
    ) -> None:
        """Append a call event to the log file."""
        event = {
            "run_id": self.run_id,
            "stage": stage,
            "provider_id": provider_id,
            "model": model,
            "base_url_sanitized": self.resolver.sanitize_url(base_url),
            "routing_version": routing_version,
            "timestamp": time.time(),
            "latency_ms": latency_ms,
            "success": success,
            "error_type": error_type,
            "http_status": http_status,
            "remote_request_id": remote_request_id,
        }

        # Ensure log directory exists
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        with open(self.log_path, "a") as f:
            f.write(json.dumps(event) + "\n")
