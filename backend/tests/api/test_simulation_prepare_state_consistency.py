"""Regression: Prepare-State darf keinen nicht persistierten Ready-Status melden.

Root Cause (vor dem Fix): ``check_simulation_prepared`` promotet einen
``preparing``-Zustand nach ``ready`` und faengt einen fehlgeschlagenen
``store.write_json`` still ab. Der Aufrufer in ``simulation_prepare.py``
uebersetzt ``is_prepared=True`` aber unabhaengig vom gemeldeten Detailstatus in
``status: "ready", progress: 100`` — die API meldet also ``ready``, waehrend
persistent weiterhin ``preparing`` steht.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from app.api import simulation_prepare_state as mod


class _FakeStore:
    """Minimaler ArtifactStore-Doppelgaenger mit steuerbarem Schreibfehler."""

    def __init__(self, state: dict[str, Any], *, write_fails: bool) -> None:
        self._state = state
        self._write_fails = write_fails
        self.written: list[dict[str, Any]] = []

    def exists(self, simulation_id: str, artifact: str) -> bool:
        return True

    def read_json(self, simulation_id: str, artifact: str, default: Any = None) -> Any:
        if artifact == "state":
            return dict(self._state)
        if artifact == "reddit_profiles":
            return [{"id": 1}]
        return default

    def write_json(self, simulation_id: str, artifact: str, payload: Any) -> None:
        if self._write_fails:
            raise OSError("disk full")
        self.written.append(payload)
        self._state = payload


@pytest.fixture()
def _simulation_dir(tmp_path, monkeypatch):
    sim_id = "sim_0123456789ab"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    (sim_dir / "twitter_profiles.csv").write_text("id\n1\n", encoding="utf-8")
    monkeypatch.setattr(mod.Config, "OASIS_SIMULATION_DATA_DIR", str(tmp_path))
    assert os.path.isdir(sim_dir)
    return sim_id


def _install_store(monkeypatch, store: _FakeStore) -> None:
    monkeypatch.setattr(mod, "get_artifact_store", lambda: store)


def test_failed_ready_persist_does_not_report_prepared(_simulation_dir, monkeypatch):
    store = _FakeStore(
        {"status": "preparing", "config_generated": True, "updated_at": "2026-01-01T00:00:00"},
        write_fails=True,
    )
    _install_store(monkeypatch, store)

    is_prepared, info = mod.check_simulation_prepared(_simulation_dir)

    assert is_prepared is False, "failed persist must not yield a positive prepared result"
    assert info.get("status") != "ready"


def test_successful_ready_persist_reports_ready(_simulation_dir, monkeypatch):
    store = _FakeStore(
        {"status": "preparing", "config_generated": True, "updated_at": "2026-01-01T00:00:00"},
        write_fails=False,
    )
    _install_store(monkeypatch, store)

    is_prepared, info = mod.check_simulation_prepared(_simulation_dir)

    assert is_prepared is True
    assert info["status"] == "ready"
    assert store.written and store.written[-1]["status"] == "ready"


def test_already_ready_state_is_untouched(_simulation_dir, monkeypatch):
    store = _FakeStore(
        {"status": "ready", "config_generated": True, "updated_at": "2026-01-01T00:00:00"},
        write_fails=True,
    )
    _install_store(monkeypatch, store)

    is_prepared, info = mod.check_simulation_prepared(_simulation_dir)

    assert is_prepared is True
    assert info["status"] == "ready"
    assert info["updated_at"] == "2026-01-01T00:00:00"
