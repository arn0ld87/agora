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

from typing import Any, Dict, Mapping

from ...contracts.report_contract import EvidenceSourceKind, counts_for_confidence

#: Quellengattung einer beobachteten Handlung aus Phase 3.
_ACTION_KIND = EvidenceSourceKind.agent_action.value

#: Quellengattungen, die überhaupt aus der Simulation stammen.
_SIMULATION_KINDS = frozenset({
    EvidenceSourceKind.agent_quote.value,
    _ACTION_KIND,
})


def _supporting_kinds(
    claim: Mapping[str, Any],
    evidence_index: Mapping[str, Any],
) -> list[str]:
    """Belege, die den Claim *stützen* — gefiltert nach ADR-0022 §4.

    Weder das Binding-Item noch der Record im Index dürfen aus manueller
    Graph-Handarbeit stammen (``graph_origin in ("manual", "edited")``).
    """
    kinds: list[str] = []
    seen_eids: set[str] = set()
    for entry in claim.get("evidence") or []:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("supports_claim") is not True:
            continue
        if not counts_for_confidence(entry):
            continue
        eid = str(entry.get("evidence_id") or "")
        if not eid or eid in seen_eids:
            continue
        seen_eids.add(eid)
        record = evidence_index.get(eid)
        if isinstance(record, Mapping):
            if not counts_for_confidence(record):
                continue
            kinds.append(str(record.get("source_kind") or ""))
        else:
            # Unauflösbare Referenz: als unbekannte Gattung führen statt sie
            # stillschweigend als Nicht-Simulation zu zählen.
            kinds.append("")
    return kinds


def _supporting_kinds_for_exported_claim(
    claim_obj: Any,
    evidence_index: Mapping[str, Any],
) -> list[str]:
    """Löst ``evidence_refs`` eines exportierten Claims gegen ``evidence_index`` auf."""
    refs = getattr(claim_obj, "evidence_refs", None)
    if refs is None and isinstance(claim_obj, Mapping):
        refs = claim_obj.get("evidence_refs")
    if not refs:
        return []
    kinds: list[str] = []
    for eid in refs:
        record = evidence_index.get(str(eid))
        if isinstance(record, Mapping):
            if not counts_for_confidence(record):
                continue
            kinds.append(str(record.get("source_kind") or ""))
        else:
            kinds.append("")
    return kinds


def _collect_claim_supporting_kinds(
    sections: Any,
    evidence_index: Mapping[str, Any],
    exported_claims: Any,
) -> list[list[str]]:
    """Sammelt je validiertem Claim die stützenden Quellengattungen."""
    if exported_claims is not None:
        return [
            kinds
            for c in exported_claims
            if (kinds := _supporting_kinds_for_exported_claim(c, evidence_index))
        ]
    collected: list[list[str]] = []
    for section in sections:
        if not isinstance(section, Mapping):
            continue
        for claim in section.get("claims") or []:
            if isinstance(claim, Mapping):
                kinds = _supporting_kinds(claim, evidence_index)
                if kinds:
                    collected.append(kinds)
    return collected


def compute_simulation_contribution(
    evidence_map: Mapping[str, Any] | None,
    *,
    exported_claims: Any = None,
) -> Dict[str, Any]:
    """Zählt, wie viele validierte Aussagen die Simulation tatsächlich tragen.

    Gezählt werden nur Aussagen, die als Claim persistiert wurden — Hypothesen
    und Datenlücken sind per Definition unbelegt und würden die Quote
    beschönigen.

    Wird ``exported_claims`` übergeben (z. B. die finale, deduplizierte
    Claims-Liste in ``ReportManager.build_report_v3``), zählt die Metrik
    exakt über diese Menge statt über die ungefilterten Roh-Abschnitte.

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

    for kinds in _collect_claim_supporting_kinds(sections, evidence_index, exported_claims):
        validated += 1
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
