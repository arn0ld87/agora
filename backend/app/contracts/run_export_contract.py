"""Run-Export-Bericht-Contract (Issue #1680).

Rein internes Artefakt-Vertrag — analog ``GraphBuildCheckpoint``
(``graph_build_checkpoint_contract.py``): lebt unter ``contracts/`` wie
jedes strukturierte Pydantic-Modell dieses Repos, überquert aber nie die
HTTP-API-Grenze als JSON-Response (der Endpoint liefert ``application/zip``)
und wird deshalb bewusst NICHT in ``dump_schemas.CONTRACTS`` aufgenommen.
Serialisiert wird er als ``export-report.json`` innerhalb des Export-ZIPs.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

SkippedExportReason = Literal["not_in_allowlist", "symlink", "outside_run_dir"]


class SkippedExportEntry(BaseModel):
    """Eine Datei im Run-Verzeichnis, die bewusst NICHT exportiert wurde.

    Kein Eintrag darf still entstehen oder fehlen: Jede übersprungene Datei
    wird mit Grund gemeldet, damit der Export nachvollziehbar bleibt und
    versehentlich ins Run-Verzeichnis geratene Dateien (z. B. Secrets)
    sichtbar auffallen, statt unbemerkt zu verschwinden.
    """

    model_config = _STRICT

    path: str = Field(description="Pfad relativ zum Run-Verzeichnis (POSIX-Separatoren)")
    reason: SkippedExportReason = Field(
        description=(
            "not_in_allowlist: Datei matcht kein Export-Muster; "
            "symlink: Symlink wird nie exportiert; "
            "outside_run_dir: realer Speicherort liegt außerhalb des Run-Verzeichnisses"
        )
    )


class RunExportReport(BaseModel):
    """Selektionsbericht des Run-Exports, wandert als ``export-report.json``
    ins ZIP (Issue #1680)."""

    model_config = _STRICT

    run_id: str
    exported: list[str] = Field(
        default_factory=list,
        description="Exportierte Dateien, relativ zum Run-Verzeichnis (POSIX), sortiert",
    )
    skipped: list[SkippedExportEntry] = Field(
        default_factory=list,
        description="Bewusst nicht exportierte Dateien mit Grund, sortiert nach Pfad",
    )
