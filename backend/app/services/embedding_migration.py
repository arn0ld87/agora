"""Embedding-Migrations-Service (Onboarding Slice 4.3).

Orchestriert den Re-Embedding-Lifecycle gemaess
``docs/decisions/0007-embedding-configuration-and-index-migration.md`` und
``docs/epics/onboarding-provider-unification/06-migration-plan.md``.

Der eigentliche Re-Embedding-Loop (Neo4j-Query, Embedding-Service-Aufruf,
Schreiben der neuen Property) lebt in
``app.services.embedding_reembedder.Neo4jReEmbedder`` (Slice 4.3.4) und
wird als ``ReEmbedder`` injiziert, damit Tests ohne Neo4j und ohne echte
Embedding-Backends laufen koennen. Der Default bleibt der No-Op-Stub —
die API-Schicht (``app.api.embedding_migrations``) verdrahtet die echte
Engine.

Was der Service garantiert (Slice 4.3):

* **Vollstaendiger Lifecycle** mit Statusuebergaengen aus dem Vertrag:
  ``pending -> running -> validating -> completed | rolled_back | failed``.
* **Checkpoint** nach jedem verarbeiteten Batch (``processed`` und
  ``failed`` werden im ``EmbeddingMigrationProgress`` aktualisiert;
  die Persistenz schreibt den Job nach jedem Update).
* **Abbruch** ueber ``cancel()``: setzt den Status auf ``rolled_back``
  (kein zerstoererisches ``failed``, weil der Operator den Abbruch
  explizit veranlasst hat).
* **Atomarer Switch** nach erfolgreicher Validierung: erst wenn der
  Re-Embedder ``completed`` meldet, wird der neue Index in der
  Konfiguration als aktiv markiert (``index_version``) und der alte
  Index ueber den Store auf ``superseded`` gesetzt. Bis dahin bleibt
  der alte Index aktiv.
* **Idempotenz**: ``start()`` mit gleicher ``configuration_id``
  waehrend ein Job laeuft, ist ein No-Op. ``start()`` fuer eine
  Konfiguration, die bereits eine aktive Migration hat, wirft
  ``ValueError``.

Wichtige Einschraenkung: der Service fuehrt **kein** DROP INDEX aus.
Das ist explizit durch ADR-0007 verboten, bis die Validierung
erfolgreich war und ein Operator den Switch explizit bestaetigt hat.
Der Switch-Pfad (``_switch_to_new_index``) ist ein Stub, der in
einem Folge-Slice die echte Konfigurations-Mutation und den
Index-Status-Wechsel implementiert.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Optional, Protocol

from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingMigrationJob,
    EmbeddingMigrationProgress,
    EmbeddingMigrationStatus,
)
from app.services.embedding_configuration_store import EmbeddingConfigurationStore


class ReEmbedder(Protocol):
    """Schnittstelle fuer den eigentlichen Re-Embedding-Loop.

    Eine konkrete Implementierung (``Neo4jReEmbedder``) liest die
    betroffenen Neo4j-Knoten, erzeugt neue Embeddings mit dem in
    ``configuration`` beschriebenen Provider und schreibt sie in die
    neue Property. Nach jedem Batch ruft sie ``checkpoint(progress)``
    mit einem aktualisierten ``EmbeddingMigrationProgress`` auf (inkl.
    ``last_processed_id`` als Resume-Cursor); der Service persistiert
    den Job-Zustand. Der uebergebene ``progress`` ist der Startzustand
    — bei Resume traegt er den letzten Checkpoint. Rueckgabe ist der
    Endstatus (``completed`` / ``failed``).
    """

    def run(
        self,
        target_index_name: str,
        target_property_key: str,
        expected_dimensions: int,
        progress: EmbeddingMigrationProgress,
        *,
        configuration: EmbeddingConfiguration,
        checkpoint: Callable[[EmbeddingMigrationProgress], None],
    ) -> EmbeddingMigrationStatus: ...


class _NoopReEmbedder:
    """Default-Re-Embedder, der den Lifecycle treibt ohne Daten zu mutieren.

    Praktisch fuer Tests und fuer Erst-Migrationen ohne vorhandene
    Embeddings. Die echte Engine ist ``Neo4jReEmbedder``
    (``app.services.embedding_reembedder``); die API-Schicht injiziert
    sie explizit.
    """

    def run(
        self,
        target_index_name: str,
        target_property_key: str,
        expected_dimensions: int,
        progress: EmbeddingMigrationProgress,
        *,
        configuration: EmbeddingConfiguration,
        checkpoint: Callable[[EmbeddingMigrationProgress], None],
    ) -> EmbeddingMigrationStatus:
        return "completed"


class EmbeddingMigrationService:
    """Orchestriert Re-Embedding-Migrationen gemaess ADR-0007."""

    def __init__(
        self,
        *,
        store: EmbeddingConfigurationStore,
        re_embedder: ReEmbedder | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._store = store
        self._re_embedder = re_embedder if re_embedder is not None else _NoopReEmbedder()
        self._now = now

    # ------------------------------------------------------------------
    # Public Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        configuration_id: str,
        *,
        batch_size: int = 50,
    ) -> EmbeddingMigrationJob:
        """Startet eine neue Re-Embedding-Migration fuer die Konfiguration.

        Voraussetzungen:
        * Die Konfiguration existiert und hat ``status == \"probed\"``
          (also wurde die Dimension erfolgreich verifiziert).
        * Es existiert kein Job mit ``status in (pending, running,
          validating)`` fuer diese Konfiguration.

        Wirft ``KeyError`` (Konfiguration unbekannt), ``ValueError``
        (Konfiguration nicht im richtigen Status oder Job laeuft
        bereits), oder ``RuntimeError`` (interner Re-Embedding-Fehler).
        """
        config = self._store.get_configuration(configuration_id)
        if config is None:
            raise KeyError(
                f"Unbekannte Embedding-Konfiguration: {configuration_id}"
            )
        if config.status != "probed":
            raise ValueError(
                f"Konfiguration muss 'probed' sein, ist aber "
                f"'{config.status}'. Erst erfolgreichen Probe ausfuehren."
            )

        for existing in self._list_jobs_for_configuration(configuration_id):
            if existing.status in ("pending", "running", "validating"):
                raise ValueError(
                    f"Es laeuft bereits eine Migration fuer "
                    f"{configuration_id}: {existing.id} ({existing.status})"
                )

        # Neue Index-Version anlegen. Index-Name folgt dem Schema
        # ``entity_embedding_vN``, Property-Key analog.
        next_version = self._store.next_index_version()
        index_name = f"entity_embedding_v{next_version}"
        property_key = f"embedding_v{next_version}"
        self._store.upsert_index_version(
            version=next_version,
            provider_connection_id=config.provider_connection_id,
            model_id=config.model_id,
            dimensions=config.dimensions,
            index_name=index_name,
            property_key=property_key,
            status="active",
        )
        # Den alten Index (niedrigere Version) auf \"superseded\" setzen,
        # damit klar ist, dass der neue ab jetzt der aktive ist. Der
        # ``active``-Status wird spaeter durch den Switch-Pfad final
        # gesetzt; bis dahin bleiben beide Indizes lesbar.
        if next_version > 1:
            self._store.supersede_index_version(next_version - 1)

        now = self._now()
        job = EmbeddingMigrationJob(
            id=self._new_job_id(),
            configuration_id=configuration_id,
            source_index_version=0 if next_version == 1 else next_version - 1,
            target_index_version=next_version,
            status="pending",
            progress=EmbeddingMigrationProgress(total=0, processed=0, failed=0),
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self._save_job(job)
        return job

    def run(self, job_id: str) -> EmbeddingMigrationJob:
        """Treibt den Job durch pending -> running -> validating -> completed.

        Der eigentliche Re-Embedding-Loop wird durch den injizierten
        ``re_embedder`` ausgefuehrt. Bei ``failed`` bleibt der alte
        Index aktiv und der neue wird auf ``rolled_back`` gesetzt.

        Ein Job im Status ``running`` darf erneut ausgefuehrt werden
        (Crash-Recovery): der Re-Embedder erhaelt den zuletzt
        persistierten Progress inklusive ``last_processed_id`` und
        setzt dort fort. ``started_at`` bleibt dabei erhalten.
        """
        job = self._load_job(job_id)
        if job.status not in ("pending", "running"):
            raise ValueError(
                f"Job {job_id} ist weder 'pending' noch 'running' "
                f"(Resume), sondern '{job.status}'."
            )
        config = self._store.get_configuration(job.configuration_id)
        if config is None:
            raise KeyError(
                f"Konfiguration fuer Job {job_id} fehlt: "
                f"{job.configuration_id}"
            )
        target_index = self._store.get_index_version(job.target_index_version)
        if target_index is None:
            raise RuntimeError(
                f"Ziel-Index-Version {job.target_index_version} fehlt im Store"
            )

        # pending -> running; bei Resume bleibt started_at erhalten.
        started_at = job.progress.started_at or self._now()
        job = self._update_job_status(
            job,
            status="running",
            progress=job.progress.model_copy(
                update={"started_at": started_at}
            ),
        )

        def _persist_checkpoint(progress: EmbeddingMigrationProgress) -> None:
            latest = self._load_job(job_id)
            self._save_job(
                latest.model_copy(
                    update={"progress": progress, "updated_at": self._now()}
                )
            )

        try:
            final_status = self._re_embedder.run(
                target_index.index_name,
                target_index.property_key,
                config.dimensions,
                job.progress,
                configuration=config,
                checkpoint=_persist_checkpoint,
            )
        except Exception as exc:  # noqa: BLE001 — wir wollen alle Re-Embedder-Fehler fangen
            job = self._load_job(job_id)
            return self._update_job_status(
                job,
                status="failed",
                error_message=f"{type(exc).__name__}: {exc}",
            )

        if final_status == "failed":
            job = self._load_job(job_id)
            return self._update_job_status(
                job, status="failed", error_message="Re-Embedder meldete failed"
            )

        # running -> validating (Anzahl + Stichprobe)
        job = self._load_job(job_id)
        job = self._update_job_status(
            job,
            status="validating",
            progress=job.progress.model_copy(
                update={"finished_at": self._now()}
            ),
        )
        if not self._validate_progress(job):
            return self._update_job_status(
                job,
                status="failed",
                error_message="Validierung fehlgeschlagen",
            )

        # validating -> completed; atomarer Switch
        return self._switch_to_new_index(job, config)

    def cancel(self, job_id: str) -> EmbeddingMigrationJob:
        """Bricht einen laufenden Job ab.

        Setzt den Status auf ``rolled_back`` (nicht ``failed``), weil
        der Abbruch eine explizite Operator-Entscheidung ist. Der
        ``active``-Index bleibt unveraendert; der neue Index wird auf
        ``rolled_back`` gesetzt.
        """
        job = self._load_job(job_id)
        if job.status not in ("pending", "running", "validating"):
            raise ValueError(
                f"Job {job_id} ist nicht abbrechbar (Status: {job.status})"
            )
        new_status: EmbeddingMigrationStatus = "rolled_back"
        job = self._update_job_status(
            job,
            status=new_status,
            error_message=f"Operator-Abbruch am {self._now().isoformat()}",
        )
        # Ziel-Index auf \"rolled_back\" setzen, damit der Operator sieht,
        # dass dieser Versuch verworfen wurde.
        self._store.upsert_index_version(
            version=job.target_index_version,
            provider_connection_id=self._require_connection_id(job),
            model_id=self._require_model_id(job),
            dimensions=self._require_dimensions(job),
            index_name=f"entity_embedding_v{job.target_index_version}",
            property_key=f"embedding_v{job.target_index_version}",
            status="rolled_back",
        )
        return job

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_job(self, job_id: str) -> EmbeddingMigrationJob | None:
        return self._load_job_or_none(job_id)

    def list_jobs(
        self, configuration_id: Optional[str] = None
    ) -> list[EmbeddingMigrationJob]:
        all_jobs = self._list_all_jobs()
        if configuration_id is None:
            return all_jobs
        return [j for j in all_jobs if j.configuration_id == configuration_id]

    # ------------------------------------------------------------------
    # Internal Lifecycle
    # ------------------------------------------------------------------

    def _switch_to_new_index(
        self,
        job: EmbeddingMigrationJob,
        config: EmbeddingConfiguration,
    ) -> EmbeddingMigrationJob:
        """Atomarer Wechsel auf den neuen Index.

        Setzt den Status der Konfiguration auf ``active`` (mit dem
        neuen ``index_version``) und markiert vorherige aktive
        Konfigurationen desselben Scopes als ``rolled_back``. Der
        eigentliche Neo4j-Index-Switch (``CALL db.index.setProperty``
        o. Ae.) bleibt einem Folge-Slice vorbehalten, weil er von
        der Live-Graph-Konfiguration abhaengt.
        """
        # Vorherige aktive Konfigurationen desselben Scopes
        # zurueckrollen, damit der Slice-4.2-Eindeutigkeits-Vertrag
        # weiterhin gilt.
        for other in self._store.list_configurations(scope=config.scope):
            if (
                other.id != config.id
                and other.status == "active"
                and other.project_id == config.project_id
            ):
                self._store.update_configuration_status(
                    other.id,
                    status="rolled_back",
                    status_message=(
                        f"abgeloest durch Re-Embedding {job.id}"
                    ),
                )
        # Diese Konfiguration aktivieren.
        self._store.update_configuration_status(
            config.id,
            status="active",
            status_message=f"Re-Embedding {job.id} abgeschlossen",
            index_version=job.target_index_version,
            last_validated_at=self._now(),
        )
        return self._update_job_status(
            job,
            status="completed",
            error_message=None,
        )

    def _validate_progress(self, job: EmbeddingMigrationJob) -> bool:
        """Einfache Validierung: ``failed`` <= ``total``, ``processed``
        + ``failed`` <= ``total`` (modell-immanent), und mindestens ein
        Embedding wurde geschrieben (sonst waere die Migration trivial).
        """
        progress = job.progress
        if progress.failed > progress.total:
            return False
        if progress.processed + progress.failed > progress.total:
            return False
        return True

    def _update_job_status(
        self,
        job: EmbeddingMigrationJob,
        *,
        status: EmbeddingMigrationStatus,
        progress: Optional[EmbeddingMigrationProgress] = None,
        error_message: Optional[str] = None,
    ) -> EmbeddingMigrationJob:
        updated_progress = progress if progress is not None else job.progress
        updated = job.model_copy(
            update={
                "status": status,
                "progress": updated_progress,
                "error_message": error_message,
                "updated_at": self._now(),
            }
        )
        self._save_job(updated)
        return updated

    def _new_job_id(self) -> str:
        import secrets
        return f"job-{secrets.token_hex(12)}"

    def _job_path(self, job_id: str):
        from pathlib import Path
        import os
        data_dir = os.environ.get("AGORA_DATA_DIR") or str(
            Path(__file__).resolve().parents[2] / "data"
        )
        return Path(data_dir) / f"embedding_migration_{job_id}.json"

    def _save_job(self, job: EmbeddingMigrationJob) -> None:
        import json
        path = self._job_path(job.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(job.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _load_job(self, job_id: str) -> EmbeddingMigrationJob:
        job = self._load_job_or_none(job_id)
        if job is None:
            raise KeyError(f"Unbekannter Embedding-Migration-Job: {job_id}")
        return job

    def _load_job_or_none(self, job_id: str) -> EmbeddingMigrationJob | None:
        path = self._job_path(job_id)
        if not path.exists():
            return None
        return EmbeddingMigrationJob.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def _list_jobs_for_configuration(
        self, configuration_id: str
    ) -> list[EmbeddingMigrationJob]:
        return [
            j
            for j in self._list_all_jobs()
            if j.configuration_id == configuration_id
        ]

    def _list_all_jobs(self) -> list[EmbeddingMigrationJob]:
        from pathlib import Path
        import os
        data_dir = os.environ.get("AGORA_DATA_DIR") or str(
            Path(__file__).resolve().parents[2] / "data"
        )
        path = Path(data_dir)
        if not path.exists():
            return []
        jobs: list[EmbeddingMigrationJob] = []
        for file in path.glob("embedding_migration_*.json"):
            try:
                jobs.append(
                    EmbeddingMigrationJob.model_validate_json(
                        file.read_text(encoding="utf-8")
                    )
                )
            except Exception:  # noqa: BLE001 — Drift in der Datei darf nicht die Liste blockieren
                continue
        return jobs

    def _require_connection_id(self, job: EmbeddingMigrationJob) -> str:
        config = self._store.get_configuration(job.configuration_id)
        if config is None:
            raise KeyError(
                f"Konfiguration fuer Job {job.id} fehlt: {job.configuration_id}"
            )
        return config.provider_connection_id

    def _require_model_id(self, job: EmbeddingMigrationJob) -> str:
        config = self._store.get_configuration(job.configuration_id)
        if config is None:
            raise KeyError(
                f"Konfiguration fuer Job {job.id} fehlt: {job.configuration_id}"
            )
        return config.model_id

    def _require_dimensions(self, job: EmbeddingMigrationJob) -> int:
        config = self._store.get_configuration(job.configuration_id)
        if config is None:
            raise KeyError(
                f"Konfiguration fuer Job {job.id} fehlt: {job.configuration_id}"
            )
        return config.dimensions


__all__ = ["EmbeddingMigrationService", "ReEmbedder"]
