"""Gegenprobe zu #1240: Wie viel Evidence stammt aus Testfall-Text?

Wertet eine ``evidence_map.json`` nach Dokument-Rolle aus: wie viele
Evidence-Items aus Fall- und Domänenfakten stammen, wie viele aus
Konstruktionsnotizen, Fragestellung oder erwarteten Ergebnissen — und ob ein
Claim trotzdem an nicht stützendem Text hängt. Nach dem Fix muss die letzte
Zahl 0 sein; die Anteile davor messen, wie viel eines Reports der Testfall
selbst beigetragen hätte.

Läufe vor #1240 tragen kein ``document_role``. Für sie nimmt die Auswertung
eine Zuordnung ``Snippet → Rolle`` entgegen (manuell eingeordnet, siehe
``docs/runbooks/scenario-leakage-gegenprobe.md``). Evidence ohne Rolle zählt
als ``unknown`` — geraten wird nicht.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Optional

from ..contracts.document_manifest_contract import NON_SUPPORTING_DOCUMENT_ROLES

UNKNOWN_ROLE = "unknown"


def _role_of(record: Dict[str, Any], labels: Dict[str, str]) -> str:
    role = record.get("document_role")
    if role:
        return str(role)
    snippet = str(record.get("snippet") or "").strip()
    return labels.get(snippet, UNKNOWN_ROLE)


def audit_evidence_roles(
    evidence_map: Dict[str, Any], labels: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Zählt Evidence und stützende Bindungen je Dokument-Rolle."""
    labels = {str(k).strip(): v for k, v in (labels or {}).items()}
    index: Dict[str, Dict[str, Any]] = evidence_map.get("evidence_index") or {}
    roles = {
        evidence_id: _role_of(record, labels)
        for evidence_id, record in index.items()
        if record.get("source_kind") == "seed_corpus" or record.get("document_role")
    }

    supporting_by_role: Counter[str] = Counter()
    claims_only_testcase = 0
    claims_total = 0
    for section in evidence_map.get("sections") or []:
        for claim in section.get("claims") or []:
            claims_total += 1
            supporting_roles = [
                roles.get(str(binding.get("evidence_id")), "not_seed")
                for binding in claim.get("evidence") or []
                if binding.get("supports_claim") is True
            ]
            supporting_by_role.update(supporting_roles)
            if supporting_roles and all(r in NON_SUPPORTING_DOCUMENT_ROLES for r in supporting_roles):
                claims_only_testcase += 1

    seed_by_role = Counter(roles.values())
    seed_total = sum(seed_by_role.values())
    non_supporting = sum(n for r, n in seed_by_role.items() if r in NON_SUPPORTING_DOCUMENT_ROLES)
    return {
        "seed_items": seed_total,
        "seed_items_by_role": dict(sorted(seed_by_role.items())),
        "testcase_share": round(non_supporting / seed_total, 3) if seed_total else 0.0,
        "claims": claims_total,
        "supporting_bindings_by_role": dict(sorted(supporting_by_role.items())),
        "claims_supported_only_by_testcase_text": claims_only_testcase,
    }


__all__ = ["UNKNOWN_ROLE", "audit_evidence_roles"]
