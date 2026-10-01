"""Offline comparison for the private real-query Jev proxy corpus.

The result is never a promotion decision. Assistant labels require an explicit
exploratory flag; even maintainer-reviewed labels still need an independent
holdout and a representative sample before rollout.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from app.contracts.decision_contract import DecisionState, NoulQuestion
from app.services.decisions.local_search_relevance import _relevance_rule


def _by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {str(item["case_id"]): item for item in items}
    if len(result) != len(items):
        raise ValueError("Fall-IDs sind nicht eindeutig")
    return result


def _load_and_check(
    corpus_path: Path, labels_path: Path, probe_path: Path
) -> tuple[str, dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    raw = corpus_path.read_bytes()
    corpus = json.loads(raw)
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    with labels_path.open(newline="", encoding="utf-8") as stream:
        rows: list[dict[str, Any]] = list(csv.DictReader(stream))
    if probe.get("status") != "complete" or probe.get("corpus_sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError("Probelauf und Korpus passen nicht zusammen")
    cases = _by_id(corpus["cases"])
    answers = _by_id(probe["completed"])
    labels = _by_id(rows)
    if not cases or set(cases) != set(answers) or set(cases) != set(labels):
        raise ValueError("Fall-IDs in Korpus, Probelauf und Labels weichen ab")
    for case_id, row in labels.items():
        case, answer = cases[case_id], answers[case_id]
        try:
            score = int(row["keyword_score"])
            probability = float(row["jev_probability_yes"])
        except (TypeError, ValueError):
            raise ValueError("Ungültige numerische Metadaten") from None
        if (
            row["query"] != case["query"]
            or row["fact"] != case["fact"]
            or score != case["keyword_score"]
            or probability != answer["probability_yes"]
            or case["expected_relevant"] is not None
        ):
            raise ValueError("Labeltabelle und private Falldaten weichen ab")
    return hashlib.sha256(raw).hexdigest(), cases, answers, rows


def _confusion(pairs: list[tuple[bool, bool]]) -> dict[str, int]:
    return {
        "tp": sum(actual and predicted for actual, predicted in pairs),
        "tn": sum(not actual and not predicted for actual, predicted in pairs),
        "fp": sum(not actual and predicted for actual, predicted in pairs),
        "fn": sum(actual and not predicted for actual, predicted in pairs),
    }


def _rule_prediction(score: int) -> bool:
    state = DecisionState(
        use_case_id="local-search-relevance", state={"top_score": score}, context_hash="offline-eval"
    )
    probability = _relevance_rule(state, NoulQuestion()).probability_yes
    if probability is None:
        raise ValueError("Rule-Provider lieferte keine Wahrscheinlichkeit")
    return probability >= 0.5


def evaluate(
    corpus_path: Path, labels_path: Path, probe_path: Path, *, exploratory: bool = False
) -> dict[str, Any]:
    dataset_hash, cases, answers, rows = _load_and_check(corpus_path, labels_path, probe_path)
    if any(row["relevant"] not in {"ja", "nein", "unklar"} for row in rows):
        raise ValueError("Alle Labels müssen ja, nein oder unklar sein")
    if not exploratory and any(
        row["review_status"] != "maintainer_reviewed" or row["relevant"] == "unklar"
        for row in rows
    ):
        raise ValueError("Nicht bestätigte oder unklare Labels: nur --exploratory zulässig")
    if exploratory and any(
        row["review_status"] not in {"assistant_provisional", "maintainer_reviewed"}
        for row in rows
    ):
        raise ValueError("Unbekannte Label-Provenienz")
    certain = [row for row in rows if row["relevant"] != "unklar"]
    if not certain:
        raise ValueError("Keine eindeutig gelabelten Fälle")
    rule_pairs = [
        (row["relevant"] == "ja", _rule_prediction(cases[row["case_id"]]["keyword_score"]))
        for row in certain
    ]
    jev_pairs = [
        (row["relevant"] == "ja", answers[row["case_id"]]["probability_yes"] >= 0.5)
        for row in certain
    ]
    return {
        "status": "exploratory" if exploratory else "reviewed_proxy",
        "promotion_eligible": False,
        "reason": "Keyword-positive Proxy-Stichprobe ohne unabhängigen Kalibrations-/Testsplit",
        "corpus_sha256": dataset_hash,
        "cases": len(rows),
        "evaluated": len(certain),
        "unclear": len(rows) - len(certain),
        "rule": _confusion(rule_pairs),
        "jev": _confusion(jev_pairs),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("probe", type=Path)
    parser.add_argument("--exploratory", action="store_true")
    args = parser.parse_args()
    try:
        result = evaluate(args.corpus, args.labels, args.probe, exploratory=args.exploratory)
    except ValueError as exc:
        sys.stderr.write(f"Auswertung verweigert: {exc}\n")
        return 2
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
