"""ManifestCapture — Draft- und Final-Manifest schreiben (Issue #763, Ticket 2+3)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from app.contracts.run_manifest_contract import (
    ManifestInputs,
    ManifestPrompts,
    ManifestRouting,
    ManifestRuntime,
    ManifestSeeds,
    ManifestVersions,
    RunManifest,
)


class ManifestCapture:
    """Erzeugt und schreibt Run-Manifeste (draft/final)."""

    @staticmethod
    def capture_draft(
        *,
        run_id: str,
        run_dir: str,
        seed_document_hash: str,
        seed_document_filename: str,
        simulation_config_hash: str,
        graph_id: str,
        agora_version: str,
        schema_version: str,
        random_seed: int,
        simulation_id_seed: str,
        graph_version: str | None = None,
        embedding_version: str | None = None,
    ) -> None:
        """Schreibt ein Draft-Manifest in das Run-Verzeichnis."""
        manifest = RunManifest(
            schema_version=1,
            run_id=run_id,
            captured_at=datetime.now(timezone.utc),
            inputs=ManifestInputs(
                seed_document_hash=seed_document_hash,
                seed_document_filename=seed_document_filename,
                simulation_config_hash=simulation_config_hash,
                graph_id=graph_id,
                graph_version=graph_version,
                embedding_version=embedding_version,
            ),
            versions=ManifestVersions(
                agora_version=agora_version,
                schema_version=schema_version,
            ),
            routing=ManifestRouting(stages={}),
            prompts=ManifestPrompts(entries={}),
            seeds=ManifestSeeds(
                random_seed=random_seed,
                simulation_id_seed=simulation_id_seed,
            ),
            status="draft",
        )

        os.makedirs(run_dir, exist_ok=True)
        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.model_dump(mode="json"), f, indent=2, sort_keys=True)

    @staticmethod
    def capture_final(
        *,
        run_id: str,
        run_dir: str,
        started_at: datetime,
        completed_at: datetime | None = None,
        duration_seconds: int | None = None,
        rounds_completed: int | None = None,
        usage_summary: dict | None = None,
        termination_reason: str | None = None,
    ) -> None:
        """Liest das Draft-Manifest und schreibt es als final mit Runtime-Daten."""
        manifest_path = os.path.join(run_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(
                f"Kein Draft-Manifest gefunden unter {manifest_path}"
            )

        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)

        manifest = RunManifest(**data)
        manifest.status = "final"
        manifest.runtime = ManifestRuntime(
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            rounds_completed=rounds_completed,
            usage_summary=usage_summary,
            termination_reason=termination_reason,
        )

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.model_dump(mode="json"), f, indent=2, sort_keys=True)
