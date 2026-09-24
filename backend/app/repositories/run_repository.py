"""Port für Run-Registry-Persistenz (#1579).

Beschreibt ausschließlich die **Ablage** von Run-Manifesten — Lesen,
Schreiben, Auflisten.  Alle höheren Belange (Singleton, Lock, canonical_status,
Events, Aggregation, sync_task) bleiben in ``RunRegistry``.

Semantik (nicht verhandelbar, damit ein zweiter Adapter sie nicht anders
auslegt):

``get`` gibt ``None`` zurück, wenn der Run nicht existiert.  Ein fehlender Run
ist ein erwarteter Fall, kein Fehler.

``save`` schreibt den Record atomar und gibt ihn zurück.  Atomizität ist
Pflicht: der File-Adapter nutzt ``write_json_atomic``; ein Postgres-Adapter
nutzt Transaktionen.

``list_all`` gibt alle Records zurück, sortiert nach ``updated_at`` absteigend.
Die Sortierung ist Teil der Zusage, nicht ein Nebenprodukt der Ablage.  Vor
der Sortierung wird auf ``limit`` abgeschnitten — wer alle Records will, übergibt
ein hohes Limit.  Korrupte/nicht lesbare Einträge werden übersprungen (wie
``list_runs`` in RunRegistry bisher).

Der Import des Adapters steht bewusst in ``get_run_repository``, damit ein
Modul, das nur den Port braucht, die Ablage nicht mitlädt.
``AGORA_RUN_BACKEND`` wählt zwischen Dateiadapter (Default ``file``) und
PostgreSQL-Adapter (#1587).
"""
from __future__ import annotations

import os
from typing import Optional, Protocol, runtime_checkable

from ..config import RUN_BACKENDS, Config
from ..contracts.run_record_contract import RunRecord


class RunBackendUnavailable(RuntimeError):
    """``AGORA_RUN_BACKEND`` trägt einen Wert, den keine Ablage bedient.

    ``Config.validate()`` lehnt ihn beim Start ab; dieser Fehler fängt den
    Weg ohne Validierung ab (Test, Skript), statt still auf die Datei
    zurückzufallen.
    """


@runtime_checkable
class RunRepository(Protocol):
    """Lesen und Schreiben von Run-Manifesten, unabhängig von der Ablage."""

    def get(self, run_id: str) -> Optional[RunRecord]:
        """Record oder ``None``, wenn der Run nicht existiert.

        Wirft nicht bei fehlendem Run — ein fehlender Run ist ein erwarteter
        Fall, kein Fehler.  Ein korruptes JSON gibt ebenfalls ``None`` zurück;
        der Aufrufer kann das über ein vorheriges ``save`` ausschließen.
        """
        ...

    def save(self, record: RunRecord) -> RunRecord:
        """Schreibt den Record atomar und gibt ihn zurück.

        Erstellt das Ablageverzeichnis bei Bedarf.  Der Rückgabewert ist
        identisch mit dem Eingabewert; er erlaubt eine Chaining-Schreibweise.
        """
        ...

    def list_all(self, *, limit: int = 100_000) -> list[RunRecord]:
        """Alle Records, neueste zuerst (nach ``updated_at`` absteigend).

        Korrupte oder nicht lesbare Dateien werden übersprungen; die Liste
        bricht deshalb nie ab.  Das Limit schneidet nach der Sortierung ab,
        sodass ``limit=1`` immer den neuesten Record liefert.
        """
        ...


def get_run_repository(registry_dir: str | None = None) -> RunRepository:
    """Die einzige Stelle, an der ein Consumer an ein Run-Repository kommt.

    ``registry_dir`` ist der Ablageort für den File-Adapter.  Ohne Angabe
    fällt er auf ``<UPLOAD_FOLDER>/run_registry`` zurück — denselben Pfad,
    den ``RunRegistry.REGISTRY_DIR`` bildet.

    ``AGORA_RUN_BACKEND=postgres`` liefert den PostgreSQL-Adapter;
    ``registry_dir`` bleibt dann unbenutzt.
    """
    backend = Config.RUN_BACKEND
    if backend not in RUN_BACKENDS:
        raise RunBackendUnavailable(
            f"AGORA_RUN_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(RUN_BACKENDS))})"
        )
    if backend == "postgres":
        from ..infrastructure.postgres.repositories import PostgresRunRepository

        return PostgresRunRepository()

    if registry_dir is None:
        registry_dir = os.path.join(Config.UPLOAD_FOLDER, "run_registry")
    from ..services.file_run_store import FileRunRepository

    return FileRunRepository(registry_dir)
