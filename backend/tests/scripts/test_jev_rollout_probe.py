"""Safety properties of the unlabelled real-query Jev probe."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.contracts.decision_contract import DecisionResult
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "jev_rollout_probe.py"
_SPEC = importlib.util.spec_from_file_location("jev_rollout_probe", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
load_cases = _MODULE.load_cases
probe = _MODULE.probe


def _case(case_id="c001", expected_relevant=None):
    return {"case_id": case_id, "query": "Privatfrage", "fact": "Privatfakt", "expected_relevant": expected_relevant}


def test_load_cases_rejects_labels_and_more_than_30(tmp_path):
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps({"cases": [_case(expected_relevant=True)]}))
    with pytest.raises(ValueError, match="ungelabelte"):
        load_cases(corpus)
    corpus.write_text(json.dumps({"cases": [_case(f"c{i:03}") for i in range(31)]}))
    with pytest.raises(ValueError, match="30 Fälle"):
        load_cases(corpus)


def test_probe_emits_only_case_id_and_decision_metadata():
    class FakeProvider:
        def decide(self, state, question):
            assert state.state["assertion"] == "Der Fakt ist für die Suchanfrage relevant."
            return DecisionResult(
                use_case_id="local-search-relevance",
                provider="jev",
                answer=None,
                probability_yes=0.8,
                confidence=0.6,
                model_version="jev-1.13.0",
                latency_ms=12,
                cost_micros=3,
                shadow=False,
            )

    report = probe([_case()], FakeProvider())
    serialized = json.dumps(report)
    assert report["status"] == "complete"
    assert "Privatfrage" not in serialized
    assert "Privatfakt" not in serialized
    assert report["completed"][0]["probability_yes"] == 0.8


def test_probe_stops_on_error_without_exposing_exception_text():
    class FailingProvider:
        def decide(self, state, question):
            raise RuntimeError("Privatfakt")

    report = probe([_case()], FailingProvider())
    assert report["status"] == "failed"
    assert report["failed_case_id"] == "c001"
    assert "Privatfakt" not in json.dumps(report)
