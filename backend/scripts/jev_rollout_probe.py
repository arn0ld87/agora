"""Bounded, unlabelled Jev probe on the private real-query rollout corpus.

Input stays local. The caller must keep JSON output private: request IDs and
per-case predictions are useful for later maintainer review, but raw query and
fact text are intentionally absent. No quality metric is possible before labels.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from typesafe_sdk import TypeSafeClient

from app.contracts.decision_contract import DecisionState, NoulQuestion
from app.services.decisions.jev_provider import JEV_PINNED_MODEL_VERSION, JevDecisionProvider
from app.services.decisions.local_search_relevance import RELEVANCE_ASSERTION

_USE_CASE_ID = "local-search-relevance"
_MAX_CASES = 30


def load_cases(path: Path) -> tuple[str, list[dict[str, Any]]]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    cases = payload["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= _MAX_CASES:
        raise ValueError("Korpus muss zwischen 1 und 30 Fälle enthalten")
    seen: set[str] = set()
    for case in cases:
        case_id = case["case_id"]
        if not isinstance(case_id, str) or re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", case_id) is None:
            raise ValueError("Ungültige Fall-ID")
        if case_id in seen:
            raise ValueError("Doppelte Fall-ID")
        seen.add(case_id)
        if case.get("expected_relevant") is not None:
            raise ValueError("Dieser Probelauf akzeptiert nur ungelabelte Fälle")
        if not all(isinstance(case.get(field), str) and case[field].strip() for field in ("query", "fact")):
            raise ValueError("Query und Fakt müssen nichtleere Strings sein")
    return hashlib.sha256(raw).hexdigest(), cases


def probe(cases: list[dict[str, Any]], provider: JevDecisionProvider) -> dict[str, Any]:
    outcomes: list[dict[str, Any]] = []
    for case in cases:
        state = DecisionState(
            use_case_id=_USE_CASE_ID,
            state={
                "assertion": RELEVANCE_ASSERTION,
                "query": case["query"],
                "fact": case["fact"],
            },
            context_hash=hashlib.sha256(
                f"{case['query']}\0{case['fact']}".encode()
            ).hexdigest(),
        )
        try:
            result = provider.decide(state, NoulQuestion())
        except Exception as exc:  # noqa: BLE001 - only the exception type is retained
            return {
                "status": "failed",
                "completed": outcomes,
                "failed_case_id": case["case_id"],
                "error_type": type(exc).__name__,
            }
        outcomes.append(
            {
                "case_id": case["case_id"],
                "probability_yes": result.probability_yes,
                "latency_ms": result.latency_ms,
                "cost_micros": result.cost_micros,
                "model_version": result.model_version,
                "request_id": result.request_id,
            }
        )
    return {"status": "complete", "completed": outcomes}


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("Aufruf: python scripts/jev_rollout_probe.py PRIVATE_CORPUS_JSON\n")
        return 2
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        sys.stderr.write("TYPESAFE_API_KEY fehlt\n")
        return 2
    corpus_hash, cases = load_cases(Path(sys.argv[1]))
    provider = JevDecisionProvider(TypeSafeClient(api_key=key, model=JEV_PINNED_MODEL_VERSION, timeout=30.0))
    report = probe(cases, provider)
    report.update(corpus_sha256=corpus_hash, requested=len(cases), use_case_id=_USE_CASE_ID)
    sys.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
