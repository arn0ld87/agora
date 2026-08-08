"""Dump JSON schemas of all Pydantic contracts.

Modi:
  python -m app.contracts.dump_schemas          # schreibt schemas/
  python -m app.contracts.dump_schemas --check  # vergleicht byte-genau, exit 1 bei Drift

CI-Verhalten (--check):
    Gibt GitHub-Actions-kompatible ::error::-Annotationen aus bei Drift.
    Exit 1 blockiert den Merge. Alle Schemas werden geprueft (kein Kurzschluss).
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
from app.contracts.persona_target_contract import PersonaTargetContract
from app.contracts.pipeline_degradation_contract import (
    PipelineDegradationModel,
    PipelineDegradationReport,
)
from app.contracts.report_contract import EvidenceMapModel, ReportContractModel, ReportModel
from app.contracts.report_v3 import ReportV3
from app.contracts.run_budget_contract import (
    PreflightEstimate,
    RunBudgetConfig,
    RunBudgetStatus,
    RunUsage,
)
from app.contracts.runs_contract import RunDetail, RunsListResponse, RunSummary
from app.contracts.system_status_contract import SystemStatusE2E, SystemStatusOllama
from app.contracts.llm_routing_contract import (
    RuntimeLlmRouting,
    ProviderDescriptor,
    ResolvedRoute,
    ModelEntry,
)
from app.contracts.api_keys_contract import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyModel,
    ApiKeysListResponse,
)
from app.contracts.llm_profile_contract import (
    LlmProfile,
    LlmProfileListResponse,
    LlmProfileCreateRequest,
)
from app.contracts.llm_provider_keys_contract import (
    LlmProviderKeyCreateRequest,
    LlmProviderKeyEntry,
    LlmProviderKeysListResponse,
)
from app.contracts.workspace_routing_contract import WorkspaceLlmRoutingDefaults
from app.contracts.post_event_contract import PostCreatedEvent
from app.contracts.llm_request import (
    NormalizedLlmRequest,
    NormalizedLlmChunk,
    NormalizedLlmError,
)
from app.contracts.ai_provider_contract import AiModel, AiRoute, ProviderConnection
from app.contracts.user_profile_contract import (
    OnboardingState,
    OnboardingStatusResponse,
    OnboardingStepUpdateRequest,
    UserProfile,
    UserProfileUpdateRequest,
)
from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingConfigurationResponse,
    EmbeddingConfigurationUpsertRequest,
    EmbeddingIndexVersion,
    EmbeddingMigrationJob,
    EmbeddingMigrationJobResponse,
    EmbeddingModelMetadata,
)
from app.contracts.interview_envelope_contract import InterviewEnvelope

# schemas/ liegt im Repo-Root, dump_schemas.py liegt in backend/app/contracts/
OUT_DIR = Path(__file__).resolve().parents[3] / "schemas"

CONTRACTS: dict[str, type] = {
    "branch-comparison.schema.json": BranchComparison,
    "graph-diff.schema.json": GraphDiff,
    "persona-entity-context.schema.json": PersonaEntityContext,
    # Pipeline-Degradierung (Issue #1029)
    "pipeline-degradation.schema.json": PipelineDegradationModel,
    "pipeline-degradation-report.schema.json": PipelineDegradationReport,
    "report-contract.schema.json": ReportContractModel,
    "report.schema.json": ReportModel,
    "evidence-map.schema.json": EvidenceMapModel,
    "persona.schema.json": PersonaModel,
    "persona-quota-plan.schema.json": PersonaQuotaPlan,
    # Persona-Ziel für den Fortschrittszähler (Issue #1034)
    "persona-target.schema.json": PersonaTargetContract,
    "report-v3.schema.json": ReportV3,
    "run-summary.schema.json": RunSummary,
    "runs-list-response.schema.json": RunsListResponse,
    "run-detail.schema.json": RunDetail,
    "run-budget-config.schema.json": RunBudgetConfig,
    "run-budget-status.schema.json": RunBudgetStatus,
    "run-usage.schema.json": RunUsage,
    "run-preflight-estimate.schema.json": PreflightEstimate,
    "llm-runtime-routing.schema.json": RuntimeLlmRouting,
    "llm-provider-descriptor.schema.json": ProviderDescriptor,
    "llm-resolved-route.schema.json": ResolvedRoute,
    "llm-model-entry.schema.json": ModelEntry,
    "api-key.schema.json": ApiKeyModel,
    "api-key-create-request.schema.json": ApiKeyCreateRequest,
    "api-key-create-response.schema.json": ApiKeyCreateResponse,
    "api-keys-list-response.schema.json": ApiKeysListResponse,
    "llm-profile.schema.json": LlmProfile,
    "llm-profile-list-response.schema.json": LlmProfileListResponse,
    "llm-profile-create-request.schema.json": LlmProfileCreateRequest,
    "llm-provider-key-entry.schema.json": LlmProviderKeyEntry,
    "llm-provider-key-create-request.schema.json": LlmProviderKeyCreateRequest,
    "llm-provider-keys-list-response.schema.json": LlmProviderKeysListResponse,
    "workspace-llm-routing-defaults.schema.json": WorkspaceLlmRoutingDefaults,
    "post-created-event.schema.json": PostCreatedEvent,
    "llm-normalized-request.schema.json": NormalizedLlmRequest,
    "llm-normalized-chunk.schema.json": NormalizedLlmChunk,
    "llm-normalized-error.schema.json": NormalizedLlmError,
    "ai-provider-connection.schema.json": ProviderConnection,
    "ai-model.schema.json": AiModel,
    "ai-route.schema.json": AiRoute,
    "user-profile.schema.json": UserProfile,
    "user-profile-update-request.schema.json": UserProfileUpdateRequest,
    "onboarding-state.schema.json": OnboardingState,
    "onboarding-step-update-request.schema.json": OnboardingStepUpdateRequest,
    "onboarding-status-response.schema.json": OnboardingStatusResponse,
    "system-status-ollama.schema.json": SystemStatusOllama,
    "system-status-e2e.schema.json": SystemStatusE2E,
    # Embedding (Slice 4.1)
    "embedding-configuration.schema.json": EmbeddingConfiguration,
    "embedding-configuration-upsert-request.schema.json": EmbeddingConfigurationUpsertRequest,
    "embedding-configuration-response.schema.json": EmbeddingConfigurationResponse,
    "embedding-migration-job.schema.json": EmbeddingMigrationJob,
    "embedding-migration-job-response.schema.json": EmbeddingMigrationJobResponse,
    "embedding-index-version.schema.json": EmbeddingIndexVersion,
    "embedding-model-metadata.schema.json": EmbeddingModelMetadata,
    # Interview-Envelope (Issue #1005)
    "interview-envelope.schema.json": InterviewEnvelope,
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
    """Vergleicht ein Schema byte-genau gegen die Datei auf Disk.

    Gibt GitHub-Actions-kompatible ::error::-Zeile bei Drift aus.
    Returns True wenn clean, False bei Drift oder fehlendem File.
    """
    path = OUT_DIR / filename
    expected = render_schema(filename, model)
    rel = f"schemas/{filename}"

    if not path.exists():
        sys.stderr.write(
            f"::error::Schema-Drift (MAI-04): Datei fehlt auf Disk: {rel}\n"
            f"  Fix: cd backend && uv run python -m app.contracts.dump_schemas"
            f" && git add schemas/\n"
        )
        return False

    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        sys.stderr.write(
            f"::error::Schema-Drift (MAI-04): Inhalt weicht ab: {rel}\n"
            f"  Fix: cd backend && uv run python -m app.contracts.dump_schemas"
            f" && git add schemas/\n"
        )
        return False

    sys.stdout.write(f"OK: {rel}\n")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dump or check Pydantic JSON schemas.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Vergleicht regenerierte Schemas byte-genau gegen schemas/ "
            "(exit 1 bei Drift). Alle Schemas werden geprueft."
        ),
    )
    args = parser.parse_args(argv)

    if args.check:
        # Alle Schemas pruefen — kein all()-Kurzschluss, damit alle Drift-Zeilen sichtbar sind.
        results = [check_one(filename, model) for filename, model in CONTRACTS.items()]
        ok = all(results)
        if not ok:
            n_drift = results.count(False)
            sys.stderr.write(
                f"::error::Schema-Drift (MAI-04): {n_drift} von {len(results)} Schemas"
                " weichen ab. Regenerieren mit:"
                " cd backend && uv run python -m app.contracts.dump_schemas"
                " && git add schemas/\n"
            )
            return 1
        sys.stdout.write(f"OK: alle {len(results)} Schemas matchen schemas/\n")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, model in CONTRACTS.items():
        path = dump_one(filename, model)
        sys.stdout.write(f"OK: {path.relative_to(OUT_DIR.parent)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
