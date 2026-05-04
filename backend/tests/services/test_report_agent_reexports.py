from __future__ import annotations

from importlib import import_module

from app.services.report_agent import (
    Report,
    ReportAgent,
    ReportManager,
    ReportOutline,
    ReportSection,
    ReportStatus,
)


def test_report_agent_public_reexports_exist():
    module = import_module("app.services.report_agent")

    assert module.ReportAgent is ReportAgent
    assert module.ReportManager is ReportManager
    assert module.Report is Report
    assert module.ReportOutline is ReportOutline
    assert module.ReportSection is ReportSection
    assert module.ReportStatus is ReportStatus


def test_report_agent_static_helpers_still_exist():
    assert hasattr(ReportAgent, "_sample_actions_timeseries")
    assert hasattr(ReportAgent, "_build_source_id_anchor")
    assert hasattr(ReportAgent, "_attach_provenance")
    assert hasattr(ReportAgent, "_atomize_claim_chunk")
    assert hasattr(ReportAgent, "_is_claim_candidate")
    assert hasattr(ReportAgent, "_is_atomic_claim")
