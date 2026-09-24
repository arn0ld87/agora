"""In-Process-Job-Lease mit Heartbeat und TTL (Issue #1472).

Ersetzt den alten PID+Token-Stempel ohne Ablauf (``app/jobs/identity.py``):
ein Job, dessen Thread haengt oder dessen Prozess nur teilweise stirbt, ohne
dass sich ``worker_token`` aendert, gilt nach ``lease_ttl_s`` ohne frischen
Heartbeat als verwaist -- auch wenn die Prozessidentitaet formal noch passt
(Architekturentscheidung des Maintainers, 2026-09-24).

Rein interner Zustandsvertrag wie ``GraphBuildCheckpoint``
(``graph_build_checkpoint_contract.py``): lebt in den ``RunRegistry``-
Metadaten (``RunDetail.metadata: dict[str, Any]``, bereits generisch) und
ueberquert die HTTP-API-Grenze nur als loses Feld in diesem bereits offenen
Dict -- nie als eigener typisierter Response-Body. Deshalb bewusst NICHT in
``dump_schemas.CONTRACTS``.

Die Metadata-Keys fuer Eigentuemer-PID/-Token sind bewusst identisch mit
``app.jobs.identity.WORKER_PID_KEY``/``WORKER_TOKEN_KEY`` (gleicher Wert,
kein Re-Export -- ``contracts/`` importiert bewusst nicht aus ``jobs/``, um
keine Abhaengigkeit in die falsche Richtung zu ziehen; ein Test in
``tests/contracts/`` haelt beide Konstantenmengen synchron): ein Altbestand-
Manifest, das nur den alten Stempel traegt (ohne ``heartbeat_at``/
``lease_ttl_s``), bleibt fuer ``owns_run()`` unveraendert lesbar -- die
Lease ERGAENZT den Stempel, ersetzt ihn nicht (Rueckwaertskompatibilitaet,
Anforderung 5 des Slices).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

#: Metadata-Schluessel der Lease. PID/Token teilen sich absichtlich den
#: Wert von ``app.jobs.identity.WORKER_PID_KEY``/``WORKER_TOKEN_KEY``
#: (siehe Moduldocstring) -- bewusst als Literal dupliziert statt importiert,
#: damit ``contracts/`` nicht von ``jobs/`` abhaengt.
OWNER_PID_KEY = "worker_pid"
OWNER_TOKEN_KEY = "worker_token"  # noqa: S105 - Manifest-Schluesselname, kein Secret
HEARTBEAT_AT_KEY = "heartbeat_at"
LEASE_TTL_KEY = "lease_ttl_s"

#: Sinnvolle Defaults: das Heartbeat-Intervall liegt deutlich unter der TTL,
#: damit ein einzelner verpasster Heartbeat (Gevent-Scheduling-Jitter,
#: GC-Pause, kurzzeitige Registry-Contention) nicht sofort zum Ablauf fuehrt.
#: Ueberschreibbar per ``Config.AGORA_JOB_LEASE_TTL_SECONDS`` /
#: ``Config.AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS``.
DEFAULT_LEASE_TTL_S = 90
DEFAULT_HEARTBEAT_INTERVAL_S = 20


class JobLease(BaseModel):
    """Lease eines In-Process-Jobs: Eigentuemer-Identitaet + Ablauf.

    ``heartbeat_at`` wird periodisch erneuert, solange der Job-Thread lebt
    (siehe ``app/jobs/__init__.py::_enqueue_thread``). Bleibt der Heartbeat
    laenger als ``lease_ttl_s`` aus, gilt die Lease als abgelaufen --
    unabhaengig davon, ob ``owner_token`` noch mit der aktuellen
    Prozessidentitaet uebereinstimmt.
    """

    model_config = _STRICT

    owner_pid: int
    owner_token: str
    heartbeat_at: AwareDatetime
    lease_ttl_s: int = Field(gt=0, default=DEFAULT_LEASE_TTL_S)

    def is_expired(self, *, now: Optional[datetime] = None) -> bool:
        """True, wenn seit ``heartbeat_at`` mehr als ``lease_ttl_s`` vergangen sind."""
        current = now if now is not None else datetime.now(UTC)
        age_s = (current - self.heartbeat_at).total_seconds()
        return age_s > self.lease_ttl_s

    def to_metadata(self) -> dict[str, Any]:
        """Serialisiert die Lease in die flachen RunRegistry-Metadata-Keys."""
        return {
            OWNER_PID_KEY: self.owner_pid,
            OWNER_TOKEN_KEY: self.owner_token,
            HEARTBEAT_AT_KEY: self.heartbeat_at.isoformat(),
            LEASE_TTL_KEY: self.lease_ttl_s,
        }

    @classmethod
    def from_metadata(cls, metadata: Optional[dict[str, Any]]) -> Optional["JobLease"]:
        """Parst eine Lease aus RunRegistry-Metadata, ``None`` bei Altbestand.

        Ein Manifest aus der Zeit vor diesem Mechanismus (oder eines, dessen
        Stempel-Write fehlschlug, siehe ``enqueue()``) traegt
        ``worker_pid``/``worker_token`` ohne ``heartbeat_at``/``lease_ttl_s``.
        Das ist KEIN Parse-Fehler, sondern der erwartete Rueckwaerts-
        kompatibilitaetsfall: ``None`` heisst hier "keine Lease-Semantik
        anwendbar", nicht "ungueltig" -- Aufrufer behandeln das wie vor
        diesem Slice (reiner Token-Vergleich, kein TTL-Check).
        """
        if not metadata or HEARTBEAT_AT_KEY not in metadata:
            return None
        try:
            return cls(
                owner_pid=metadata[OWNER_PID_KEY],
                owner_token=metadata[OWNER_TOKEN_KEY],
                heartbeat_at=metadata[HEARTBEAT_AT_KEY],
                lease_ttl_s=metadata.get(LEASE_TTL_KEY, DEFAULT_LEASE_TTL_S),
            )
        except Exception:  # noqa: BLE001 - defekte/fremde Lease zaehlt als "keine Lease"
            return None


__all__ = [
    "DEFAULT_HEARTBEAT_INTERVAL_S",
    "DEFAULT_LEASE_TTL_S",
    "HEARTBEAT_AT_KEY",
    "LEASE_TTL_KEY",
    "OWNER_PID_KEY",
    "OWNER_TOKEN_KEY",
    "JobLease",
]
