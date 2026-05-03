"""
CLI: dumpt alle Pydantic-Contracts als JSON Schema 2020-12 nach schemas/.

Aufruf:
    cd backend && uv run python -m app.contracts.dump_schemas

CI-Verhalten:
    Nach dump muss `git diff --exit-code schemas/` sauber sein —
    sonst hat Backend Schemas geändert ohne Frontend-Regen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.contracts.branch_comparison import BranchComparison
from app.contracts.graph_diff import GraphDiff
from app.contracts.persona_contract import PersonaModel, PersonaQuotaPlan
from app.contracts.report_contract import EvidenceMapModel, ReportContractModel, ReportModel
from app.contracts.runs_contract import RunDetail, RunsListResponse, RunSummary

# schemas/ liegt im Repo-Root, dump_schemas.py liegt in backend/app/contracts/
OUT_DIR = Path(__file__).resolve().parents[3] / "schemas"

CONTRACTS: dict[str, type] = {
    "branch-comparison.schema.json": BranchComparison,
    "graph-diff.schema.json": GraphDiff,
    "report-contract.schema.json": ReportContractModel,
    "report.schema.json": ReportModel,
    "evidence-map.schema.json": EvidenceMapModel,
    "persona.schema.json": PersonaModel,
    "persona-quota-plan.schema.json": PersonaQuotaPlan,
    "run-summary.schema.json": RunSummary,
    "runs-list-response.schema.json": RunsListResponse,
    "run-detail.schema.json": RunDetail,
}


def dump_one(filename: str, model: type) -> Path:
    schema = model.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://alexle135.de/schemas/{filename}"
    path = OUT_DIR / filename
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, model in CONTRACTS.items():
        path = dump_one(filename, model)
        print(f"\u2713 {path.relative_to(OUT_DIR.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
