"""Regression #1898: ``./log`` liegt vor dem OASIS-Import der xdist-Worker bereit."""

from __future__ import annotations

from pathlib import Path

from tests._oasis_log_dir import OASIS_LOG_DIR_NAME, ensure_oasis_log_dir


def test_creates_log_dir_when_missing(tmp_path: Path) -> None:
    assert not (tmp_path / OASIS_LOG_DIR_NAME).exists()

    log_dir = ensure_oasis_log_dir(tmp_path)

    assert log_dir == tmp_path / OASIS_LOG_DIR_NAME
    assert log_dir.is_dir()


def test_existing_log_dir_is_no_error(tmp_path: Path) -> None:
    (tmp_path / OASIS_LOG_DIR_NAME).mkdir()

    log_dir = ensure_oasis_log_dir(tmp_path)

    assert log_dir.is_dir()


def test_conftest_created_log_dir_before_collection() -> None:
    # Die Conftest läuft im Controller vor jeder Testsammlung; danach muss
    # ``./log`` relativ zum Arbeitsverzeichnis existieren, sonst rennen die
    # Worker beim OASIS-Import wieder gegeneinander.
    assert Path(OASIS_LOG_DIR_NAME).is_dir()
