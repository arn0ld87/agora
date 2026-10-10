"""Abnahmemaße der Haltungsanalyse eines Berichts (#1779).

Die Positionierungsquote (#1778) ist gesättigt: eine Stimme zählt schon mit einem
einzigen positionierten Beitrag. Das ändert nichts daran, dass die konfigurierte
Haltung über die Runden verblasst (Lauf ``sim_c8c6b30aa652``: 19,6 % positionierte
Beiträge in den Runden 7-11, 7,6 % in den Runden 12-24). Die Maßnahmen für #1779
werden deshalb zusätzlich an drei Gegenmaßen abgenommen, alle aus
``stance_analysis.json`` (Vertrag ``StanceAnalysis``) ableitbar:

* **Verfall:** Anteil positionierter Beiträge (``in_favour``/``opposed``) der
  konfigurierten Gegner und Befürworter je Runde und aggregiert für ein frühes
  und ein spätes Rundenfenster (Standard 7-11 gegen 12-24), gesamt und je Startklasse.
* **Treue zur Startklasse:** Anteil der Beiträge konfigurierter Gegner, die als
  ``opposed`` klassifiziert sind, bzw. konfigurierter Befürworter als ``in_favour``.
* **Unentschiedene Stimmen:** Anteil der Stimmen mit Startklasse ``undecided``, die
  in der Simulation Stellung beziehen (mindestens ein Beitrag ``in_favour``/``opposed``).

Kein Modell, kein Netz: reine Funktionen über der gespeicherten Analyse. Die Quote
selbst kommt unverändert aus der Pipeline (``positioning_ratio``); die Abnahme
verlangt strikt mehr als 0,5.

Aufruf:
    uv run python scripts/stance_acceptance.py <stance_analysis.json|Berichtsverzeichnis> \
        [--early 7-11] [--late 12-24]

Ausgabe: ein JSON-Objekt auf stdout. Exit 2 bei fehlender oder vertragswidriger Datei.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Sicherstellen, dass das backend-Paket importierbar ist.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.contracts.stance_analysis_contract import (  # noqa: E402
    ClassifiedContribution,
    StanceAnalysis,
    StanceClass,
)

logger = logging.getLogger(__name__)

ANALYSIS_FILENAME = "stance_analysis.json"
DEFAULT_EARLY_ROUNDS: Tuple[int, int] = (7, 11)
DEFAULT_LATE_ROUNDS: Tuple[int, int] = (12, 24)

#: Schwelle der Abnahme aus #1778/#1779: strikt mehr als die Hälfte der Stimmen.
POSITIONING_RATIO_THRESHOLD = 0.5

_VOICE_KEY_PREFIX = "agent:"

_Window = Tuple[int, int]
_SidedContribution = Tuple[ClassifiedContribution, StanceClass]


def _share(part: int, whole: int) -> Optional[float]:
    return part / whole if whole else None


def _positioned_stats(contributions: Iterable[ClassifiedContribution]) -> Dict[str, Any]:
    items = list(contributions)
    positioned = sum(1 for c in items if c.stance_class != "undecided")
    return {"contributions": len(items), "positioned": positioned, "share": _share(positioned, len(items))}


def _matching_stats(sided: Iterable[_SidedContribution]) -> Dict[str, Any]:
    items = list(sided)
    matching = sum(1 for contribution, start in items if contribution.stance_class == start)
    return {"contributions": len(items), "matching": matching, "share": _share(matching, len(items))}


def _agent_id_of(voice_key: str) -> Optional[int]:
    if not voice_key.startswith(_VOICE_KEY_PREFIX):
        return None
    raw = voice_key[len(_VOICE_KEY_PREFIX):]
    return int(raw) if raw.isdigit() else None


def _in_window(contribution: ClassifiedContribution, window: _Window) -> bool:
    return window[0] <= contribution.round_num <= window[1]


def _decay_block(sided: Sequence[_SidedContribution], early: _Window, late: _Window) -> Dict[str, Any]:
    early_stats = _positioned_stats(c for c, _s in sided if _in_window(c, early))
    late_stats = _positioned_stats(c for c, _s in sided if _in_window(c, late))
    delta = (
        late_stats["share"] - early_stats["share"]
        if early_stats["share"] is not None and late_stats["share"] is not None
        else None
    )
    return {"early": early_stats, "late": late_stats, "delta": delta}


def compute_acceptance_metrics(
    analysis: StanceAnalysis,
    *,
    early_rounds: _Window = DEFAULT_EARLY_ROUNDS,
    late_rounds: _Window = DEFAULT_LATE_ROUNDS,
) -> Dict[str, Any]:
    """Berechnet die Abnahmemaße aus einer ``StanceAnalysis``.

    Beiträge werden über ``voice_key`` (``agent:<agent_id>``) der Stimme und damit
    ihrer Startklasse zugeordnet; Beiträge ohne Stimme zählt ``unmatched_contributions``.
    "Konfigurierte Gegner/Befürworter" sind Stimmen mit Startklasse ``opposed`` bzw.
    ``in_favour``. Ein leerer Nenner ergibt ``None`` statt einer Division durch null.
    """
    if not analysis.applicable:
        return {"applicable": False}

    start_by_agent: Dict[int, StanceClass] = {}
    for voice in analysis.voices:
        agent_id = _agent_id_of(voice.voice_key)
        if agent_id is not None:
            start_by_agent[agent_id] = voice.start_class

    sided: List[_SidedContribution] = []
    unmatched = 0
    for contribution in analysis.contributions:
        start = start_by_agent.get(contribution.agent_id)
        if start is None:
            unmatched += 1
        elif start != "undecided":
            sided.append((contribution, start))

    by_round: Dict[int, Dict[str, Any]] = {}
    for round_num in sorted({c.round_num for c, _s in sided}):
        by_round[round_num] = _positioned_stats(c for c, _s in sided if c.round_num == round_num)

    decay = _decay_block(sided, early_rounds, late_rounds)
    decay_by_start = {
        start: _decay_block([item for item in sided if item[1] == start], early_rounds, late_rounds)
        for start in ("opposed", "in_favour")
    }

    undecided_voices = [v for v in analysis.voices if v.start_class == "undecided"]
    undecided_positioned = sum(
        1 for v in undecided_voices if any(c != "undecided" for c in v.contribution_classes)
    )

    return {
        "applicable": True,
        "positioning_ratio": analysis.positioning_ratio,
        "positioning_ratio_above_half": (
            analysis.positioning_ratio is not None
            and analysis.positioning_ratio > POSITIONING_RATIO_THRESHOLD
        ),
        "voices_total": analysis.voices_total,
        "voices_positioned": analysis.voices_positioned,
        "classification_failed": analysis.classification_failed,
        "unmatched_contributions": unmatched,
        "positioned_contribution_share_by_round": by_round,
        "decay": {
            "early_rounds": list(early_rounds),
            "late_rounds": list(late_rounds),
            **decay,
            "by_start_class": decay_by_start,
        },
        "start_class_fidelity": {
            "opposed": _matching_stats(item for item in sided if item[1] == "opposed"),
            "in_favour": _matching_stats(item for item in sided if item[1] == "in_favour"),
            "all": _matching_stats(sided),
        },
        "undecided_voices": {
            "total": len(undecided_voices),
            "positioned": undecided_positioned,
            "share": _share(undecided_positioned, len(undecided_voices)),
        },
    }


def _parse_window(raw: str) -> _Window:
    try:
        start_raw, end_raw = raw.split("-", 1)
        start, end = int(start_raw), int(end_raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"erwartet <von>-<bis> (z. B. 7-11), erhalten: {raw!r}") from exc
    if start < 0 or end < start:
        raise argparse.ArgumentTypeError(f"ungültiges Rundenfenster: {raw!r}")
    return start, end


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path / ANALYSIS_FILENAME if path.is_dir() else path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Abnahmemaße der Haltungsanalyse (#1779)")
    parser.add_argument("path", help=f"{ANALYSIS_FILENAME} oder das Berichtsverzeichnis, das sie enthält")
    parser.add_argument("--early", type=_parse_window, default=DEFAULT_EARLY_ROUNDS, help="frühes Rundenfenster, z. B. 7-11")
    parser.add_argument("--late", type=_parse_window, default=DEFAULT_LATE_ROUNDS, help="spätes Rundenfenster, z. B. 12-24")
    args = parser.parse_args(argv)

    path = _resolve_path(args.path)
    try:
        analysis = StanceAnalysis.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.error("Haltungsanalyse nicht lesbar (%s): %s", path, exc)
        return 2
    except ValueError as exc:
        logger.error("Haltungsanalyse entspricht nicht dem Vertrag StanceAnalysis (%s): %s", path, exc)
        return 2

    metrics = compute_acceptance_metrics(analysis, early_rounds=args.early, late_rounds=args.late)
    sys.stdout.write(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main())
