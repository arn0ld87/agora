"""ManifestCapture — Draft- und Final-Manifest schreiben (Issue #763, Ticket 2+3+9)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from app.contracts.run_manifest_contract import (
    ManifestInputs,
    ManifestPrompts,
    ManifestRouting,
    ManifestRuntime,
    ManifestSeeds,
    ManifestVersions,
    RunManifest,
    StageRoute,
)

logger = logging.getLogger("agora.manifest_capture")


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
        routing: dict[str, dict[str, str]] | None = None,
    ) -> None:
        """Schreibt ein Draft-Manifest in das Run-Verzeichnis.

        ``routing`` (optional): {stage_id: {model, provider, base_url}} —
        Stage-Routing-Snapshots zum Zeitpunkt des Run-Starts (Issue #763,
        Ticket 9).
        """
        stages = {
            stage_id: StageRoute(
                model=route["model"],
                provider=route["provider"],
                base_url=route["base_url"],
            )
            for stage_id, route in (routing or {}).items()
        }
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
            routing=ManifestRouting(stages=stages),
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

    @staticmethod
    def migrate_legacy(
        *,
        run_id: str,
        run_dir: str,
        run_metadata: dict,
        agora_version: str,
        schema_version: str,
    ) -> None:
        """Erzeugt ein Legacy-Manifest für einen Alt-Run ohne Manifest.

        Überschreibt kein vorhandenes Manifest. Rekonstruiert bekannte Felder
        aus den Run-Metadaten; nicht rekonstruierbare Felder bleiben auf
        Platzhalter-Werten.
        """
        manifest_path = os.path.join(run_dir, "manifest.json")
        if os.path.exists(manifest_path):
            return  # Kein Überschreiben

        started_at_str = run_metadata.get("started_at")
        captured_at = datetime.now(timezone.utc)
        if started_at_str:
            try:
                captured_at = datetime.fromisoformat(started_at_str)
            except (ValueError, TypeError):
                pass

        graph_id = run_metadata.get("graph_id", "unknown")
        seed_document_filename = run_metadata.get("document_name", "unknown")

        manifest = RunManifest(
            schema_version=1,
            run_id=run_id,
            captured_at=captured_at,
            inputs=ManifestInputs(
                seed_document_hash="unknown",
                seed_document_filename=seed_document_filename,
                simulation_config_hash="unknown",
                graph_id=graph_id,
            ),
            versions=ManifestVersions(
                agora_version=agora_version,
                schema_version=schema_version,
            ),
            routing=ManifestRouting(stages={}),
            prompts=ManifestPrompts(entries={}),
            seeds=ManifestSeeds(
                random_seed=0,
                simulation_id_seed="legacy",
            ),
            status="legacy",
        )

        os.makedirs(run_dir, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.model_dump(mode="json"), f, indent=2, sort_keys=True)

    @staticmethod
    def capture_draft_best_effort(*, run_id: str, **kwargs: Any) -> None:
        """Best-Effort-Wrapper um :meth:`capture_draft` (Issue #763, Ticket 9).

        Für die Verdrahtung in echte Run-Start-Pfade: ein Manifest-Fehler
        (Disk voll, unerwartete Datenlücke) darf niemals einen laufenden
        Simulations- oder Report-Run zum Absturz bringen. Fehler werden
        geloggt und geschluckt.
        """
        try:
            ManifestCapture.capture_draft(run_id=run_id, **kwargs)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001 — best-effort, siehe Docstring
            logger.warning(
                "Manifest-Draft für run_id=%s konnte nicht geschrieben werden",
                run_id,
                exc_info=True,
            )

    @staticmethod
    def capture_final_best_effort(*, run_id: str, **kwargs: Any) -> None:
        """Best-Effort-Wrapper um :meth:`capture_final` (Issue #763, Ticket 9).

        Gleiche Begründung wie :meth:`capture_draft_best_effort`: das
        Finalisieren des Manifests am Run-Ende darf den bereits abgeschlossenen
        Run (completed/failed/stopped) nicht mehr gefährden.
        """
        try:
            ManifestCapture.capture_final(run_id=run_id, **kwargs)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001 — best-effort, siehe Docstring
            logger.warning(
                "Manifest-Final für run_id=%s konnte nicht geschrieben werden",
                run_id,
                exc_info=True,
            )
