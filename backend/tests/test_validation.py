from app.utils.validation import (
    validate_graph_id,
    validate_project_id,
    validate_report_id,
    validate_run_id,
    validate_simulation_id,
    validate_task_id,
)


def test_validate_project_id_accepts_expected_format():
    assert validate_project_id("proj_abcdef123456") is True


def test_validate_project_id_rejects_invalid_format():
    assert validate_project_id("project_123") is False


def test_validate_simulation_id_accepts_expected_format():
    assert validate_simulation_id("sim_abcdef123456") is True


def test_validate_report_id_accepts_expected_format():
    assert validate_report_id("report_abcdef123456") is True


def test_validate_run_id_accepts_expected_format():
    assert validate_run_id("run_abcdef123456") is True


def test_validate_graph_id_accepts_uuid_and_compact_uuid():
    assert validate_graph_id("123e4567-e89b-12d3-a456-426614174000") is True
    assert validate_graph_id("123e4567e89b12d3a456426614174000") is True


def test_validate_task_id_accepts_uuid_without_prefix():
    assert validate_task_id("123e4567-e89b-12d3-a456-426614174000") is True


def test_validate_task_id_rejects_prefixed_task_id():
    assert validate_task_id("task_abcdef123456") is False
