import json

from app.services.report_agent import Report, ReportManager, ReportOutline, ReportSection, ReportStatus


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
