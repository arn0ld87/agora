"""CLI: Kennzahlen "Simulation lebt" aus einem Run-Verzeichnis (#1713 Slice S0).

Aufruf:
    uv run python scripts/sim_liveness_metrics.py <run_dir> [--seed PATH]

Liest ``<run_dir>/simulation_config.json``, ``<run_dir>/run_state.json``,
``<run_dir>/twitter/actions.jsonl`` und ``<run_dir>/reddit/actions.jsonl``
(fehlende Dateien sind kein Fehler — Single-Platform-Runs haben nur eine der
beiden Plattformen). Gibt ``SimulationLivenessReport.model_dump_json()`` auf
stdout aus (einzige stdout-Ausgabe, kein ``print()``); Diagnose/Warnungen
gehen als strukturiertes Logging nach stderr.

``--seed PATH`` zeigt auf das Seed-Dokument (``seed_document.md`` o.ä.) fuer
L7 (Seed-Echo). Ohne ``--seed`` bleibt L7 ``None``.

Definitionen und Zielwerte: ``docs/runbooks/simulation-liveness.md``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.contracts.simulation_liveness_contract import (  # noqa: E402
    PlatformLiveness,
    SimulationLivenessReport,
)

logger = logging.getLogger("agora.sim_liveness_metrics")

_STARTPOST_ROUND = 0
_NON_ACTIVITY_TYPES = {"DO_NOTHING", "REFRESH", "SIGN_UP"}
_OWN_POST_TYPES = {"CREATE_POST", "QUOTE_POST"}
_CREATIVE_TYPES = {"CREATE_POST", "CREATE_COMMENT", "QUOTE_POST", "REPOST"}
_REACTION_TYPES = {"LIKE_POST", "DISLIKE_POST", "LIKE_COMMENT", "DISLIKE_COMMENT"}
_DISLIKE_TYPES = {"DISLIKE_POST", "DISLIKE_COMMENT"}
# Aktionstyp -> Feld in action_args, das die Ziel-Entity referenziert
# (#1713 Slice S1: reposted_id ist seitdem Teil der Whitelist). Nur fuer den
# Akteur-Reaktionsgraphen (mutual_pair_share) — max_chain_length nutzt seit
# Slice S2 die eigenen _CHAIN_*-Felder unten (Beitrags-, nicht Agentenebene).
_TARGET_FIELD_BY_TYPE = {
    "LIKE_POST": "post_id",
    "DISLIKE_POST": "post_id",
    "LIKE_COMMENT": "comment_id",
    "DISLIKE_COMMENT": "comment_id",
    "QUOTE_POST": "quoted_id",
    "REPOST": "reposted_id",
}
# L4 max_chain_length: laengste Beitrags-Antwortkette (#1713 Slice S2).
# Jeder inhaltliche Beitrag referenziert hoechstens einen frueheren Beitrag
# ueber genau eines dieser Felder -> Wald/DAG in Zeitordnung statt Pfadsuche
# im (potenziell zyklischen) Agentengraphen.
_CHAIN_OWN_ID_FIELDS: dict[str, tuple[str, ...]] = {
    "CREATE_POST": ("post_id", "new_post_id", "id"),
    "CREATE_COMMENT": ("comment_id", "id"),
    "QUOTE_POST": ("new_post_id", "id"),
    "REPOST": ("new_post_id", "id"),
}
_CHAIN_PARENT_ID_FIELDS: dict[str, tuple[str, ...]] = {
    # #1713 S5: parent_comment_id wird zuerst geprueft (Kommentar-auf-Kommentar
    # verlaengert die Kette); erst danach faellt es auf den Elternpost zurueck.
    "CREATE_COMMENT": ("parent_comment_id", "post_id", "new_post_id"),
    "QUOTE_POST": ("quoted_id",),
    "REPOST": ("reposted_id", "original_post_id"),
}
# CREATE_POST/-COMMENT/QUOTE_POST/REPOST erzeugen jeweils einen Post ausser
# CREATE_COMMENT (eigener Namensraum). Mit nested comments (#1713 S5) koennen
# Kommentare selbst als Eltern auftreten -> Namensraum dynamisch.
_CHAIN_OWN_NAMESPACE_BY_TYPE = {
    "CREATE_POST": "post",
    "CREATE_COMMENT": "comment",
    "QUOTE_POST": "post",
    "REPOST": "post",
}
_CHAIN_PARENT_NAMESPACE = "post"
# Felder, deren Namespace vom Default _CHAIN_PARENT_NAMESPACE abweicht (#1713 S5).
_CHAIN_PARENT_NAMESPACE_BY_FIELD: dict[str, str] = {
    "parent_comment_id": "comment",
}

_WORD_RE = re.compile(r"\S+")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_SEED_NGRAM_SIZE = 8


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            entries.append(json.loads(stripped))
        except json.JSONDecodeError:
            logger.warning("Unparsable line in %s: %r", path, stripped[:200])
    return entries


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Unparsable JSON: %s", path)
        return {}


def _agent_name_to_id(config: dict[str, Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for agent_cfg in config.get("agent_configs", []):
        agent_id = agent_cfg.get("agent_id")
        entity_name = agent_cfg.get("entity_name")
        if agent_id is not None and entity_name:
            mapping[entity_name] = agent_id
    return mapping


def _resolve_rounds(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Stellt sicher, dass jede Aktions-Zeile ein ``round``-Feld traegt.

    Neue Logs (seit #1713 Slice S1) schreiben ``round`` immer explizit. Ein
    Altlauf ohne das Feld bekommt die Runde des zuletzt gesehenen
    ``round_start``-Events in Dateireihenfolge zugewiesen; bleibt auch das
    aus, faellt die Zeile aus allen rundenbasierten Kennzahlen heraus statt
    Runde 0 zu erfinden.
    """
    notes: list[str] = []
    resolved: list[dict[str, Any]] = []
    current_round = None
    derived_any = False
    dropped_any = False
    for entry in entries:
        if entry.get("event_type") == "round_start":
            current_round = entry.get("round")
        if entry.get("action_type") is None:
            resolved.append(entry)
            continue
        if "round" in entry:
            resolved.append(entry)
            continue
        if current_round is not None:
            entry = {**entry, "round": current_round}
            derived_any = True
            resolved.append(entry)
        else:
            dropped_any = True
    if derived_any:
        notes.append("Runde fuer mindestens eine Zeile aus round_start-Events abgeleitet (kein round-Feld im Log)")
    if dropped_any:
        notes.append("mindestens eine Aktions-Zeile ohne bestimmbare Runde wurde aus Runden-Kennzahlen ausgeschlossen")
    return resolved, notes


def _actual_actions(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nur Aktions-Zeilen (kein round_start/round_end/simulation_start/-end)."""
    return [e for e in entries if e.get("action_type") is not None and "round" in e]


def _real_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ohne Startposts (Runde 0) und ohne DO_NOTHING/REFRESH/SIGN_UP."""
    return [
        a for a in actions
        if a.get("round") != _STARTPOST_ROUND and a.get("action_type") not in _NON_ACTIVITY_TYPES
    ]


def _startpost_duplicates(actions: list[dict[str, Any]]) -> int:
    """Signatur des #1713-Altlauf-Defekts: ein CREATE_POST mit identischem
    ``(agent_id, content)`` erscheint sowohl in Runde 0 (Startpost) als auch
    erneut in einer spaeteren Runde, weil ``last_rowid`` nicht auf den
    Trace-Stand nach dem Initial-Post-Step gezogen wurde."""
    startposts: set[tuple[Any, str]] = set()
    for a in actions:
        if a.get("round") == _STARTPOST_ROUND and a.get("action_type") == "CREATE_POST":
            content = (a.get("action_args") or {}).get("content", "")
            startposts.add((a.get("agent_id"), content))
    if not startposts:
        return 0
    duplicates = 0
    for a in actions:
        if a.get("round") == _STARTPOST_ROUND or a.get("action_type") != "CREATE_POST":
            continue
        content = (a.get("action_args") or {}).get("content", "")
        if (a.get("agent_id"), content) in startposts:
            duplicates += 1
    return duplicates


def _round_fill(entries: list[dict[str, Any]]) -> tuple[int, int, list[str]]:
    """Liefert (abgeschlossene Runden, hoechste gesehene Rundennummer, Notes)."""
    notes: list[str] = []
    round_starts = {
        e.get("round") for e in entries
        if e.get("event_type") == "round_start" and (e.get("round") or 0) > 0
    }
    round_ends = {
        e.get("round") for e in entries
        if e.get("event_type") == "round_end" and (e.get("round") or 0) > 0
    }
    all_rounds = round_starts | round_ends
    if not all_rounds:
        notes.append("keine Rundenmarker (round_start/round_end) gefunden")
        return 0, 0, notes
    max_round = max(all_rounds)
    complete = round_starts & round_ends
    missing = sorted(all_rounds - complete)
    if missing:
        notes.append(f"unvollstaendige Rundenmarker fuer Runde(n) {missing}")
    return len(complete), max_round, notes


def _l1(real_actions: list[dict[str, Any]], agent_count: int, rounds_completed: int) -> float | None:
    if agent_count <= 0 or rounds_completed <= 0:
        return None
    return len(real_actions) / (agent_count * rounds_completed)


def _round_shares(actions: list[dict[str, Any]], agent_count: int) -> list[float]:
    if agent_count <= 0:
        return []
    by_round: dict[Any, set[Any]] = defaultdict(set)
    for a in actions:
        r = a.get("round")
        if r is None or r == _STARTPOST_ROUND:
            continue
        by_round[r].add(a.get("agent_id"))
    return [len(agents) / agent_count for agents in by_round.values()]


def _l3(real_actions: list[dict[str, Any]]) -> float | None:
    creative = [a for a in real_actions if a.get("action_type") in _CREATIVE_TYPES]
    if not creative:
        return None
    own = sum(1 for a in creative if a.get("action_type") in _OWN_POST_TYPES)
    return own / len(creative)


def _resolve_target_agent_id(action: dict[str, Any], name_to_id: dict[str, int]) -> int | None:
    action_type = action.get("action_type")
    field = _TARGET_FIELD_BY_TYPE.get(action_type)
    args = action.get("action_args") or {}
    if field is None or field not in args:
        return None
    author_name = (
        args.get("post_author_name")
        or args.get("comment_author_name")
        or args.get("original_author_name")
    )
    if not author_name:
        return None
    return name_to_id.get(author_name)


def _build_edges(real_actions: list[dict[str, Any]], name_to_id: dict[str, int]) -> set[tuple[Any, Any]]:
    edges: set[tuple[Any, Any]] = set()
    for a in real_actions:
        if a.get("action_type") not in _TARGET_FIELD_BY_TYPE:
            continue
        actor = a.get("agent_id")
        target = _resolve_target_agent_id(a, name_to_id)
        if actor is None or target is None or actor == target:
            continue
        edges.add((actor, target))
    return edges


def _mutual_pair_share(edges: set[tuple[Any, Any]]) -> float | None:
    if not edges:
        return None
    pairs: dict[frozenset, set[tuple[Any, Any]]] = defaultdict(set)
    for src, dst in edges:
        pairs[frozenset((src, dst))].add((src, dst))
    mutual = sum(1 for directions in pairs.values() if len(directions) == 2)
    return mutual / len(pairs)


def _chain_own_id(action: dict[str, Any]) -> Any | None:
    fields = _CHAIN_OWN_ID_FIELDS.get(action.get("action_type"))
    if not fields:
        return None
    args = action.get("action_args") or {}
    for field in fields:
        value = args.get(field)
        if value is not None:
            return value
    return None


def _chain_parent_info(action: dict[str, Any]) -> tuple[Any, str] | None:
    """Liefert ``(parent_id, namespace)`` fuer die erste gefundene Elternreferenz.

    #1713 S5: ``parent_comment_id`` zeigt auf einen Kommentar (Namespace
    ``"comment"``), alle anderen Felder zeigen auf Posts (Namespace ``"post"``).
    """
    action_type = action.get("action_type")
    fields = _CHAIN_PARENT_ID_FIELDS.get(action_type)
    if not fields:
        return None
    args = action.get("action_args") or {}
    for field in fields:
        value = args.get(field)
        if value is not None:
            ns = _CHAIN_PARENT_NAMESPACE_BY_FIELD.get(field, _CHAIN_PARENT_NAMESPACE)
            return value, ns
    return None


def _chain_parent_id(action: dict[str, Any]) -> Any | None:
    """Rueckwaertskompatibel: liefert nur die parent_id (ohne Namespace).

    Intern wird ``_chain_parent_info`` genutzt.
    """
    info = _chain_parent_info(action)
    return info[0] if info is not None else None


def _max_chain_length(real_actions: list[dict[str, Any]], key_prefix: str) -> int | None:
    """Laengste Beitrags-Antwortkette (#1713 Slice S2, ersetzt die Pfadsuche
    im Agentengraphen aus Slice S0/S1).

    Jeder inhaltliche Beitrag (``CREATE_POST``/``CREATE_COMMENT``/
    ``QUOTE_POST``/``REPOST``) referenziert hoechstens einen frueheren
    Beitrag. Da ``real_actions`` bereits in Dateireihenfolge (= Erstell-
    reihenfolge) vorliegt, ist die Elterntiefe beim Erreichen eines Knotens
    stets schon bekannt -> ein Durchlauf, O(n), ohne Rekursion.

    Referenziert ein Beitrag eine Eltern-ID, die (noch) kein bekannter Knoten
    ist — fehlender Startpost ohne ``post_id``, kaputte Referenz, oder eine
    Vorwaertsreferenz auf einen erst spaeter geloggten Beitrag — wird der
    Kindknoten zur Wurzel statt die Berechnung zu blockieren. Dadurch kann
    aus (fehlerhaften) Logs keine echte Zyklusreferenz entstehen: nur
    bereits gesehene, also zeitlich fruehere Beitraege zaehlen als Eltern.
    """
    depth_by_key: dict[tuple[str, str, Any], int] = {}
    max_depth = 0
    found_any = False
    for action in real_actions:
        action_type = action.get("action_type")
        own_namespace = _CHAIN_OWN_NAMESPACE_BY_TYPE.get(action_type)
        if own_namespace is None:
            continue
        own_id = _chain_own_id(action)
        if own_id is None:
            continue
        found_any = True
        own_key = (key_prefix, own_namespace, own_id)
        parent_info = _chain_parent_info(action)
        parent_key = (key_prefix, parent_info[1], parent_info[0]) if parent_info is not None else None
        node_depth = depth_by_key[parent_key] + 1 if parent_key in depth_by_key else 0
        depth_by_key[own_key] = node_depth
        if node_depth > max_depth:
            max_depth = node_depth
    return max_depth if found_any else None


def _l5(real_actions: list[dict[str, Any]]) -> float | None:
    reactions = [a for a in real_actions if a.get("action_type") in _REACTION_TYPES]
    if not reactions:
        return None
    dislikes = sum(1 for a in reactions if a.get("action_type") in _DISLIKE_TYPES)
    return dislikes / len(reactions)


def _seed_ngrams(tokens: list[str], n: int = _SEED_NGRAM_SIZE) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def _l7(
    real_actions: list[dict[str, Any]], seed_text: str | None
) -> tuple[float | None, list[str]]:
    notes: list[str] = []
    if seed_text is None:
        notes.append("kein --seed angegeben, L7 nicht berechnet")
        return None, notes
    own_posts = [a for a in real_actions if a.get("action_type") in _OWN_POST_TYPES]
    if not own_posts:
        return None, notes
    seed_numbers = set(_NUMBER_RE.findall(seed_text))
    seed_ngrams = _seed_ngrams(_WORD_RE.findall(seed_text))
    echoes = 0
    for a in own_posts:
        content = (a.get("action_args") or {}).get("content", "") or ""
        if set(_NUMBER_RE.findall(content)) & seed_numbers:
            echoes += 1
            continue
        if _seed_ngrams(_WORD_RE.findall(content)) & seed_ngrams:
            echoes += 1
    return echoes / len(own_posts), notes


def _compute_platform(
    platform: str,
    entries: list[dict[str, Any]],
    agent_count: int,
    name_to_id: dict[str, int],
    seed_text: str | None,
) -> tuple[PlatformLiveness, dict[str, Any]]:
    resolved, round_notes = _resolve_rounds(entries)
    actions = _actual_actions(resolved)
    real_actions = _real_actions(actions)

    complete_rounds, max_round, fill_notes = _round_fill(resolved)
    round_fill_share = (complete_rounds / max_round) if max_round else None

    duplicates = _startpost_duplicates(actions)
    round_shares = _round_shares(actions, agent_count)
    edges = _build_edges(real_actions, name_to_id)
    mutual_share = _mutual_pair_share(edges)
    max_chain = _max_chain_length(real_actions, platform)
    seed_echo_share, l7_notes = _l7(real_actions, seed_text)
    action_type_counts = Counter(a.get("action_type", "UNKNOWN") for a in actions)

    notes = [*round_notes, *fill_notes, *l7_notes]
    if duplicates:
        notes.append(f"{duplicates} doppelt geloggte(r) Startpost(s) gefunden (Altlauf-Signatur #1713)")

    liveness = PlatformLiveness(
        platform=platform,
        actions_per_agent_round=_l1(real_actions, agent_count, max_round),
        active_agent_share_median=(median(round_shares) if round_shares else None),
        own_post_share=_l3(real_actions),
        mutual_pair_share=mutual_share,
        max_chain_length=max_chain,
        rejection_share=_l5(real_actions),
        contra_reply_share=None,
        seed_echo_share=seed_echo_share,
        duplicate_log_lines=duplicates,
        round_fill_share=round_fill_share,
        action_type_counts=dict(action_type_counts),
        data_quality_notes=notes,
    )
    intermediate = {
        "real_actions": real_actions,
        "round_shares": round_shares,
        "edges": {(f"{platform}:{a}", f"{platform}:{b}") for a, b in edges},
        "own_posts_for_seed": [a for a in real_actions if a.get("action_type") in _OWN_POST_TYPES],
        "duplicates": duplicates,
        "complete_rounds": complete_rounds,
        "max_round": max_round,
        "action_type_counts": action_type_counts,
        "max_chain": max_chain,
        "notes": notes,
    }
    return liveness, intermediate


def _combine_overall(
    intermediates: dict[str, dict[str, Any]], agent_count: int, seed_text: str | None
) -> PlatformLiveness:
    real_actions_all: list[dict[str, Any]] = []
    round_shares_all: list[float] = []
    edges_all: set[tuple[Any, Any]] = set()
    action_type_counts_total: Counter[str] = Counter()
    notes_all: list[str] = []
    duplicates_total = 0
    complete_rounds_total = 0
    max_round_total = 0
    max_chain_per_platform: list[int] = []

    for data in intermediates.values():
        real_actions_all.extend(data["real_actions"])
        round_shares_all.extend(data["round_shares"])
        edges_all |= data["edges"]
        action_type_counts_total.update(data["action_type_counts"])
        notes_all.extend(data["notes"])
        duplicates_total += data["duplicates"]
        complete_rounds_total += data["complete_rounds"]
        max_round_total += data["max_round"]
        if data["max_chain"] is not None:
            max_chain_per_platform.append(data["max_chain"])

    mutual_share = _mutual_pair_share(edges_all)
    # Post-/Kommentar-IDs sind pro Plattform namensraumgebunden (der
    # Ketten-Schluessel traegt das Plattformpraefix) -> die Ketten zweier
    # Plattformen koennen sich nie ueberschneiden, "gesamt" ist schlicht das
    # Maximum der bereits pro Plattform berechneten Kettenlaengen.
    max_chain = max(max_chain_per_platform) if max_chain_per_platform else None
    seed_echo_share, l7_notes = _l7(real_actions_all, seed_text)
    round_fill_share = (complete_rounds_total / max_round_total) if max_round_total else None

    return PlatformLiveness(
        platform="gesamt",
        actions_per_agent_round=_l1(real_actions_all, agent_count, max_round_total),
        active_agent_share_median=(median(round_shares_all) if round_shares_all else None),
        own_post_share=_l3(real_actions_all),
        mutual_pair_share=mutual_share,
        max_chain_length=max_chain,
        rejection_share=_l5(real_actions_all),
        contra_reply_share=None,
        seed_echo_share=seed_echo_share,
        duplicate_log_lines=duplicates_total,
        round_fill_share=round_fill_share,
        action_type_counts=dict(action_type_counts_total),
        data_quality_notes=[*dict.fromkeys(notes_all), *l7_notes],
    )


def compute_report(run_dir: Path, seed_path: Path | None = None) -> SimulationLivenessReport:
    config = _read_json(run_dir / "simulation_config.json")
    run_state = _read_json(run_dir / "run_state.json")
    name_to_id = _agent_name_to_id(config)
    agent_count = len(config.get("agent_configs", []))
    sim_id = config.get("simulation_id") or run_state.get("simulation_id") or run_dir.name

    seed_text: str | None = None
    if seed_path is not None:
        if seed_path.exists():
            seed_text = seed_path.read_text(encoding="utf-8")
        else:
            logger.warning("Seed-Datei nicht gefunden: %s", seed_path)

    platforms: list[str] = []
    per_platform: dict[str, PlatformLiveness] = {}
    intermediates: dict[str, dict[str, Any]] = {}
    for platform in ("twitter", "reddit"):
        log_path = run_dir / platform / "actions.jsonl"
        if not log_path.exists():
            continue
        platforms.append(platform)
        entries = _read_jsonl(log_path)
        liveness, intermediate = _compute_platform(platform, entries, agent_count, name_to_id, seed_text)
        per_platform[platform] = liveness
        intermediates[platform] = intermediate

    overall = _combine_overall(intermediates, agent_count, seed_text) if intermediates else PlatformLiveness(
        platform="gesamt", data_quality_notes=["keine Plattform-Logs gefunden (weder twitter/ noch reddit/)"]
    )
    rounds_completed = max((data["max_round"] for data in intermediates.values()), default=0)

    wall_clock_seconds = None
    started_at = run_state.get("started_at")
    completed_at = run_state.get("completed_at") or run_state.get("updated_at")
    if started_at and completed_at:
        try:
            from datetime import datetime
            wall_clock_seconds = (
                datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at)
            ).total_seconds()
        except ValueError:
            logger.warning("started_at/completed_at nicht ISO-parsebar in run_state.json")

    return SimulationLivenessReport(
        sim_id=str(sim_id),
        platforms=platforms,
        agent_count=agent_count,
        rounds_completed=rounds_completed,
        runner_status=str(run_state.get("runner_status", "unknown")),
        wall_clock_seconds=wall_clock_seconds,
        per_platform=per_platform,
        overall=overall,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Simulations-Run-Verzeichnis")
    parser.add_argument("--seed", type=Path, default=None, help="Pfad zum Seed-Dokument (fuer L7)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")

    if not args.run_dir.exists():
        logger.error("Run-Verzeichnis existiert nicht: %s", args.run_dir)
        return 1

    report = compute_report(args.run_dir, args.seed)
    sys.stdout.write(report.model_dump_json(indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
