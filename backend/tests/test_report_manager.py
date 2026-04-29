import json

from app.services.report_agent import ReportAgent, ReportManager
from app.models.report import Report, ReportOutline, ReportSection, ReportStatus


def test_get_progress_returns_none_for_invalid_json(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path))
    report_id = 'report_abcdef123456'
    report_dir = tmp_path / report_id
    report_dir.mkdir(parents=True)
    (report_dir / 'progress.json').write_text('', encoding='utf-8')

    assert ReportManager.get_progress(report_id) is None


def test_get_report_returns_none_for_invalid_meta_json(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path))
    report_id = 'report_abcdef123456'
    report_dir = tmp_path / report_id
    report_dir.mkdir(parents=True)
    (report_dir / 'meta.json').write_text('', encoding='utf-8')

    assert ReportManager.get_report(report_id) is None


def test_update_progress_and_save_report_use_readable_json(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path))
    report_id = 'report_abcdef123456'

    ReportManager.update_progress(
        report_id,
        status='processing',
        progress=42,
        message='Working',
        current_section='Intro',
        completed_sections=['Outline'],
    )
    progress = ReportManager.get_progress(report_id)
    assert progress['progress'] == 42
    assert progress['current_section'] == 'Intro'

    report = Report(
        report_id=report_id,
        simulation_id='sim_abcdef123456',
        graph_id='graph_abcdef123456',
        simulation_requirement='Test requirement',
        status=ReportStatus.COMPLETED,
        outline=ReportOutline(
            title='Demo',
            summary='Summary',
            sections=[ReportSection(title='Intro', content='Body')],
        ),
        markdown_content='# Demo\n\nBody',
        created_at='2026-04-23T00:00:00',
        completed_at='2026-04-23T00:05:00',
    )
    ReportManager.save_report(report)

    with open(tmp_path / report_id / 'meta.json', 'r', encoding='utf-8') as handle:
        raw = json.load(handle)
    assert raw['report_id'] == report_id

    loaded = ReportManager.get_report(report_id)
    assert loaded is not None
    assert loaded.report_id == report_id
    assert loaded.status == ReportStatus.COMPLETED


def test_report_claim_model_keeps_legacy_fields_and_numeric_score():
    agent = ReportAgent.__new__(ReportAgent)
    agent._active_section_evidence = [{
        "type": "graph_fact",
        "source": "report_tool",
        "snippet": "Agent group A repeatedly reposted group B.",
    }]
    agent.evidence_map = {
        "global_evidence": [{
            "type": "graph_metric",
            "source": "simulation_metrics",
            "value": "echo_chamber_index=0.64",
            "snippet": "echo_chamber_index: 0.64",
        }]
    }

    claims = agent._build_claims_for_section("Akteursgruppe A polarisiert die Diskussion.")

    assert claims[0]["claim"] == "Akteursgruppe A polarisiert die Diskussion."
    assert claims[0]["claim_text"] == "Akteursgruppe A polarisiert die Diskussion."
    assert claims[0]["confidence"] == "medium"
    assert claims[0]["confidence_score"] == 0.49
    assert claims[0]["evidence"] == claims[0]["evidence_items"]
    assert {item["type"] for item in claims[0]["evidence"]} == {
        "graph_fact",
        "graph_metric",
        "model_generated_inference",
    }


def test_collect_simulation_evidence_uses_metrics_and_actions(monkeypatch):
    from app.services.simulation_runner import AgentAction, SimulationRunner

    actions = [
        AgentAction(
            round_num=2,
            timestamp="2026-04-29T10:00:00",
            platform="twitter",
            agent_id=1,
            agent_name="Agent A",
            action_type="FOLLOW",
            action_args={"target_agent_id": 2},
        ),
        AgentAction(
            round_num=2,
            timestamp="2026-04-29T10:01:00",
            platform="twitter",
            agent_id=2,
            agent_name="Agent B",
            action_type="FOLLOW",
            action_args={"target_agent_id": 1},
        ),
    ]
    monkeypatch.setattr(SimulationRunner, "get_all_actions", classmethod(lambda cls, simulation_id: actions))
    agent = ReportAgent.__new__(ReportAgent)
    agent.simulation_id = "sim_abcdef123456"

    evidence = agent._collect_simulation_evidence_items()

    assert any(item["type"] == "graph_metric" and item["source"] == "simulation_metrics" for item in evidence)
    assert any(item["type"] == "agent_action" and item["source"] == "simulation_actions" for item in evidence)


def test_evidence_map_round_trip_updates_report_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path))
    report_id = 'report_abcdef123456'
    evidence_map = {
        "schema_version": 1,
        "report_id": report_id,
        "simulation_id": "sim_abcdef123456",
        "global_evidence": [],
        "sections": [{
            "section_index": 1,
            "section_title": "Intro",
            "claims": [{
                "claim_id": "claim_01",
                "claim": "A claim",
                "claim_text": "A claim",
                "confidence": "medium",
                "confidence_score": 0.62,
                "evidence": [{"type": "graph_metric", "source": "simulation_metrics"}],
                "evidence_items": [{"type": "graph_metric", "source": "simulation_metrics"}],
            }],
        }],
    }
    ReportManager.save_evidence_map(report_id, evidence_map)
    report = Report(
        report_id=report_id,
        simulation_id='sim_abcdef123456',
        graph_id='graph_abcdef123456',
        simulation_requirement='Test requirement',
        status=ReportStatus.COMPLETED,
        markdown_content='# Demo',
    )

    ReportManager.save_report(report)
    loaded = ReportManager.get_report(report_id)

    assert ReportManager.get_evidence_map(report_id)["sections"][0]["claims"][0]["confidence_score"] == 0.62
    assert loaded.has_evidence is True
    assert loaded.evidence_sections == 1
