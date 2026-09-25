"""Gegenprobe #1240: Evidence einer evidence_map.json nach Dokument-Rolle.

Aufruf:
    uv run python scripts/evidence_role_audit.py <evidence_map.json> [<weitere …>] [--labels labels.json]

``--labels`` ordnet Snippets aus Läufen vor #1240 (ohne ``document_role``)
einer Rolle zu. Kein LLM, kein Netzwerk.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.evidence_role_audit import audit_evidence_roles  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("evidence_maps", nargs="+", type=Path)
    parser.add_argument("--labels", type=Path, default=None)
    args = parser.parse_args()

    labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else {}
    results = {
        str(path): audit_evidence_roles(json.loads(path.read_text(encoding="utf-8")), labels)
        for path in args.evidence_maps
    }
    sys.stdout.write(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
