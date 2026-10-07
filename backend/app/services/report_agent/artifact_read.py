"""Strenges Lesen vertragsgebundener Berichts-Artefakte (Issue #1804, Etappe 5).

``load_evidence_density`` und ``load_stance_analysis`` dienen dem Resume im
Report-Workflow und melden jede unbrauchbare Datei als ``None``. Ein
Lese-Endpunkt braucht die Unterscheidung, die dort fehlt: *keine Datei*
(Altbericht, HTTP 404) gegen *Datei vorhanden, aber vertragswidrig*
(sichtbare Omission statt leerer Zahlen).

Speicher- und Berechtigungsfehler (``OSError``) werden bewusst nicht
abgefangen: sie sind kein Vertragsbruch der Daten und dürfen nicht wie einer
aussehen.
"""

from __future__ import annotations

import json
import os
from pydantic import BaseModel, ValidationError

_MAX_ERRORS = 5


class ArtifactContractViolation(Exception):
    """Die Artefaktdatei liegt vor, erfüllt den Vertrag aber nicht."""

    def __init__(self, path: str, validation_errors: list[str]) -> None:
        super().__init__(f"Artefakt nicht vertragskonform: {path}")
        self.path = path
        self.validation_errors = validation_errors[:_MAX_ERRORS]


def read_contract_artifact[M: BaseModel](path: str, model: type[M]) -> M | None:
    """Liest ``path`` und validiert gegen ``model``.

    Rückgabe ``None``, wenn die Datei nicht existiert. Beschädigtes JSON und
    Schemaverstöße lösen ``ArtifactContractViolation`` aus.
    """
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        try:
            raw = json.load(handle)
        except ValueError as exc:
            raise ArtifactContractViolation(path, [f"<json>: {exc}"]) from exc
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        errors = [
            f"{'.'.join(str(part) for part in err.get('loc', ()))}: {err.get('msg', '')}"
            for err in exc.errors(include_url=False)[:_MAX_ERRORS]
        ]
        raise ArtifactContractViolation(path, errors) from exc


__all__ = ["ArtifactContractViolation", "read_contract_artifact"]
