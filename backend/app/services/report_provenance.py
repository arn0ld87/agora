"""Erzeugungsherkunft einer Berichtsfassung: Modell, Anbieter, Job (Issue #1804).

Die Berichts-Metadatei (``meta.json``) trägt weder Modell noch Anbieter. Belegt
ist beides am Berichts-Job der ``RunRegistry`` (``run_type=report_generate``,
``entity_id=<report_id>``): ``metadata.llm_model`` und
``metadata.llm_provider.provider_id`` stammen dort aus der gelockten Route der
Stufe ``report_generation`` (siehe ``ReportGenerationService``), also aus dem,
was tatsächlich gelaufen ist, nicht aus Workspace-Defaults.

Dieses Modul liest nur. Fehlt der Job (Bericht vor Einführung des Registers,
gelöschter Lauf) oder trägt er keine Angabe, bleibt das Feld leer — nichts wird
geraten.
"""

from __future__ import annotations

from typing import Any, Collection, Mapping, Optional

from pydantic import BaseModel, ConfigDict

from .run_registry import RunRegistry

#: ``run_type`` des Berichts-Jobs (siehe ``ReportGenerationService.start_generation``).
REPORT_GENERATE_RUN_TYPE = "report_generate"

#: Obergrenze für den Registerscan; ``list_runs`` kappt sonst bei 200.
_SCAN_LIMIT = 100_000


class ReportGenerationInfo(BaseModel):
    """Was sich über die Erzeugung einer Berichtsfassung belegen lässt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    llm_model: Optional[str] = None
    llm_provider_id: Optional[str] = None
    generation_run_id: str

    def as_report_fields(self) -> dict[str, Optional[str]]:
        """Die additiven ``ReportModel``-Felder."""
        return {
            "llm_model": self.llm_model,
            "llm_provider_id": self.llm_provider_id,
            "generation_run_id": self.generation_run_id,
        }


def _clean(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _info_from_run(run: Mapping[str, Any]) -> Optional[ReportGenerationInfo]:
    run_id = _clean(run.get("run_id"))
    if run_id is None:
        return None
    metadata = run.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    provider = metadata.get("llm_provider")
    provider_id = _clean(provider.get("provider_id")) if isinstance(provider, Mapping) else None
    return ReportGenerationInfo(
        llm_model=_clean(metadata.get("llm_model")),
        llm_provider_id=provider_id,
        generation_run_id=run_id,
    )


def _report_id_of(run: Mapping[str, Any]) -> Optional[str]:
    linked = run.get("linked_ids")
    linked_id = linked.get("report_id") if isinstance(linked, Mapping) else None
    return _clean(run.get("entity_id")) or _clean(linked_id)


def load_generation_info(
    report_ids: Optional[Collection[str]] = None,
) -> dict[str, ReportGenerationInfo]:
    """``report_id`` → Erzeugungsherkunft, aus dem jeweils jüngsten Berichts-Job.

    Ein einziger Registerscan für beliebig viele Berichte (die Liste braucht
    ihn einmal, nicht je Bericht). Mit ``report_ids`` wird auf diese Berichte
    eingeschränkt. Berichte ohne Job fehlen im Ergebnis.
    """
    wanted = set(report_ids) if report_ids is not None else None
    runs = RunRegistry().list_runs(run_type=REPORT_GENERATE_RUN_TYPE, limit=_SCAN_LIMIT)
    found: dict[str, ReportGenerationInfo] = {}
    # ``list_runs`` liefert nach ``updated_at`` absteigend: der erste Treffer je
    # Bericht ist der jüngste Job (z. B. nach einem Resume).
    for run in runs:
        report_id = _report_id_of(run)
        if report_id is None or report_id in found:
            continue
        if wanted is not None and report_id not in wanted:
            continue
        info = _info_from_run(run)
        if info is not None:
            found[report_id] = info
    return found


__all__ = [
    "REPORT_GENERATE_RUN_TYPE",
    "ReportGenerationInfo",
    "load_generation_info",
]
