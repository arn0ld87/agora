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
- e2e_stub_chat_response: deterministischer String-Return für chat()-Aufrufe
  (ReACT-Loop in generate_section_react — min_tool_calls=1 wird durch
  Zählen der assistant-Nachrichten in der Message-History erfüllt).
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import re
from typing import Any

_stub_logger = logging.getLogger("agora.llm_e2e_stub")

# Snapshot-Pfad — Single Source of Truth für Pflichtabschnitte.
# Der prod-Container kopiert backend/app (ohne backend/tests), daher wird
# der Pfad zu backend/tests/eval/snapshots/ dort nicht existieren.
# _required_sections() fällt in diesem Fall auf den eingebetteten
# Fallback zurück, anstatt ImportError zu werfen (CI-Root-Cause M11.4b-Followup-1).
_SNAPSHOT_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "tests"
    / "eval"
    / "snapshots"
    / "output-contract-required-sections.txt"
)

# Eingebetteter Fallback — gespiegelt aus backend/tests/eval/snapshots/output-contract-required-sections.txt.
# Muss mit der Snapshot-Datei synchron bleiben (M11.8b).
# Wird aktiviert wenn die Snapshot-Datei im Container nicht vorhanden ist
# (prod-Image kopiert backend/tests nicht).
_FALLBACK_REQUIRED_SECTIONS: list[str] = [
    "Executive Summary",
    "Segment-Tabelle",
    "Persona-Tabelle",
    "Multiplikator-Auswertung",
    "Top 10 Reibungspunkte",
    "Top 10 Vertrauenssignale",
    "Top 10 Änderungen",
    "Projektwirkung",
    "Positionierung",
    "Content-Ideen",
    "Datenlücken",
    "Handlungsempfehlung",
]


# Einmalig beim Import geladen (Pure Python, kein I/O danach)
def _required_sections() -> list[str]:
    """Liest die Pflichtabschnittsnamen aus dem Snapshot.

    Primär: Snapshot-Datei backend/tests/eval/snapshots/output-contract-required-sections.txt.
    Fallback: eingebettete Liste _FALLBACK_REQUIRED_SECTIONS — aktiv wenn die Datei
    im Container nicht vorhanden ist (prod-Image enthält backend/tests nicht).
    Warnt via logging wenn Fallback aktiv ist, damit CI-Logs die Ursache zeigen.
    """
    if _SNAPSHOT_PATH.exists():
        lines = _SNAPSHOT_PATH.read_text(encoding="utf-8").splitlines()
        sections = [line.strip() for line in lines if line.strip()]
        _stub_logger.info(
            "llm_e2e_stub: Snapshot geladen von %s (%d Abschnitte)",
            _SNAPSHOT_PATH,
            len(sections),
        )
        return sections

    _stub_logger.warning(
        "llm_e2e_stub: Snapshot-Datei fehlt (%s) — verwende eingebetteten Fallback "
        "(%d Abschnitte). Prod-Image kopiert backend/tests nicht; Fallback ist "
        "im E2E-Stub-Modus valide.",
        _SNAPSHOT_PATH,
        len(_FALLBACK_REQUIRED_SECTIONS),
    )
    return list(_FALLBACK_REQUIRED_SECTIONS)


# Geladen einmalig beim Modulimport
_REQUIRED_SECTIONS: list[str] = _required_sections()

_stub_logger.info(
    "llm_e2e_stub: Modul importiert. AGORA_E2E_LLM_MODE=%s, %d Pflichtabschnitte geladen. "
    "Embedding-Service stubt separat via EmbeddingService._stub_vector() "
    "(app.storage.embedding_service — kein Netzwerkaufruf im Stub-Modus).",
    os.environ.get("AGORA_E2E_LLM_MODE", "<nicht gesetzt>"),
    len(_REQUIRED_SECTIONS),
)

# Deterministischer Zeitstempel für alle Stub-Antworten
_STUB_TIMESTAMP = "2026-01-01T00:00:00+00:00"


def _is_plan_response_schema(schema: dict[str, Any]) -> bool:
    """Erkennt ob schema ein PlanResponse-JSON-Schema ist.

    Heuristiken:
    1. title enthält "PlanResponse" oder "plan_response".
    2. properties enthält "sections" und mindestens eines von "title"/"summary".
    """
    if not isinstance(schema, dict):
        return False
    title = str(schema.get("title", "")).lower()
    if "planresponse" in title or "plan_response" in title:
        return True
    props = set(schema.get("properties", {}).keys())
    if "sections" in props and ("title" in props or "summary" in props):
        return True
    return False


def _stub_plan_response() -> dict[str, Any]:
    """Erzeugt ein deterministisches PlanResponse-Objekt mit allen 11 Pflichtabschnitten.

    Liefert exakt die 11 Section-Titel aus dem Snapshot — damit der Report-Agent
    einen vollständigen Outline produziert, der in der UI assertiert werden kann.
    """
    return {
        "title": "E2E-Smoke-Stub-Report — Deterministische Scenario-Evaluierung",
        "summary": "Stub-Zusammenfassung für E2E-CI-Smokes. Keine echten LLM-Daten.",
        "sections": [
            {"title": section, "description": f"Stub-Beschreibung für {section}."}
            for section in _REQUIRED_SECTIONS
        ],
    }


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
        "schema_version": 4,
        "report_id": "e2e-stub-report-001",
        "generated_at": _STUB_TIMESTAMP,
        "evidence_index": {
            "ev_00000000000000000000000000000000": {
                "evidence_id": "ev_00000000000000000000000000000000",
                "producer_key": "e2e-stub:evidence-01",
                "type": "graph_fact",
                "source": "e2e_stub",
                "snippet": "Deterministische Evidence fuer E2E-Smoke-Tests.",
                "source_kind": "graph_relation",
            }
        },
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
                "evidence_refs": ["ev_00000000000000000000000000000000"],
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
                "evidence_refs": ["ev_00000000000000000000000000000000"],
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
_STUB_TOOL_RETURNS: dict[str, dict[str, Any]] = {
    "insight_forge": {
        "insights": [
            "Stub-Insight: Zielgruppe reagiert positiv auf transparente Kommunikation."
        ],
        "confidence": "medium",
        "evidence_refs": ["ev-stub-01"],
    },
    "panorama_search": {
        "results": [
            {
                "id": "ev-stub-01",
                "title": "Stub-Dokument",
                "snippet": "Stub-Inhalt für E2E-Tests.",
                "relevance": 0.8,
            }
        ]
    },
    "quick_search": {
        "results": [
            {
                "id": "ev-stub-01",
                "title": "Stub-Dokument",
                "snippet": "Stub-Inhalt.",
                "relevance": 0.7,
            }
        ]
    },
    "interview_agents": {
        "interviews": [
            {
                "agent_id": "stub-agent-01",
                "response": "Stub-Interview-Antwort für E2E-Tests.",
            }
        ]
    },
}

_STUB_TOOL_DEFAULT: dict[str, Any] = {"ok": True, "stub": True}


def _detect_react_tool_call(messages: list[dict[str, Any]]) -> str | None:
    """Erkennt Tool-Call in Messages und gibt Tool-Namen zurück, oder None."""
    for msg in messages:
        content = str(msg.get("content", ""))
        # ReACT-Pattern: <tool_call>{...}</tool_call> — robust gegen nested JSON
        match = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", content, re.DOTALL)
        if match:
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                name = payload.get("name")
                if name:
                    return str(name)
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


def _count_assistant_messages(messages: list[dict[str, Any]]) -> int:
    """Zählt die assistant-Nachrichten in der Message-History.

    Wird in e2e_stub_chat_response genutzt, um den ReACT-Loop-Fortschritt
    zu erkennen: nach ≥ 3 assistant-Nachrichten (= 3 Tool-Calls) wird
    "Final Answer:" zurückgegeben, sonst ein Tool-Call-String.
    """
    return sum(1 for m in messages if m.get("role") == "assistant")


# Deterministischer Tool-Call-String für den ReACT-Loop.
# Die vier registrierten Tools rotieren nach Runde (0-basiert):
# Runde 0 → panorama_search, Runde 1 → quick_search, Runde 2 → insight_forge.
_STUB_TOOL_CALL_SEQUENCE: list[str] = [
    '<tool_call>{"name": "panorama_search", "parameters": {"query": "E2E-Smoke-Stub-Query"}}</tool_call>',
    '<tool_call>{"name": "quick_search", "parameters": {"query": "E2E-Smoke-Stub-Query-2"}}</tool_call>',
    '<tool_call>{"name": "insight_forge", "parameters": {"query": "E2E-Smoke-Stub-Insight"}}</tool_call>',
]

# Deterministischer Final-Answer-Text — enthält den Section-Titel als Platzhalter.
# Kein Persona-Zitat: Cite-Validation schlägt im Stub-Modus nicht an,
# weil persona_ids_for_validation leer ist (kein echter Graph in CI).
_STUB_FINAL_ANSWER_TEMPLATE = (
    "Final Answer: Stub-Abschnitt für E2E-Smoke-Tests. "
    "Dieser Text wurde deterministisch durch den llm_e2e_stub erzeugt. "
    "Keine echten LLM-Daten in diesem Lauf."
)


def e2e_stub_chat_response(
    *,
    messages: list[dict[str, Any]],
    **kwargs: Any,
) -> str:
    """Deterministischer String-Return für LLMClient.chat() im Stub-Modus.

    Entscheidungslogik für den ReACT-Loop in generate_section_react:
    - Die erste ≥ min_tool_calls (= 1) Iterationen geben Tool-Call-Strings zurück.
    - Ab der zweiten Iteration wird "Final Answer:" zurückgegeben.

    Die Entscheidung basiert auf dem Zählen vorhandener assistant-Nachrichten
    in der Message-History — kein globaler Zustand nötig.

    Kein I/O, kein Sleep, kein Random.
    """
    assistant_count = _count_assistant_messages(messages)
    # min_tool_calls im Workflow = 1 — nach 1 Tool-Call kommt Final Answer
    if assistant_count < 1:
        idx = assistant_count % len(_STUB_TOOL_CALL_SEQUENCE)
        return _STUB_TOOL_CALL_SEQUENCE[idx]
    return _STUB_FINAL_ANSWER_TEMPLATE


def e2e_stub_chat_with_tools_response(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Deterministischer Return für LLMClient.chat_with_tools() im Stub-Modus.

    Entscheidungslogik analog zu e2e_stub_chat_response:
    - Weniger als 1 assistant-Nachricht → gibt einen Tool-Call zurück.
    - Ab 1 assistant-Nachricht → Final-Answer-Content, tool_calls=[].

    Der Tool-Name wird aus der tools-Liste genommen (erster Eintrag), falls vorhanden.
    Fallback: "panorama_search".
    """
    from app.utils.llm_client import ToolCallResponse, ToolCallItem  # noqa: PLC0415

    assistant_count = _count_assistant_messages(messages)

    if assistant_count < 1:
        # Tool-Namen aus übergebener tools-Liste holen
        tool_name = "panorama_search"
        if tools:
            first = tools[0]
            func = first.get("function", {})
            tool_name = func.get("name", "panorama_search")
        return ToolCallResponse(
            content="",
            tool_calls=[
                ToolCallItem(
                    id=f"stub-call-{assistant_count:02d}",
                    name=tool_name,
                    arguments={"query": f"E2E-Smoke-Stub-Query-{assistant_count}"},
                )
            ],
            finish_reason="tool_calls",
            raw_response=None,
        )

    return ToolCallResponse(
        content=_STUB_FINAL_ANSWER_TEMPLATE,
        tool_calls=[],
        finish_reason="stop",
        raw_response=None,
    )


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
        return _STUB_TOOL_RETURNS.get(tool_name, _STUB_TOOL_DEFAULT)

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

    # 2b. PlanResponse-Schema?
    if resolved_schema is not None and _is_plan_response_schema(resolved_schema):
        return _stub_plan_response()

    # 3. Generischer Fallback
    return {"ok": True, "stub": True}
