"""ManifestCapture — Draft- und Final-Manifest schreiben (Issue #763, Ticket 2+3+9)."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

from app.contracts.run_manifest_contract import (
    ManifestDeviation,
    ManifestInputs,
    ManifestPrompts,
    ManifestRouting,
    ManifestRuntime,
    ManifestSeeds,
    ManifestSimulationParams,
    ManifestVersions,
    PromptSnapshot,
    RunManifest,
    StageRoute,
)
from app.models.project import ProjectManager

logger = logging.getLogger("agora.manifest_capture")

#: Site-packages-Pfadende der Datei, die den System-Prompt fuer jede
#: OASIS-Persona pro Runde baut (``UserInfo.to_system_message``, Issue #1274
#: Punkt 5). Agora uebergibt kein eigenes ``user_info_template`` — die
#: Default-Implementierung der gepinnten ``camel-oasis``-Version bestimmt den
#: tatsaechlichen Prompt-Inhalt der ``simulation_rounds``-Stage vollstaendig.
_OASIS_USER_PROMPT_MODULE_SUFFIX = "oasis/social_platform/config/user.py"


def _write_manifest(manifest_path: str, manifest: RunManifest) -> None:
    """Manifest atomar schreiben (tmp-File + ``os.replace``).

    Ein direkter ``open(..., "w")`` würde ein vorhandenes gültiges Manifest
    bereits beim Öffnen abschneiden; bricht der Dump danach ab, bleibt eine
    Ruine zurück. Zusätzlich können ``GET /manifest`` und der ZIP-Export
    parallel lesen und dabei halbfertiges JSON erwischen.

    Bewusst lokal statt über ``utils.json_io``: der Guard in
    ``tests/test_no_json_io_leakage.py`` reserviert diesen Helper für den
    ``SimulationArtifactStore``-Adapter. Das Manifest braucht außerdem
    ``sort_keys=True`` für stabile Diffs zwischen Draft und Final.
    """
    directory = os.path.dirname(manifest_path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-manifest-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest.model_dump(mode="json"), handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, manifest_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


class ManifestCapture:
    """Erzeugt und schreibt Run-Manifeste (draft/final)."""

    @staticmethod
    def capture_draft(
        *,
        run_id: str,
        run_dir: str,
        seed_document_hash: str | None,
        seed_document_filename: str | None,
        simulation_config_hash: str,
        graph_id: str,
        agora_version: str,
        schema_version: str,
        random_seed: int | None = None,
        simulation_id_seed: str | None = None,
        graph_version: str | None = None,
        embedding_version: str | None = None,
        routing: dict[str, dict[str, Any]] | None = None,
        prompts: dict[str, dict[str, str]] | None = None,
        platform: str | None = None,
        max_rounds: int | None = None,
        enable_graph_memory_update: bool | None = None,
        memory_update_graph_id: str | None = None,
        replayed_from_run_id: str | None = None,
        deviations: list[dict[str, Any]] | None = None,
    ) -> None:
        """Schreibt ein Draft-Manifest in das Run-Verzeichnis.

        ``routing`` (optional): {stage_id: {model, provider, base_url,
        ai_route_snapshot}} — Stage-Routing-Snapshots zum Zeitpunkt des
        Run-Starts (Issue #763, Ticket 9; ``ai_route_snapshot`` seit Issue
        #1274 Punkt 2). ``prompts`` (optional): {key: {content, source_file}}
        — byte-genaue Prompt-Modul-Snapshots (Issue #1274 Punkt 5).
        ``platform``/``max_rounds``/``enable_graph_memory_update`` bilden
        zusammen mit ``memory_update_graph_id`` die 1:1-Replay-Parameter
        (Issue #1274 Punkt 3); ohne ``platform`` und
        ``enable_graph_memory_update`` bleibt ``RunManifest.simulation``
        ``None`` statt mit Platzhaltern befüllt zu werden.
        """
        stages = {
            stage_id: StageRoute(**route) for stage_id, route in (routing or {}).items()
        }
        prompt_entries = {
            key: PromptSnapshot(**entry) for key, entry in (prompts or {}).items()
        }
        simulation_params = None
        if platform is not None and enable_graph_memory_update is not None:
            simulation_params = ManifestSimulationParams(
                platform=platform,
                max_rounds=max_rounds,
                enable_graph_memory_update=enable_graph_memory_update,
                memory_update_graph_id=memory_update_graph_id,
            )
        manifest = RunManifest(
            schema_version=1,
            run_id=run_id,
            replayed_from_run_id=replayed_from_run_id,
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
            prompts=ManifestPrompts(entries=prompt_entries),
            seeds=ManifestSeeds(
                random_seed=random_seed,
                simulation_id_seed=simulation_id_seed,
            ),
            simulation=simulation_params,
            deviations=[ManifestDeviation(**d) for d in (deviations or [])],
            status="draft",
        )

        os.makedirs(run_dir, exist_ok=True)
        _write_manifest(os.path.join(run_dir, "manifest.json"), manifest)

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

        _write_manifest(manifest_path, manifest)

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
        aus den Run-Metadaten; nicht rekonstruierbare Felder bleiben ``None``
        (Issue #1274 Punkt 4) statt fabrizierter Platzhalter wie dem früheren
        ``random_seed=0``/``simulation_id_seed="legacy"``. ``"unknown"`` bleibt
        ausschließlich für Felder, die im Vertrag Pflicht-Strings sind
        (``simulation_config_hash``, ``graph_id``) — dort ist kein ``None``
        vorgesehen.
        """
        manifest_path = os.path.join(run_dir, "manifest.json")
        if os.path.exists(manifest_path):
            return  # Kein Überschreiben

        started_at_str = run_metadata.get("started_at")
        parsed_started_at: datetime | None = None
        if started_at_str:
            try:
                parsed = datetime.fromisoformat(started_at_str)
                # RunRegistry.create_run schreibt started_at als naives
                # datetime.now().isoformat() — ohne Coercion wäre dieser Wert
                # nicht mit den tz-aware Werten aus capture_draft vergleichbar
                # (TypeError bei Subtraktion/Vergleich).
                parsed_started_at = (
                    parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
                )
            except (ValueError, TypeError):
                pass
        # captured_at (Migrationszeitpunkt) und runtime.started_at
        # (Run-Startzeitpunkt) sind unterschiedliche Zeitpunkte — captured_at
        # darf auf "jetzt" zurückfallen, runtime.started_at nicht: ein
        # fabriziertes "jetzt" als angeblicher Original-Run-Start wäre selbst
        # der Fehler, den dieses Ticket beheben soll.
        captured_at = parsed_started_at or datetime.now(timezone.utc)

        runtime = None
        if parsed_started_at is not None:
            completed_at_str = run_metadata.get("completed_at")
            parsed_completed_at: datetime | None = None
            if completed_at_str:
                try:
                    parsed_completed = datetime.fromisoformat(completed_at_str)
                    parsed_completed_at = (
                        parsed_completed.replace(tzinfo=timezone.utc)
                        if parsed_completed.tzinfo is None
                        else parsed_completed
                    )
                except (ValueError, TypeError):
                    pass
            status = run_metadata.get("status")
            if parsed_completed_at is not None or status is not None:
                runtime = ManifestRuntime(
                    started_at=parsed_started_at,
                    completed_at=parsed_completed_at,
                    termination_reason=str(status) if status is not None else None,
                )

        graph_id = run_metadata.get("graph_id", "unknown")
        seed_document_filename = run_metadata.get("document_name")

        llm_model = run_metadata.get("llm_model")
        llm_provider = run_metadata.get("llm_provider")
        stages: dict[str, StageRoute] = {}
        if llm_model is not None and llm_provider is not None:
            stages["simulation_rounds"] = StageRoute(model=llm_model, provider=llm_provider)

        manifest = RunManifest(
            schema_version=1,
            run_id=run_id,
            captured_at=captured_at,
            inputs=ManifestInputs(
                seed_document_hash=None,
                seed_document_filename=seed_document_filename,
                simulation_config_hash="unknown",
                graph_id=graph_id,
            ),
            versions=ManifestVersions(
                agora_version=agora_version,
                schema_version=schema_version,
            ),
            routing=ManifestRouting(stages=stages),
            prompts=ManifestPrompts(entries={}),
            seeds=ManifestSeeds(
                random_seed=None,
                simulation_id_seed=run_metadata.get("simulation_id"),
            ),
            runtime=runtime,
            status="legacy",
        )

        os.makedirs(run_dir, exist_ok=True)
        _write_manifest(manifest_path, manifest)

    @staticmethod
    def seed_document_snapshot(project_id: str | None) -> tuple[str | None, str | None]:
        """Reale (Hash, Dateiname)-Werte des Projekt-Quelltexts (Issue #1274 Punkt 6).

        ``ProjectManager.get_extracted_text`` liefert den rohen, kombinierten
        Upload-Text (ADR-0013); das Dokument-Manifest liefert die
        Original-Dateinamen. Fehlt beides (Altprojekt ohne Sidecar, Text
        gelöscht, kein ``project_id``), bleibt ``(None, None)`` — ein
        fabrizierter Wert wäre hier falsche Evidenz.
        """
        if not project_id:
            return None, None
        text = ProjectManager.get_extracted_text(project_id)
        seed_hash = (
            f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
            if text is not None
            else None
        )

        manifest = ProjectManager.get_document_manifest(project_id)
        filenames = [entry.filename for entry in manifest.documents] if manifest else []
        filename = ",".join(filenames) if filenames else None
        return seed_hash, filename

    @staticmethod
    def oasis_prompt_snapshots() -> dict[str, dict[str, str]]:
        """Byte-genauer Snapshot des OASIS-System-Prompt-Templates (Issue #1274 Punkt 5).

        ``oasis.social_platform.config.user.UserInfo.to_system_message`` baut
        den System-Prompt für jede Persona jeder Simulationsrunde; Agora
        übergibt der Environment kein eigenes ``user_info_template``, das
        Standardverhalten der gepinnten ``camel-oasis``-Version bestimmt den
        tatsächlichen Prompt-Inhalt also vollständig. Pfadauflösung über
        ``importlib.metadata`` statt ``import oasis`` — ein echter Import
        zöge Torch/Sentence-Transformers in den Webprozess, den OASIS sonst
        nur im separaten Simulations-Subprozess lädt. Liefert ``{}`` wenn die
        Distribution oder Datei nicht auffindbar ist, statt eine Ausnahme zu
        werfen — der Aufrufer ist ohnehin best-effort.
        """
        try:
            dist = importlib.metadata.distribution("camel-oasis")
            for file in dist.files or ():
                if file.as_posix().endswith(_OASIS_USER_PROMPT_MODULE_SUFFIX):
                    path = dist.locate_file(file)
                    with open(path, encoding="utf-8") as handle:
                        content = handle.read()
                    return {
                        "oasis_user_system_message": {
                            "content": content,
                            "source_file": (
                                f"camel-oasis=={dist.version}:{file.as_posix()}"
                            ),
                        }
                    }
        except (importlib.metadata.PackageNotFoundError, OSError):
            pass
        return {}

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
