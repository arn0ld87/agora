"""
Tests fuer die statischen Provenance-Helper in ReportAgent (Task 12).

_build_source_id_anchor und _attach_provenance sind pure Funktionen —
kein Storage, kein LLM-Client noetig.
"""
from app.services.report_agent import ReportAgent


def test_anchor_from_agent_log_ref_with_entry():
    item = {"agent_log_ref": {"agent_log_id": "42", "entry_id": "p1234"}}
    assert ReportAgent._build_source_id_anchor(item) == "agent-log-42#entry-p1234"


def test_anchor_from_agent_log_ref_only_log_id():
    item = {"agent_log_ref": {"agent_log_id": "42"}}
    assert ReportAgent._build_source_id_anchor(item) == "agent-log-42"


def test_anchor_from_web_raw():
    item = {"raw": {"url": "https://example.com/x", "text": "Originalsatz hier."}}
    anchor = ReportAgent._build_source_id_anchor(item)
    assert anchor is not None
    assert anchor.startswith("web:https://example.com/x#:~:text=")


def test_anchor_returns_none_without_source():
    assert ReportAgent._build_source_id_anchor({}) is None


def test_attach_provenance_is_idempotent():
    item = {
        "quote": "vorhanden",
        "source_id_anchor": "fix:42",
        "raw": {"url": "https://example.com", "text": "anders"},
    }
    out = ReportAgent._attach_provenance(item)
    assert out["quote"] == "vorhanden"
    assert out["source_id_anchor"] == "fix:42"


def test_attach_provenance_fills_from_snippet_and_url():
    item = {"snippet": "Snippet-Text", "raw": {"url": "https://x.de"}}
    out = ReportAgent._attach_provenance(item)
    assert out["quote"] == "Snippet-Text"
    assert out["source_id_anchor"] is not None
    assert out["source_id_anchor"].startswith("web:https://x.de")
