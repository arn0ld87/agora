"""
CLI: dumpt alle Pydantic-Contracts als JSON Schema 2020-12 nach schemas/.

Aufruf:
    cd backend && uv run python -m app.contracts.dump_schemas

CI-Verhalten:
    Nach dump muss `git diff --exit-code schemas/` sauber sein —
    sonst hat Backend Schemas geändert ohne Frontend-Regen.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.contracts.branch_comparison import BranchComparison
from app.contracts.graph_diff import GraphDiff
from app.contracts.persona_contract import PersonaModel, PersonaQuotaPlan
from app.contracts.persona_entity_context import PersonaEntityContext
from app.contracts.report_contract import EvidenceMapModel, ReportContractModel, ReportModel
from app.contracts.report_v3 import ReportV3
from app.contracts.runs_contract import RunDetail, RunsListResponse, RunSummary
from app.contracts.llm_routing_contract import (
    RuntimeLlmRouting,
    ProviderDescriptor,
    ResolvedRoute,
)
from app.contracts.api_keys_contract import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyModel,
    ApiKeysListResponse,
)

# schemas/ liegt im Repo-Root, dump_schemas.py liegt in backend/app/contracts/
OUT_DIR = Path(__file__).resolve().parents[3] / "schemas"

CONTRACTS: dict[str, type] = {
    "branch-comparison.schema.json": BranchComparison,
    "graph-diff.schema.json": GraphDiff,
    "persona-entity-context.schema.json": PersonaEntityContext,
    "report-contract.schema.json": ReportContractModel,
    "report.schema.json": ReportModel,
    "evidence-map.schema.json": EvidenceMapModel,
    "persona.schema.json": PersonaModel,
    "persona-quota-plan.schema.json": PersonaQuotaPlan,
    "report-v3.schema.json": ReportV3,
    "run-summary.schema.json": RunSummary,
    "runs-list-response.schema.json": RunsListResponse,
    "run-detail.schema.json": RunDetail,
    "llm-runtime-routing.schema.json": RuntimeLlmRouting,
    "llm-provider-descriptor.schema.json": ProviderDescriptor,
    "llm-resolved-route.schema.json": ResolvedRoute,
    "api-key.schema.json": ApiKeyModel,
    "api-key-create-request.schema.json": ApiKeyCreateRequest,
    "api-key-create-response.schema.json": ApiKeyCreateResponse,
    "api-keys-list-response.schema.json": ApiKeysListResponse,
}


def render_schema(filename: str, model: type) -> str:
    schema = model.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://alexle135.de/schemas/{filename}"
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def dump_one(filename: str, model: type) -> Path:
    path = OUT_DIR / filename
    path.write_text(render_schema(filename, model), encoding="utf-8")
    return path


def check_one(filename: str, model: type) -> bool:
    path = OUT_DIR / filename
    expected = render_schema(filename, model)
    if not path.exists():
        print(f"missing: {path.relative_to(OUT_DIR.parent)}", file=sys.stderr)
        return False
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        print(f"drift: {path.relative_to(OUT_DIR.parent)}", file=sys.stderr)
        return False
    print(f"✓ {path.relative_to(OUT_DIR.parent)}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="nur prüfen, ob schemas/ dem aktuellen Pydantic-Stand entspricht",
    )
    args = parser.parse_args(argv)

    if args.check:
        return 0 if all(check_one(filename, model) for filename, model in CONTRACTS.items()) else 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, model in CONTRACTS.items():
        path = dump_one(filename, model)
        print(f"\u2713 {path.relative_to(OUT_DIR.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
