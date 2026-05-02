"""Snapshot-Eval-Tests fuer Baseline-Metriken (Sub-Slice 17).

Vergleicht die berechneten Metriken pro Fixture gegen die committeten
Werte in expected_metrics.json. Drift -> Test failt mit klarem Diff.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contracts import EvidenceMapModel

import sys
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
from check_evidence_quality import evaluate, load_one  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXPECTED_PATH = Path(__file__).parent / "expected_metrics.json"

EXPECTED = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
FIXTURE_NAMES = sorted(EXPECTED.keys())


@pytest.fixture(scope="module")
def metrics() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for name in FIXTURE_NAMES:
        ev = load_one(FIXTURES_DIR / name, 2)
        assert ev is not None, f"Fixture {name} ist nicht ladbar"
        out[name] = evaluate(ev)
    return out


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_validates_against_pydantic(name: str) -> None:
    raw = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
    EvidenceMapModel.model_validate(raw)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_metrics_match_snapshot(name: str, metrics: dict[str, dict[str, float]]) -> None:
    actual = metrics[name]
    expected = EXPECTED[name]
    for key, exp_val in expected.items():
        act_val = round(float(actual[key]), 3)
        assert act_val == exp_val, (
            f"Drift in {name}.{key}: expected {exp_val}, got {act_val}. "
            f"Wenn diese Aenderung bewusst ist, expected_metrics.json updaten."
        )


def test_evaluate_output_keys() -> None:
    """check_evidence_quality.evaluate() muss alle Layer-5-Metriken liefern."""
    ev = load_one(FIXTURES_DIR / FIXTURE_NAMES[0], 2)
    assert ev is not None
    m = evaluate(ev)
    required = {
        "evidence_coverage", "claim_support_ratio", "orphan_claim_rate",
        "dedup_rate", "concentration_index", "total_claims",
    }
    missing = required - set(m.keys())
    assert not missing, f"Fehlende Metric-Keys: {missing}"
