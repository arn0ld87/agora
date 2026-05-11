"""S0 Diagnose-Skript: Metric-Snapshot-Anomalie reproduzieren (Evidence-Pipeline v2).

Hintergrund: Externer Review meldete `total_agents=0`/`total_interactions=0`
neben vorhandenen `simulation_actions` im Report-Export. Dieses Skript
analysiert bestehende Sim-Runs (read-only), repliziert den exakten Pfad,
den `report_agent._collect_simulation_evidence_items` nimmt
(`SimulationRunner.get_all_actions` → `NetworkAnalyticsService.compute_metrics`),
und schreibt einen Diff-Bericht.

Usage:
    uv run python backend/scripts/diagnose_metric_snapshot.py
    uv run python backend/scripts/diagnose_metric_snapshot.py --sim sim_xxx
    uv run python backend/scripts/diagnose_metric_snapshot.py --all
    uv run python backend/scripts/diagnose_metric_snapshot.py --limit 10

Ausgabe: stdout-Zusammenfassung + Markdown-Bericht unter
``docs/archive/history/2026-05-01-metric-snapshot-diagnose.md``.

Read-only. Triggert keinen Sim-Run, keine LLM-Calls, keinen Neo4j-Zugriff.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, backend_dir)

from app.services.network_analytics import (  # noqa: E402
    NetworkAnalyticsService,
    _DIRECTED_ACTIONS,
)
from app.services.simulation_runner import SimulationRunner  # noqa: E402

REPO_ROOT = Path(backend_dir).parent
SIM_DIR = REPO_ROOT / "backend" / "uploads" / "simulations"
DEFAULT_REPORT_PATH = REPO_ROOT / "docu" / "2026-05-01-metric-snapshot-diagnose.md"


@dataclass
class SimDiagnosis:
    sim_id: str
    twitter_jsonl_bytes: int = 0
    reddit_jsonl_bytes: int = 0
    twitter_lines: int = 0
    reddit_lines: int = 0
    actions_total: int = 0
    actions_loaded_via_runner: int = 0
    action_types: Counter = field(default_factory=Counter)
    unique_agents: int = 0
    directed_action_count: int = 0
    metrics: Dict[str, Any] = field(default_factory=dict)
    state_status: Optional[str] = None
    state_current_round: Optional[int] = None
    state_updated_at: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def verdict(self) -> str:
        """Klassifiziere die Anomalie nach klaren Buckets."""
        if self.actions_total == 0:
            return "no_actions_logged"
        if self.directed_action_count == 0:
            return "broadcast_only_no_pairwise"
        if self.metrics.get("total_agents", 0) == 0 and self.directed_action_count > 0:
            return "directed_actions_but_no_agents_extracted"
        if self.metrics.get("total_interactions", 0) == 0 and self.directed_action_count > 0:
            return "directed_actions_filtered_to_empty"
        return "metrics_consistent"


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as f:
        return sum(1 for _ in f)


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _load_state_json(sim_path: Path) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    state_file = sim_path / "state.json"
    if not state_file.exists():
        return None, None, None
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, None, None
    return data.get("status"), data.get("current_round"), data.get("updated_at")


def diagnose_sim(sim_id: str) -> SimDiagnosis:
    sim_path = SIM_DIR / sim_id
    diag = SimDiagnosis(sim_id=sim_id)

    twitter_jsonl = sim_path / "twitter" / "actions.jsonl"
    reddit_jsonl = sim_path / "reddit" / "actions.jsonl"
    diag.twitter_jsonl_bytes = _file_size(twitter_jsonl)
    diag.reddit_jsonl_bytes = _file_size(reddit_jsonl)
    diag.twitter_lines = _count_lines(twitter_jsonl)
    diag.reddit_lines = _count_lines(reddit_jsonl)

    diag.state_status, diag.state_current_round, diag.state_updated_at = _load_state_json(sim_path)

    try:
        actions = SimulationRunner.get_all_actions(sim_id)
    except Exception as exc:
        diag.notes.append(f"get_all_actions failed: {exc!r}")
        return diag

    action_dicts = [a.to_dict() for a in actions]
    diag.actions_loaded_via_runner = len(action_dicts)
    diag.actions_total = diag.twitter_lines + diag.reddit_lines

    if not action_dicts:
        return diag

    types = Counter(a.get("action_type", "UNKNOWN") for a in action_dicts)
    diag.action_types = types
    diag.directed_action_count = sum(
        v for k, v in types.items() if (k or "").upper() in _DIRECTED_ACTIONS
    )

    agents = {a.get("agent_id") for a in action_dicts if a.get("agent_id") is not None}
    diag.unique_agents = len(agents)

    metrics = NetworkAnalyticsService().compute_metrics(action_dicts, simulation_id=sim_id)
    diag.metrics = metrics.to_dict()

    return diag


def list_runs_with_actions(limit: Optional[int] = None) -> List[str]:
    if not SIM_DIR.exists():
        return []
    candidates = []
    for sim_path in SIM_DIR.iterdir():
        if not sim_path.is_dir() or not sim_path.name.startswith("sim_"):
            continue
        twitter_jsonl = sim_path / "twitter" / "actions.jsonl"
        reddit_jsonl = sim_path / "reddit" / "actions.jsonl"
        if _file_size(twitter_jsonl) > 0 or _file_size(reddit_jsonl) > 0:
            mtime = max(
                _file_size(twitter_jsonl) and twitter_jsonl.stat().st_mtime or 0,
                _file_size(reddit_jsonl) and reddit_jsonl.stat().st_mtime or 0,
            )
            candidates.append((mtime, sim_path.name))
    candidates.sort(reverse=True)
    sims = [name for _, name in candidates]
    return sims if limit is None else sims[:limit]


def render_markdown(diags: List[SimDiagnosis]) -> str:
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines = [
        "# Metric-Snapshot-Diagnose (S0)",
        "",
        f"**Datum:** {now_iso}",
        f"**Diagnostizierte Sim-Runs:** {len(diags)}",
        "",
        "## Methodik",
        "",
        "Skript repliziert den Pfad aus `report_agent._collect_simulation_evidence_items`:",
        "",
        "1. `SimulationRunner.get_all_actions(sim_id)` — liest `<sim>/twitter/actions.jsonl` und `<sim>/reddit/actions.jsonl`",
        "2. `NetworkAnalyticsService.compute_metrics(...)` — Louvain-Communities + Echo-Chamber-Index",
        "3. Vergleich mit Action-Type-Histogramm und `_DIRECTED_ACTIONS`-Filter",
        "",
        "## Ergebnis-Tabelle",
        "",
        "| Sim | Status | Lines (T/R) | Actions | Directed | Agents | Metric agents/inter/cluster | Verdict |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for d in diags:
        m = d.metrics
        m_str = f"{m.get('total_agents', '-')}/{m.get('total_interactions', '-')}/{m.get('cluster_count', '-')}"
        lines.append(
            f"| `{d.sim_id}` | {d.state_status or '?'} | {d.twitter_lines}/{d.reddit_lines} | "
            f"{d.actions_loaded_via_runner} | {d.directed_action_count} | {d.unique_agents} | "
            f"{m_str} | **{d.verdict()}** |"
        )

    lines.extend(["", "## Action-Type-Histogramm pro Run", ""])
    for d in diags:
        lines.append(f"### `{d.sim_id}` — verdict: **{d.verdict()}**")
        lines.append("")
        if d.actions_loaded_via_runner == 0:
            lines.append("_Keine Actions geladen._")
        else:
            lines.append("| Type | Count | In _DIRECTED_ACTIONS? |")
            lines.append("|---|---|---|")
            for atype, count in sorted(d.action_types.items(), key=lambda x: -x[1]):
                directed = "✅" if (atype or "").upper() in _DIRECTED_ACTIONS else "❌"
                lines.append(f"| `{atype}` | {count} | {directed} |")
        if d.notes:
            lines.append("")
            lines.append("**Notes:**")
            for note in d.notes:
                lines.append(f"- {note}")
        lines.append("")

    lines.extend([
        "## Verdict-Kategorien",
        "",
        "- **`no_actions_logged`** — actions.jsonl leer/fehlend. Sim wurde nicht oder unvollständig durchgelaufen.",
        "- **`broadcast_only_no_pairwise`** — actions.jsonl gefüllt, aber nur `CREATE_POST`/`CREATE_COMMENT`-Broadcasts ohne pairwise Interactions wie `LIKE_POST`/`FOLLOW`. Metriken sind technisch korrekt 0, aber semantisch eine Lüge im Report-Export.",
        "- **`directed_actions_but_no_agents_extracted`** — Directed Actions vorhanden, aber `_extract_target_agent` findet keine Target-IDs. Schema-Mismatch.",
        "- **`directed_actions_filtered_to_empty`** — Directed Actions vorhanden mit Targets, aber alle werden später gefiltert (z. B. self-loops). Sollte selten sein.",
        "- **`metrics_consistent`** — Metriken passen zu Actions, kein Bug.",
        "",
        "## Konsequenzen für S2",
        "",
        "Die Diagnose-Verteilung bestimmt, was S2a (Snapshot-Hardening) konkret tun muss:",
        "",
        "- Bei vielen `broadcast_only_no_pairwise` → S2a sollte einen **Status-Flag** im Snapshot setzen (`status: \"no_pairwise_interactions\"`) statt 0/0/0/0 als Metrik auszugeben. UI in S2b zeigt dann Metriken-nicht-verfuegbar.",
        "- Bei `no_actions_logged` → ähnlich, Status `no_actions`.",
        "- Bei `directed_actions_but_no_agents_extracted` → echter Bug in `_extract_target_agent`, separate Untersuchung.",
        "",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim", help="Einzelne Simulation-ID diagnostizieren")
    parser.add_argument("--all", action="store_true", help="Alle Runs mit non-empty actions.jsonl")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Wenn --all: max. N Runs (sortiert nach mtime, neueste zuerst). Default 5.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"Pfad zum Markdown-Bericht. Default: {DEFAULT_REPORT_PATH}",
    )
    parser.add_argument("--no-write", action="store_true", help="Bericht nicht in Datei schreiben")
    args = parser.parse_args()

    if args.sim:
        sims = [args.sim]
    elif args.all:
        sims = list_runs_with_actions(limit=None)
    else:
        sims = list_runs_with_actions(limit=args.limit)

    if not sims:
        print("Keine Sim-Runs mit Actions gefunden.", file=sys.stderr)
        return 1

    print(f"Diagnostiziere {len(sims)} Run(s)…")
    diags: List[SimDiagnosis] = []
    for sim_id in sims:
        try:
            diag = diagnose_sim(sim_id)
            diags.append(diag)
            m = diag.metrics
            print(
                f"  {sim_id}: actions={diag.actions_loaded_via_runner} "
                f"directed={diag.directed_action_count} "
                f"agents={diag.unique_agents} "
                f"metric_agents={m.get('total_agents', '-')} "
                f"metric_inter={m.get('total_interactions', '-')} "
                f"verdict={diag.verdict()}"
            )
        except Exception as exc:
            print(f"  {sim_id}: FAILED — {exc!r}", file=sys.stderr)

    verdict_counts = Counter(d.verdict() for d in diags)
    print("\nVerdict-Verteilung:")
    for verdict, count in verdict_counts.most_common():
        print(f"  {verdict}: {count}")

    if not args.no_write:
        report = render_markdown(diags)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"\nBericht geschrieben: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
