"""Select real query/fact pairs for the local-search Jev benchmark.

Reads report tool-call logs and Neo4j without modifying either source. The
default output contains counts only; ``--emit-private-json`` emits minimized
query/fact pairs for a private review artifact. Never commit that output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, NamedTuple

from neo4j import GraphDatabase

from app.config import Config


class LoggedQuery(NamedTuple):
    graph_id: str
    report_id: str
    query: str


class Edge(NamedTuple):
    uuid: str
    name: str
    fact: str


_SENSITIVE = re.compile(
    r"https?://|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"\b(?:\+?\d[\d .()/\-]{7,}\d)\b",
    flags=re.IGNORECASE,
)


def _clean(value: str) -> str:
    return " ".join(value.split())


def _allowed(query: str, fact: str) -> bool:
    return (
        8 <= len(query) <= 180
        and 10 <= len(fact) <= 400
        and not _SENSITIVE.search(query)
        and not _SENSITIVE.search(fact)
    )


def _match_score(query: str, text: str) -> int:
    """Mirror graph_reader.local_search's keyword score for candidate selection."""
    query_lower = query.lower()
    text_lower = text.lower()
    if query_lower in text_lower:
        return 100
    keywords = [
        word.strip()
        for word in query_lower.replace(",", " ").replace("，", " ").split()
        if len(word.strip()) > 1
    ]
    return sum(10 for word in keywords if word in text_lower)


def _logged_queries(reports_dir: Path) -> list[LoggedQuery]:
    queries: list[LoggedQuery] = []
    for log_file in sorted(reports_dir.glob("*/agent_log.jsonl")):
        graph_id: str | None = None
        report_queries: list[str] = []
        for line in log_file.open(encoding="utf-8"):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            details = record.get("details") or {}
            if record.get("action") in {"start", "report_start"}:
                graph_id = details.get("graph_id")
            elif (
                record.get("action") == "tool_call"
                and details.get("tool_name") == "quick_search"
            ):
                parameters = details.get("parameters") or {}
                query = parameters.get("query")
                if isinstance(query, str) and query.strip():
                    report_queries.append(_clean(query))
        if graph_id:
            queries.extend(
                LoggedQuery(graph_id, log_file.parent.name, query)
                for query in report_queries
            )
    return queries


def _edges_by_graph(graph_ids: set[str]) -> dict[str, list[Edge]]:
    result: dict[str, list[Edge]] = defaultdict(list)
    driver = GraphDatabase.driver(
        Config.NEO4J_URI,
        auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
    )
    try:
        with driver.session() as session:
            rows = session.run(
                "MATCH ()-[r:RELATION]->() WHERE r.graph_id IN $graph_ids "
                "RETURN r.graph_id AS graph_id, r.uuid AS uuid, "
                "r.name AS name, r.fact AS fact",
                graph_ids=sorted(graph_ids),
            )
            for row in rows:
                result[row["graph_id"]].append(
                    Edge(row["uuid"] or "", row["name"] or "", row["fact"] or "")
                )
    finally:
        driver.close()
    return result


def select_cases(
    queries: list[LoggedQuery],
    edges_by_graph: dict[str, list[Edge]],
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Pick one highest-scored edge per real query, with graph diversity."""
    candidates: list[dict[str, Any]] = []
    seen_queries: set[tuple[str, str]] = set()
    counts = {"logged_queries": len(queries), "matched": 0, "filtered": 0}
    for logged in queries:
        key = (logged.graph_id, logged.query)
        if key in seen_queries:
            continue
        seen_queries.add(key)
        scored = [
            (_match_score(logged.query, edge.fact) + _match_score(logged.query, edge.name), edge)
            for edge in edges_by_graph.get(logged.graph_id, [])
        ]
        # Python's max keeps the first tie, like local_search's stable sort.
        score, edge = max(scored, key=lambda item: item[0], default=(0, None))
        if score <= 0 or edge is None:
            continue
        counts["matched"] += 1
        query, fact = _clean(logged.query), _clean(edge.fact)
        if not _allowed(query, fact):
            counts["filtered"] += 1
            continue
        case_id = hashlib.sha256(
            f"{logged.graph_id}\0{query}\0{edge.uuid}".encode()
        ).hexdigest()[:16]
        candidates.append(
            {
                "case_id": case_id,
                "graph_id": logged.graph_id,
                "report_id": logged.report_id,
                "edge_uuid": edge.uuid,
                "query": query,
                "fact": fact,
                "keyword_score": score,
                "expected_relevant": None,
            }
        )
    candidates.sort(key=lambda case: case["case_id"])
    selected: list[dict[str, Any]] = []
    per_graph: dict[str, int] = defaultdict(int)
    for case in candidates:
        if per_graph[case["graph_id"]] >= 2:
            continue
        selected.append(case)
        per_graph[case["graph_id"]] += 1
        if len(selected) == limit:
            break
    counts["eligible"] = len(candidates)
    counts["selected"] = len(selected)
    counts["selected_graphs"] = len(per_graph)
    return selected, counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--emit-private-json", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")

    queries = _logged_queries(Path(Config.UPLOAD_FOLDER) / "reports")
    edges = _edges_by_graph({query.graph_id for query in queries})
    cases, counts = select_cases(queries, edges, limit=args.limit)
    payload: dict[str, Any] = {"summary": counts}
    if args.emit_private_json:
        payload["cases"] = cases
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
