"""
E2E-Stub für deterministischen LLM-Betrieb in CI-Smokes.

Aktivierung ausschließlich via Umgebungsvariable:
    AGORA_E2E_LLM_MODE=stub

Ohne diese Variable ist dieses Modul NICHT importiert — Prod-Verhalten
bleibt vollständig unverändert.

Liefert:
- Valides ReportV3-Objekt, wenn schema auf ReportV3-Struktur hindeutet.
- Deterministischen Tool-Return für die vier registrierten Report-Agent-Tools.
- Generisches {"ok": true, "stub": true} als Fallback.
"""
from __future__ import annotations

import pathlib
from typing import Any

# Snapshot-Pfad — Single Source of Truth für Pflichtabschnitte
_SNAPSHOT_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "tests"
    / "eval"
    / "snapshots"
    / "output-contract-required-sections.txt"
)

# Einmalig beim Import geladen (Pure Python, kein I/O danach)
def _eleven_required_sections() -> list[str]:
    """Liest die 11 Pflichtabschnittsnamen aus dem Snapshot.

    Die Datei ist Single Source of Truth (M11.8b).
    ImportError mit erklärender Message, wenn Datei fehlt.
    """
    if not _SNAPSHOT_PATH.exists():
        raise ImportError(
            f"Pflichtabschnitt-Snapshot fehlt: {_SNAPSHOT_PATH}\n"
            "Bitte sicherstellen, dass M11.8b (Snapshot-Generierung) ausgeführt wurde."
        )
    lines = _SNAPSHOT_PATH.read_text(encoding="utf-8").splitlines()
    sections = [line.strip() for line in lines if line.strip()]
    return sections


# Geladen einmalig beim Modulimport
_REQUIRED_SECTIONS: list[str] = _eleven_required_sections()

# Deterministischer Zeitstempel für alle Stub-Antworten
_STUB_TIMESTAMP = "2026-01-01T00:00:00+00:00"


def _is_report_v3_schema(schema: dict[str, Any]) -> bool:
    """Erkennt ob schema ein ReportV3-JSON-Schema ist.

    Heuristiken (in Reihenfolge):
    1. $id oder title enthalten "ReportV3" oder "report_v3".
    2. properties enthält mindestens 3 der ReportV3-Kernfelder.
    3. required enthält "schema_version".
    """
    if not isinstance(schema, dict):
        return False

    # 1. Namens-Hinweise
    title = str(schema.get("title", "")).lower()
    schema_id = str(schema.get("$id", "")).lower()
    if "reportv3" in title or "report_v3" in title:
        return True
    if "reportv3" in schema_id or "report_v3" in schema_id:
        return True

    # 2. Properties-Überlappung
    _REPORT_V3_CORE_FIELDS = {
        "personas", "segments", "claims", "multipliers",
        "friction_points", "trust_signals", "change_recommendations",
        "project_impacts", "positioning_variants", "content_ideas", "data_gaps",
    }
    props = set(schema.get("properties", {}).keys())
    if len(props & _REPORT_V3_CORE_FIELDS) >= 3:
        return True

    # 3. required enthält schema_version
    required = schema.get("required", [])
    if "schema_version" in required:
        return True

    return False


def _stub_report_v3() -> dict[str, Any]:
    """Erzeugt ein deterministisches, valides ReportV3-Objekt.

    Alle 11 Pflichtfelder sind befüllt (leere Listen sind Pydantic-konform).
    Verwende minimale, aber valide Objekte je Feldtyp.
    """
    return {
        "schema_version": 3,
        "report_id": "e2e-stub-report-001",
        "generated_at": _STUB_TIMESTAMP,
        "personas": [
            {
                "id": "p-stub-01",
                "voice_register": "neutral-de",
                "alter_range": "30-45",
                "beruf": "Angestellte/r",
                "region": "DACH",
                "bildungsgrad": None,
                "haushaltseinkommen": None,
                "needs": ["Sicherheit", "Verlässlichkeit"],
                "values": ["Qualität", "Transparenz"],
                "evidence_refs": ["ev-stub-01"],
            }
        ],
        "segments": [
            {
                "id": "seg-stub-01",
                "name": "DACH-Kernsegment",
                "beschreibung": "Stub-Segment für E2E-Smoke-Tests",
                "persona_ids": ["p-stub-01"],
                "kontaktwahrscheinlichkeit_prozent": None,
            }
        ],
        "claims": [
            {
                "id": "claim-stub-01",
                "statement": "Das Produkt wird von der Zielgruppe als vertrauenswürdig eingeschätzt.",
                "evidence_refs": ["ev-stub-01"],
                "confidence": "medium",
                "persona_ids": ["p-stub-01"],
                "aggregation_basis": "aggregat",
            }
        ],
        "multipliers": [
            {
                "id": "mult-stub-01",
                "name": "Stub-Multiplikator",
                "kategorie": "awareness",
                "reichweite_score": 5,
                "evidence_refs": [],
            }
        ],
        "friction_points": [
            {
                "id": "fp-stub-01",
                "beschreibung": "Stub-Reibungspunkt für E2E-Tests",
                "severity": "low",
                "affected_persona_ids": [],
                "evidence_refs": [],
            }
        ],
        "trust_signals": [
            {
                "id": "ts-stub-01",
                "beschreibung": "Stub-Vertrauenssignal",
                "signal_type": "authority",
                "evidence_refs": [],
            }
        ],
        "change_recommendations": [
            {
                "id": "cr-stub-01",
                "titel": "Stub-Empfehlung",
                "beschreibung": "Stub-Beschreibung für E2E-Tests",
                "priority": "medium",
                "aufwand": "M",
                "evidence_refs": [],
            }
        ],
        "project_impacts": [
            {
                "id": "pi-stub-01",
                "beschreibung": "Stub-Projektwirkung",
                "affected_segments": ["seg-stub-01"],
                "confidence": "medium",
                "evidence_refs": [],
            }
        ],
        "positioning_variants": [
            {
                "id": "pv-stub-01",
                "titel": "Stub-Positionierung",
                "claim_text": "Stub-Positionierungstext",
                "ziel_persona_ids": ["p-stub-01"],
                "evidence_refs": [],
            }
        ],
        "content_ideas": [
            {
                "id": "ci-stub-01",
                "titel": "Stub-Content-Idee",
                "format": "blog",
                "persona_ids": ["p-stub-01"],
                "evidence_refs": [],
            }
        ],
        "data_gaps": [
            {
                "id": "dg-stub-01",
                "beschreibung": "Stub-Datenlücke",
                "severity": "low",
                "suggested_fixes": [],
            }
        ],
    }


# Deterministischer Tool-Return für ReACT-Schleife.
# Nur die vier Tools, die report_agent/tools.py tatsächlich registriert:
# insight_forge, panorama_search, quick_search, interview_agents.
_STUB_TOOL_RETURNS: dict[str, str] = {
    "insight_forge": (
        '{"insights": ["Stub-Insight: Zielgruppe reagiert positiv auf transparente Kommunikation."], '
        '"confidence": "medium", "evidence_refs": ["ev-stub-01"]}'
    ),
    "panorama_search": (
        '{"results": [{"id": "ev-stub-01", "title": "Stub-Dokument", '
        '"snippet": "Stub-Inhalt für E2E-Tests.", "relevance": 0.8}]}'
    ),
    "quick_search": (
        '{"results": [{"id": "ev-stub-01", "title": "Stub-Dokument", '
        '"snippet": "Stub-Inhalt.", "relevance": 0.7}]}'
    ),
    "interview_agents": (
        '{"interviews": [{"agent_id": "stub-agent-01", "response": '
        '"Stub-Interview-Antwort für E2E-Tests."}]}'
    ),
}

_STUB_TOOL_DEFAULT = '{"ok": true, "stub": true}'


def _detect_react_tool_call(messages: list[dict[str, Any]]) -> str | None:
    """Erkennt Tool-Call in Messages und gibt Tool-Namen zurück, oder None."""
    for msg in messages:
        content = str(msg.get("content", ""))
        # ReACT-Pattern: <tool_call>{"name": "tool_name", ...}</tool_call>
        import re
        match = re.search(r'<tool_call>\s*\{[^}]*"name"\s*:\s*"([^"]+)"', content)
        if match:
            return match.group(1)
        # Auch OpenAI-Tool-Call-Format
        tool_calls = msg.get("tool_calls")
        if tool_calls and isinstance(tool_calls, list):
            first = tool_calls[0]
            if isinstance(first, dict):
                func = first.get("function", {})
                name = func.get("name") if isinstance(func, dict) else None
                if name:
                    return str(name)
    return None


def e2e_stub_response(
    *,
    schema: dict[str, Any] | None,
    messages: list[dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    """Deterministischer Stub-Return für E2E-CI-Smokes.

    Entscheidungslogik:
    1. ReACT-Tool-Call erkannt → deterministischer Tool-Return (dict).
    2. schema ist ReportV3-konform → valides ReportV3-Objekt.
    3. Sonst → generisches {"ok": true, "stub": true}.

    Kein I/O außer einmaligem Snapshot-Read beim Import.
    Kein Sleep, kein Random.
    """
    # 1. ReACT-Tool-Call?
    tool_name = _detect_react_tool_call(messages)
    if tool_name is not None:
        import json
        raw = _STUB_TOOL_RETURNS.get(tool_name, _STUB_TOOL_DEFAULT)
        return dict(json.loads(raw))  # type: ignore[arg-type]

    # 2. ReportV3-Schema?
    resolved_schema: dict[str, Any] | None = None
    if schema is not None:
        if isinstance(schema, dict):
            resolved_schema = schema
        elif isinstance(schema, type):
            try:
                resolved_schema = schema.model_json_schema()  # type: ignore[attr-defined]
            except AttributeError:
                resolved_schema = None

    if resolved_schema is not None and _is_report_v3_schema(resolved_schema):
        return _stub_report_v3()

    # 3. Generischer Fallback
    return {"ok": True, "stub": True}
