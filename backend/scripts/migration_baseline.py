"""Baseline-Manifest fuer die Supabase-Migration (docs/plans/supabase.md §6).

Warum das existiert
-------------------
Vor dem ersten Datenumbau muss festliegen, welcher Stand als „funktioniert"
gilt. Nicht als Prosa, sondern als vergleichbare Zahlenreihe: dieselbe Klasse,
dieselbe Anzahl, dieselben IDs, dieselben Zeitstempel, dieselben Statuswerte,
dieselben Referenzen, dieselben Pruefsummen — vor und nach jeder Phase.

Das Skript erzeugt genau dieses Manifest. Es wird zweimal gefahren, einmal vor
und einmal nach einer Migration, und die beiden Ergebnisse werden verglichen
(``--compare``). Wenn `old_count != new_count` gilt oder eine ID verschwindet,
steht es im Diff, statt drei Wochen spaeter in einem Bericht zu fehlen.

Was es NICHT ist
----------------
Es prueft nicht, ob ein Restore funktioniert — das tut
``backend/scripts/restore_verify.py``. Es sichert nichts — das tut
``scripts/restore-drill.sh``. Es liest ausschliesslich und schreibt nur die
Manifestdatei.

Es vergleicht auch keine LLM- oder Simulationsausgaben byteweise. Diese Laeufe
sind nicht deterministisch; ein gespeicherter ``random_seed`` macht einen Lauf
nicht reproduzierbar. Verglichen wird die *Struktur* der Persistenz, nicht der
erzeugte Text.

Was nie im Manifest steht
-------------------------
Keine Dateiinhalte und keine Geheimnisse. Die Spalte ``api_key`` aus
``instance/llm_profiles.db`` wird nicht gelesen; von den Fernet-Stores unter
``backend/data/`` wird ausschliesslich die Eintragsanzahl erhoben, nie ein Wert.
Ein Manifest ist zum Weitergeben gedacht — es muss sich an ein Issue haengen
lassen, ohne vorher durchgesehen zu werden.

Aufruf::

    uv run python scripts/migration_baseline.py --data-dir uploads --store-dir data
    uv run python scripts/migration_baseline.py --data-dir uploads --output baseline-vorher.json
    uv run python scripts/migration_baseline.py --compare baseline-vorher.json baseline-nachher.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

#: Dateien ab dieser Groesse werden gehasht, aber gestreamt statt am Stueck
#: gelesen. Simulationsdatenbanken erreichen zweistellige Megabyte.
_HASH_CHUNK = 1024 * 1024


@dataclass
class ClassSnapshot:
    """Eine Objektklasse aus §6 mit ihren Migrationsinvarianten.

    ``records`` bildet die ID auf genau die Felder ab, die eine Migration
    unveraendert lassen muss: Status, Zeitstempel und Referenzen. Alles andere
    bleibt draussen — ein Manifest, das den halben Datensatz mitfuehrt, ist ein
    Datenexport und kein Vergleichsmassstab.
    """

    name: str
    count: int = 0
    records: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    #: Gesetzt, wenn die Quelle nicht erreichbar war. Ausdruecklich NICHT
    #: dasselbe wie ``count == 0``: eine fehlende Quelle darf im Vergleich nicht
    #: als „alles geloescht" durchgehen.
    unchecked: bool = False
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "unchecked": self.unchecked,
            "detail": self.detail,
            "ids": sorted(self.records),
            "records": {k: self.records[k] for k in sorted(self.records)},
        }


@dataclass
class BaselineManifest:
    commit: str
    version: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    classes: List[ClassSnapshot] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)
    artifacts_unchecked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commit": self.commit,
            "version": self.version,
            "created_at": self.created_at,
            "classes": [c.to_dict() for c in self.classes],
            "artifacts": dict(sorted(self.artifacts.items())),
            "artifacts_unchecked": self.artifacts_unchecked,
        }


# ---------------------------------------------------------------------------
# Lesehelfer
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    """Liest eine JSON-Datei. Gibt ``None`` zurueck, statt den Lauf abzubrechen.

    Eine einzelne kaputte Datei darf ein Manifest nicht verhindern — sie soll
    im Ergebnis fehlen und dadurch im Vergleich auffallen.
    """
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _pick(data: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    """Uebernimmt genau die benannten Felder, fehlende als ``None``."""
    return {k: data.get(k) for k in keys}


def _sha256(path: Path) -> Optional[str]:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while chunk := fh.read(_HASH_CHUNK):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _git_commit(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


def _version(repo_root: Path) -> str:
    path = repo_root / "VERSION"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


# ---------------------------------------------------------------------------
# Klassen aus dem Artefaktverzeichnis
# ---------------------------------------------------------------------------


def snapshot_projects(data_dir: Path) -> ClassSnapshot:
    snap = ClassSnapshot(name="projects")
    root = data_dir / "projects"
    if not root.is_dir():
        snap.unchecked = True
        snap.detail = f"{root} fehlt"
        return snap
    for entry in sorted(root.glob("proj_*")):
        meta = _read_json(entry / "project.json")
        if meta is None:
            continue
        pid = str(meta.get("project_id") or entry.name)
        snap.records[pid] = _pick(
            meta, "status", "created_at", "updated_at", "graph_id"
        )
    snap.count = len(snap.records)
    return snap


def snapshot_simulations(data_dir: Path) -> ClassSnapshot:
    snap = ClassSnapshot(name="simulations")
    root = data_dir / "simulations"
    if not root.is_dir():
        snap.unchecked = True
        snap.detail = f"{root} fehlt"
        return snap
    for entry in sorted(root.glob("sim_*")):
        state = _read_json(entry / "state.json")
        if state is None:
            continue
        sid = str(state.get("simulation_id") or entry.name)
        snap.records[sid] = _pick(
            state,
            "status",
            "created_at",
            "updated_at",
            "project_id",
            "graph_id",
            "source_simulation_id",
            "root_simulation_id",
        )
    snap.count = len(snap.records)
    return snap


def snapshot_runs(data_dir: Path) -> ClassSnapshot:
    snap = ClassSnapshot(name="runs")
    root = data_dir / "run_registry"
    if not root.is_dir():
        snap.unchecked = True
        snap.detail = f"{root} fehlt"
        return snap
    for entry in sorted(root.glob("*.json")):
        run = _read_json(entry)
        if run is None:
            continue
        rid = str(run.get("run_id") or entry.stem)
        snap.records[rid] = _pick(
            run,
            "run_type",
            "status",
            "started_at",
            "updated_at",
            "completed_at",
            "entity_id",
            "parent_run_id",
        )
    snap.count = len(snap.records)
    return snap


def snapshot_reports(data_dir: Path) -> ClassSnapshot:
    snap = ClassSnapshot(name="reports")
    root = data_dir / "reports"
    if not root.is_dir():
        snap.unchecked = True
        snap.detail = f"{root} fehlt"
        return snap
    for entry in sorted(root.glob("report_*")):
        meta = _read_json(entry / "meta.json")
        if meta is None:
            continue
        rid = str(meta.get("report_id") or entry.name)
        snap.records[rid] = _pick(
            meta,
            "status",
            "created_at",
            "completed_at",
            "simulation_id",
            "graph_id",
            "has_evidence",
        )
    snap.count = len(snap.records)
    return snap


def snapshot_personas(data_dir: Path) -> ClassSnapshot:
    """Personas liegen pro Simulation, nicht in einem zentralen Store.

    Gezaehlt wird deshalb je Simulation; die ID ist die Simulation, der Wert
    ihre Personazahl. Ein zentraler Personasatz-Zaehler waere eine Summe ohne
    Zuordnung und wuerde eine Verschiebung zwischen zwei Simulationen nicht
    sichtbar machen.
    """
    snap = ClassSnapshot(name="personas")
    root = data_dir / "simulations"
    if not root.is_dir():
        snap.unchecked = True
        snap.detail = f"{root} fehlt"
        return snap
    total = 0
    for entry in sorted(root.glob("sim_*")):
        path = entry / "reddit_profiles.json"
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8") as fh:
                profiles = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(profiles, list):
            continue
        snap.records[entry.name] = {"persona_count": len(profiles)}
        total += len(profiles)
    snap.count = total
    snap.detail = f"{len(snap.records)} Simulationen mit Personasatz"
    return snap


# ---------------------------------------------------------------------------
# Klassen ausserhalb des Artefaktverzeichnisses
# ---------------------------------------------------------------------------


def snapshot_llm_profiles(instance_dir: Path) -> ClassSnapshot:
    """LLM-Profile aus ``instance/llm_profiles.db``.

    Die Spalte ``api_key`` wird bewusst nicht in die Abfrage aufgenommen — sie
    steht dort im Klartext (``llm_profiles_store.py``) und hat in einem
    weitergebbaren Manifest nichts verloren. ``base_url`` und ``model_name``
    bleiben aus demselben Grund draussen: eine Basis-URL kann ein Token
    tragen, und fuer die Migrationsinvariante reichen ID, Zuordnung und
    Zeitstempel.
    """
    snap = ClassSnapshot(name="llm_profiles")
    db_path = instance_dir / "llm_profiles.db"
    if not db_path.is_file():
        snap.unchecked = True
        snap.detail = f"{db_path} fehlt"
        return snap
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as exc:
        snap.unchecked = True
        snap.detail = f"nicht lesbar: {type(exc).__name__}"
        return snap
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, provider, is_default, created_at, updated_at FROM llm_profiles"
        ).fetchall()
    except sqlite3.Error as exc:
        snap.unchecked = True
        snap.detail = f"Abfrage fehlgeschlagen: {type(exc).__name__}"
        return snap
    finally:
        conn.close()
    for row in rows:
        snap.records[str(row["id"])] = {
            "provider": row["provider"],
            "is_default": bool(row["is_default"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    snap.count = len(snap.records)
    return snap


def snapshot_graph() -> List[ClassSnapshot]:
    """Knoten je Label und Kanten aus Neo4j.

    Verbindung ueber dieselben Umgebungsvariablen wie die Anwendung. Ist die
    Datenbank nicht erreichbar — im lokalen Lauf der Normalfall — werden beide
    Klassen als ungeprueft ausgewiesen. Ein Manifest, das eine abwesende
    Datenbank als „null Knoten" fuehrt, wuerde bei einem spaeteren Vergleich
    genau das Gegenteil dessen behaupten, was es soll.
    """
    nodes = ClassSnapshot(name="graph_nodes")
    edges = ClassSnapshot(name="graph_edges")
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")

    try:
        from neo4j import GraphDatabase
    except ImportError:
        for snap in (nodes, edges):
            snap.unchecked = True
            snap.detail = "neo4j-Treiber nicht installiert"
        return [nodes, edges]

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            for label in ("Graph", "Entity", "Episode"):
                result = session.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()
                count = int(result["c"]) if result else 0
                nodes.records[label] = {"count": count}
                nodes.count += count
            result = session.run(
                "MATCH ()-[r:RELATION]->() RETURN count(r) AS c"
            ).single()
            edges.count = int(result["c"]) if result else 0
            edges.records["RELATION"] = {"count": edges.count}
        driver.close()
    except Exception as exc:  # noqa: BLE001 — jede Treiberstoerung heisst „ungeprueft"
        for snap in (nodes, edges):
            snap.unchecked = True
            snap.count = 0
            snap.records.clear()
            snap.detail = f"Neo4j nicht erreichbar: {type(exc).__name__}"
    return [nodes, edges]


def snapshot_artifacts(data_dir: Path) -> tuple[Dict[str, str], bool]:
    """sha256 je Datei unter dem Artefaktverzeichnis, Pfad relativ zu diesem."""
    if not data_dir.is_dir():
        return {}, True
    sums: Dict[str, str] = {}
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file():
            continue
        digest = _sha256(path)
        # Eine unlesbare Datei faellt nicht aus dem Manifest, sondern bekommt
        # einen Marker. Verschwaende sie stillschweigend und waere sie in
        # beiden Laeufen unlesbar, ginge der Vergleich glatt durch, obwohl
        # niemand hingesehen hat.
        sums[str(path.relative_to(data_dir))] = digest or "<nicht lesbar>"
    return sums, False


# ---------------------------------------------------------------------------
# Manifest und Vergleich
# ---------------------------------------------------------------------------


def build_manifest(
    repo_root: Path,
    data_dir: Path,
    instance_dir: Path,
    *,
    with_checksums: bool = True,
    with_graph: bool = True,
) -> BaselineManifest:
    manifest = BaselineManifest(
        commit=_git_commit(repo_root), version=_version(repo_root)
    )
    manifest.classes = [
        snapshot_projects(data_dir),
        snapshot_simulations(data_dir),
        snapshot_runs(data_dir),
        snapshot_reports(data_dir),
        snapshot_personas(data_dir),
        snapshot_llm_profiles(instance_dir),
    ]
    if with_graph:
        manifest.classes.extend(snapshot_graph())
    else:
        for name in ("graph_nodes", "graph_edges"):
            manifest.classes.append(
                ClassSnapshot(name=name, unchecked=True, detail="per --skip-graph ausgelassen")
            )
    if with_checksums:
        manifest.artifacts, manifest.artifacts_unchecked = snapshot_artifacts(data_dir)
    else:
        manifest.artifacts_unchecked = True
    return manifest


def compare(
    before: Dict[str, Any], after: Dict[str, Any]
) -> tuple[List[str], List[str]]:
    """Vergleicht zwei Manifeste.

    Gibt ``(abweichungen, ungeprueft)`` zurueck. Die Trennung ist dieselbe wie
    in ``restore_verify.py``: ein uebersprungener Punkt ist kein Erfolg, aber
    auch kein Fehlschlag — er faerbt den Lauf gelb, nicht gruen und nicht rot.
    """
    findings: List[str] = []
    unchecked: List[str] = []
    old = {c["name"]: c for c in before.get("classes", [])}
    new = {c["name"]: c for c in after.get("classes", [])}

    for name in sorted(set(old) | set(new)):
        a, b = old.get(name), new.get(name)
        if a is None or b is None:
            findings.append(f"{name}: nur in einem der beiden Manifeste vorhanden")
            continue
        if a.get("unchecked") or b.get("unchecked"):
            unchecked.append(f"{name}: Quelle war nicht erreichbar")
            continue
        if a["count"] != b["count"]:
            findings.append(f"{name}: Anzahl {a['count']} -> {b['count']}")
        missing = set(a["ids"]) - set(b["ids"])
        added = set(b["ids"]) - set(a["ids"])
        if missing:
            findings.append(f"{name}: {len(missing)} ID(s) verschwunden, z. B. {sorted(missing)[:3]}")
        if added:
            findings.append(f"{name}: {len(added)} ID(s) neu, z. B. {sorted(added)[:3]}")
        for rid in sorted(set(a["ids"]) & set(b["ids"])):
            if a["records"][rid] != b["records"][rid]:
                findings.append(f"{name}/{rid}: Felder abweichend")

    if before.get("artifacts_unchecked") or after.get("artifacts_unchecked"):
        unchecked.append("artifacts: ohne Pruefsummen erzeugt")
    else:
        for path in sorted(set(before["artifacts"]) | set(after["artifacts"])):
            old_sum = before["artifacts"].get(path)
            new_sum = after["artifacts"].get(path)
            if old_sum != new_sum:
                findings.append(f"artifacts/{path}: Pruefsumme abweichend")
    return findings, unchecked


def render(manifest: BaselineManifest) -> str:
    lines = [
        "Migrations-Baseline",
        f"  Commit:  {manifest.commit}",
        f"  Version: {manifest.version}",
        f"  Erzeugt: {manifest.created_at}",
        "",
    ]
    for snap in manifest.classes:
        mark = "ungeprueft" if snap.unchecked else str(snap.count)
        suffix = f"  ({snap.detail})" if snap.detail else ""
        lines.append(f"  {snap.name:<14} {mark:>10}{suffix}")
    artifacts = (
        "ungeprueft" if manifest.artifacts_unchecked else str(len(manifest.artifacts))
    )
    lines.append(f"  {'artifacts':<14} {artifacts:>10}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("uploads"),
        help="Artefaktverzeichnis (backend/uploads)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository-Wurzel fuer Commit und VERSION",
    )
    parser.add_argument("--output", type=Path, help="Manifest als JSON hierhin schreiben")
    parser.add_argument("--json", action="store_true", help="Manifest auf stdout")
    parser.add_argument(
        "--instance-dir",
        type=Path,
        default=Path("instance"),
        help="Instanzverzeichnis mit llm_profiles.db (backend/instance)",
    )
    parser.add_argument(
        "--skip-checksums",
        action="store_true",
        help="Artefaktpruefsummen auslassen (schnell, aber ohne Inhaltsnachweis)",
    )
    parser.add_argument(
        "--skip-graph",
        action="store_true",
        help="Neo4j nicht abfragen (die beiden Graph-Klassen bleiben ungeprueft)",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("VORHER", "NACHHER"),
        type=Path,
        help="Zwei Manifeste vergleichen statt eines zu erzeugen",
    )
    args = parser.parse_args(argv)

    if args.compare:
        before, after = (json.loads(p.read_text(encoding="utf-8")) for p in args.compare)
        findings, unchecked = compare(before, after)
        if findings:
            print(f"{len(findings)} Abweichung(en):")
            for line in findings:
                print(f"  - {line}")
        if unchecked:
            print(f"{len(unchecked)} Punkt(e) ungeprueft:")
            for line in unchecked:
                print(f"  - {line}")
        if findings:
            return 1
        if unchecked:
            print("Kein Unterschied gefunden, aber nicht alles war vergleichbar.")
            return 2
        print("Baseline identisch: Anzahl, IDs, Felder und Pruefsummen unveraendert.")
        return 0

    manifest = build_manifest(
        args.repo_root,
        args.data_dir,
        args.instance_dir,
        with_checksums=not args.skip_checksums,
        with_graph=not args.skip_graph,
    )
    payload = manifest.to_dict()
    if args.output:
        args.output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render(manifest))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
