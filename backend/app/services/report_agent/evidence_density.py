"""Belegdichte der Claims eines Berichts (Issue #1779, Schritt 2.1).

Zählt aus der fertigen Evidence-Map, wie dicht die Claims belegt sind, und
legt das Ergebnis als ``evidence_density.json`` im Berichtsverzeichnis ab.
Die Berechnung ist rein: kein Modellaufruf, kein I/O. Sie ändert weder
Confidence noch Status — sie macht nur messbar, was sonst ein Handskript
nachzählen müsste.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from ...contracts.evidence_density_contract import EvidenceDensity
from ...utils.logger import get_logger
from .artifact_read import read_contract_artifact
from .claim_qualification import (  # noqa: F401
    _ACTION_TYPE,
    _CAP_TOLERANCE,
    _SINGLE_SOURCE_CAP,
    _is_at_single_source_cap,
    _ratio,
    compute_evidence_density,
    supporting_entries_for_claim as _supporting_entries,
)
from .storage import write_json_atomic

logger = get_logger("agora.report_agent.evidence_density")

#: Dateiname der Zählung im Berichtsverzeichnis.
EVIDENCE_DENSITY_FILENAME = "evidence_density.json"


def load_evidence_density(report_folder: str) -> Optional[EvidenceDensity]:
    """Liest eine gespeicherte Zählung; ``None``, wenn keine gültige vorliegt."""
    path = os.path.join(report_folder, EVIDENCE_DENSITY_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return EvidenceDensity.model_validate(json.load(handle))
    except (OSError, ValueError) as exc:
        logger.warning("Gespeicherte Belegdichte nicht lesbar (%s): %r", path, exc)
        return None


def read_evidence_density(report_folder: str) -> Optional[EvidenceDensity]:
    """Strenges Lesen für den Lese-Endpunkt (Issue #1804).

    ``None``, wenn keine Datei vorliegt; ``ArtifactContractViolation``, wenn sie
    den Vertrag verletzt. ``load_evidence_density`` bleibt der tolerante
    Resume-Pfad.
    """
    return read_contract_artifact(
        os.path.join(report_folder, EVIDENCE_DENSITY_FILENAME), EvidenceDensity
    )


def save_evidence_density(report_folder: str, density: EvidenceDensity) -> str:
    """Schreibt die Zählung atomar als ``evidence_density.json`` und liefert den Pfad."""
    path = os.path.join(report_folder, EVIDENCE_DENSITY_FILENAME)
    write_json_atomic(path, density.model_dump(mode="json"))
    return path


__all__ = [
    "EVIDENCE_DENSITY_FILENAME",
    "compute_evidence_density",
    "load_evidence_density",
    "read_evidence_density",
    "save_evidence_density",
]
