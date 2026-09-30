"""The real-query evaluator keeps provisional labels out of approval metrics."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "jev_rollout_eval.py"
_SPEC = importlib.util.spec_from_file_location("jev_rollout_eval", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _files(tmp_path: Path) -> tuple[Path, Path, Path]:
    corpus_path, labels_path, probe_path = (
        tmp_path / "corpus.json", tmp_path / "labels.csv", tmp_path / "probe.json"
    )
    cases = [
        {"case_id": "a", "query": "PrivateQueryA", "fact": "PrivateFactA", "keyword_score": 10, "expected_relevant": None},
        {"case_id": "b", "query": "PrivateQueryB", "fact": "PrivateFactB", "keyword_score": 10, "expected_relevant": None},
    ]
    corpus_path.write_text(json.dumps({"cases": cases}))
    probe_path.write_text(json.dumps({
        "status": "complete",
        "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        "completed": [
            {"case_id": "a", "probability_yes": 0.8},
            {"case_id": "b", "probability_yes": 0.2},
        ],
    }))
    with labels_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "case_id", "query", "fact", "keyword_score", "jev_probability_yes",
            "relevant", "review_status",
        ])
        writer.writeheader()
        for case, probability, label in zip(cases, (0.8, 0.2), ("ja", "nein"), strict=True):
            writer.writerow({
                "case_id": case["case_id"], "query": case["query"], "fact": case["fact"],
                "keyword_score": case["keyword_score"], "jev_probability_yes": probability,
                "relevant": label, "review_status": "assistant_provisional",
            })
    return corpus_path, labels_path, probe_path


def test_default_rejects_assistant_labels(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="nur --exploratory"):
        _MODULE.evaluate(*_files(tmp_path))


def test_exploratory_counts_are_private_and_not_a_promotion(tmp_path: Path) -> None:
    report = _MODULE.evaluate(*_files(tmp_path), exploratory=True)
    assert report["status"] == "exploratory"
    assert report["promotion_eligible"] is False
    assert report["rule"] == {"tp": 1, "tn": 0, "fp": 1, "fn": 0}
    assert report["jev"] == {"tp": 1, "tn": 1, "fp": 0, "fn": 0}
    assert "PrivateQuery" not in json.dumps(report)
    assert "PrivateFact" not in json.dumps(report)


def test_refuses_mismatched_dataset(tmp_path: Path) -> None:
    corpus, labels, probe = _files(tmp_path)
    corpus.write_text(corpus.read_text() + " ")
    with pytest.raises(ValueError, match="passen nicht zusammen"):
        _MODULE.evaluate(corpus, labels, probe, exploratory=True)


def test_invalid_numeric_metadata_does_not_echo_private_value(tmp_path: Path) -> None:
    corpus, labels, probe = _files(tmp_path)
    original = labels.read_text()
    changed = original.replace(",10,0.8,", ",PrivateQuery,0.8,", 1)
    assert changed != original
    labels.write_text(changed)
    with pytest.raises(ValueError, match="Ungültige numerische Metadaten") as error:
        _MODULE.evaluate(corpus, labels, probe, exploratory=True)
    assert "PrivateQuery" not in str(error.value)
