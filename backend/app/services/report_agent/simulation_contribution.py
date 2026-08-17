"""Messung des Simulationsbeitrags an den validierten Aussagen (Issue #1304, S3).

Die externe Kritik am Referenzlauf lautete: 24 Runden Simulation, und **keine
einzige** validierte Aussage stützt sich auf eine Agentenaktion. Der Befund war
richtig, aber unbelegbar — es gab keine Zahl, gegen die man ihn hätte prüfen
können, und nach jedem Fix an Sampling oder Interviewkontext wäre unklar
geblieben, ob er gewirkt hat.

Diese Datei liefert die Zahl. Sie ändert nichts am Report, sie zählt nur.

Drei Ebenen, absichtlich getrennt:

``simulation`` — die Aussage stützt sich auf irgendetwas aus der Simulation
    (``agent_quote`` *oder* ``agent_action``). Das schließt Interviews ein, die
    zwar mit den Personas geführt wurden, aber keine Runde der Simulation
    voraussetzen.
``action`` — die Aussage stützt sich auf mindestens eine beobachtete Aktion aus
    Phase 3. Das ist die Zahl, um die es in der Kritik geht.
``necessary`` — *alle* stützenden Belege der Aussage sind Aktionen. Nur hier
    hätte die Aussage ohne die Simulationsrunden gar nicht entstehen können; bei
    den übrigen trägt sie auch ein anderer Beleg.

``action`` ohne ``necessary`` gelesen überschätzt den Beitrag, ``necessary``
allein unterschätzt ihn — deshalb stehen beide im Ergebnis.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

from ...contracts.report_contract import EvidenceSourceKind

#: Quellengattung einer beobachteten Handlung aus Phase 3.
_ACTION_KIND = EvidenceSourceKind.agent_action.value

#: Quellengattungen, die überhaupt aus der Simulation stammen.
_SIMULATION_KINDS = frozenset({
    EvidenceSourceKind.agent_quote.value,
    _ACTION_KIND,
})


def _supporting_evidence_ids(claim: Mapping[str, Any]) -> list[str]:
    """Belege, die den Claim *stützen* — nicht die bloß thematisch verwandten.

    Dieselbe Bedingung wie in ``build_report_v3``: ohne ``supports_claim=True``
    trägt ein Beleg die Aussage nicht, egal wie ähnlich er ist.
    """
    return list(dict.fromkeys(
        str(item.get("evidence_id"))
        for item in claim.get("evidence") or []
        if isinstance(item, dict)
        and item.get("evidence_id")
        and item.get("supports_claim") is True
    ))


def _kinds_for(
    evidence_ids: Iterable[str],
    evidence_index: Mapping[str, Any],
) -> list[str]:
    kinds: list[str] = []
    for evidence_id in evidence_ids:
        record = evidence_index.get(evidence_id)
        if not isinstance(record, Mapping):
            # Unauflösbare Referenz: als unbekannte Gattung führen statt sie
            # stillschweigend als Nicht-Simulation zu zählen. Sie verhindert
            # damit ein "necessary", behauptet aber auch keinen Beitrag.
            kinds.append("")
            continue
        kinds.append(str(record.get("source_kind") or ""))
    return kinds


def compute_simulation_contribution(
    evidence_map: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    """Zählt, wie viele validierte Aussagen die Simulation tatsächlich tragen.

    Gezählt werden nur Aussagen, die als Claim persistiert wurden — Hypothesen
    und Datenlücken sind per Definition unbelegt und würden die Quote
    beschönigen.

    Liefert ein dict in der Feldform von
    ``contracts.report_v3.SimulationContribution``. Bei fehlender oder leerer
    Evidenzkarte sind alle Zähler 0 und alle Anteile ``None`` — eine 0.0 würde
    "kein Beitrag" behaupten, wo nichts gemessen wurde.
    """
    sections = (evidence_map or {}).get("sections") or []
    raw_index = (evidence_map or {}).get("evidence_index") or {}
    evidence_index: Mapping[str, Any] = raw_index if isinstance(raw_index, Mapping) else {}

    validated = 0
    with_simulation = 0
    with_action = 0
    action_necessary = 0

    for section in sections:
        if not isinstance(section, Mapping):
            continue
        for claim in section.get("claims") or []:
            if not isinstance(claim, Mapping):
                continue
            supporting = _supporting_evidence_ids(claim)
            if not supporting:
                # Ohne stützenden Beleg ist die Aussage kein validierter Claim —
                # ``build_report_v3`` überspringt sie ebenfalls.
                continue
            validated += 1
            kinds = _kinds_for(supporting, evidence_index)
            if any(kind in _SIMULATION_KINDS for kind in kinds):
                with_simulation += 1
            if _ACTION_KIND in kinds:
                with_action += 1
                if all(kind == _ACTION_KIND for kind in kinds):
                    action_necessary += 1

    def _share(count: int) -> float | None:
        return round(count / validated, 4) if validated else None

    return {
        "validated_claims": validated,
        "claims_with_simulation_evidence": with_simulation,
        "claims_with_action_evidence": with_action,
        "claims_requiring_action_evidence": action_necessary,
        "simulation_share": _share(with_simulation),
        "action_share": _share(with_action),
        "action_necessary_share": _share(action_necessary),
    }


__all__ = ["compute_simulation_contribution"]
