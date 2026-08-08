"""InterviewEnvelope — Pydantic-Vertrag für die Interview-Endpunkt-Antwort.

Issue #1005 (Review-Kommentar aus PR #1004, Codex P1): ``_echo_result`` in
``app/api/simulation_interviews.py`` baute die Antwortstruktur bisher als
handgebautes ``dict`` zusammen. Das verstößt gegen die Regel „Dataclasses
oder handgeschriebene Inline-Schemas für API-Verträge" aus ``AGENTS.md``.

Legacy-Form (bewusst, nicht versehentlich): die vier Interview-Endpunkte
(``/interview``, ``/interview/batch``, ``/interview/all``) antworten immer
mit HTTP 200 — auch wenn der interne Interview-Lauf fehlgeschlagen ist.
Der Fehlerzustand wird ausschließlich über ``success: false`` sowie die
additiv gespiegelten Top-Level-Felder ``error``/``code`` transportiert,
nicht über den HTTP-Status. Das weicht vom regulären ``json_success``/
``json_error``-Pfad (``app/utils/api_responses.py``) ab, der 4xx/5xx nutzt.
Dieser Vertrag modelliert die Abweichung explizit, statt sie stillschweigend
zu vereinheitlichen — eine Statuscode-Angleichung wäre eine Verhaltensänderung
für bestehende Consumer und ist hier nicht im Scope (vgl. #1000, #1004).

``data`` trägt immer den vollständigen, unveränderten internen Result-Dict
der jeweiligen ``SimulationRunner``-Methode — dessen innere Form ist nicht
Teil dieses Vertrags (sie variiert je nach IPC- vs. Direct-Pfad, siehe
``_aggregate_batch_error``), deshalb bleibt ``data`` bewusst ein offenes
``dict[str, Any]``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class InterviewEnvelope(BaseModel):
    """Antwort-Envelope der Interview-Endpunkte (Legacy-Form, HTTP 200 immer).

    ``error``/``code`` sind nur bei ``success=False`` gesetzt und auch dann nur,
    wenn eine Fehlerursache tatsächlich ermittelt werden konnte (additiv
    gespiegelt aus ``data`` bzw. aus der Direct-Pfad-Aggregation) — analog zum
    bisherigen ``if error: envelope["error"] = error``-Verhalten. Bei
    ``model_dump(exclude_none=True)`` verschwinden nicht gesetzte Felder aus
    der Antwort, statt als ``null`` zu erscheinen.
    """

    model_config = ConfigDict(extra="forbid")

    success: bool
    data: dict[str, Any]
    error: str | None = None
    code: str | None = None


__all__ = ["InterviewEnvelope"]
