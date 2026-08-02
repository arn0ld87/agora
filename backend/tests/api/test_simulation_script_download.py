"""Tests für ``/api/simulation/script/<script_name>/download`` (#1017).

``action_logger.py`` importiert seit #1016
``app.contracts.sim_action_log_contract.RoundEndEvent``. Ein isolierter
Einzeldatei-Download bricht außerhalb des Repos mit ``ModuleNotFoundError``.
Der Endpoint muss für ``action_logger.py`` stattdessen ein ZIP-Bundle
ausliefern, das den Contract mitbringt — die drei anderen Skripte bleiben
unverändert Einzeldatei-Downloads.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import zipfile

import pytest
from flask import Flask

from app.api import simulation_bp

_BACKEND_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_CONTRACT_PATH = os.path.join(
    _BACKEND_ROOT, "app", "contracts", "sim_action_log_contract.py"
)

EXPECTED_BUNDLE_NAMES = {
    "action_logger.py",
    "app/__init__.py",
    "app/contracts/__init__.py",
    "app/contracts/sim_action_log_contract.py",
}


@pytest.fixture
def client(monkeypatch):
    # @allow_ticket_auth greift nur mit gesetztem AGORA_AUTH_TOKEN. Diese
    # Tests prüfen den Download-Inhalt, nicht Auth — Open-Mode erzwingen.
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.config["TESTING"] = True
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


class TestActionLoggerBundleDownload:
    def test_returns_zip_with_expected_paths(self, client):
        resp = client.get("/api/simulation/script/action_logger.py/download")

        assert resp.status_code == 200
        cd = resp.headers.get("Content-Disposition", "")
        assert "action_logger_bundle.zip" in cd
        assert resp.headers.get("Content-Type", "").startswith("application/zip")

        with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
            names = set(zf.namelist())
            assert names == EXPECTED_BUNDLE_NAMES

    def test_init_files_are_empty(self, client):
        resp = client.get("/api/simulation/script/action_logger.py/download")
        assert resp.status_code == 200

        with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
            assert zf.read("app/__init__.py") == b""
            assert zf.read("app/contracts/__init__.py") == b""

    def test_contract_content_is_byte_identical(self, client):
        resp = client.get("/api/simulation/script/action_logger.py/download")
        assert resp.status_code == 200

        with open(_CONTRACT_PATH, "rb") as f:
            expected_contract = f.read()

        with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
            bundled_contract = zf.read("app/contracts/sim_action_log_contract.py")

        assert bundled_contract == expected_contract

    def test_extracted_bundle_is_independently_importable(self, client, tmp_path):
        """Das entpackte Bundle muss außerhalb des Repos importierbar sein.

        Läuft in einem Subprozess mit bereinigtem PYTHONPATH, da der bereits
        geladene ``app``-Namespace des Testlaufs den Fehler sonst maskieren
        würde.
        """
        resp = client.get("/api/simulation/script/action_logger.py/download")
        assert resp.status_code == 200

        with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
            zf.extractall(tmp_path)

        env = dict(os.environ)
        env.pop("PYTHONPATH", None)

        result = subprocess.run(
            [sys.executable, "-c", "import action_logger"],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "ModuleNotFoundError" not in result.stderr

    def test_other_scripts_remain_single_file_download(self, client):
        resp = client.get(
            "/api/simulation/script/run_parallel_simulation.py/download"
        )

        assert resp.status_code == 200
        cd = resp.headers.get("Content-Disposition", "")
        assert "run_parallel_simulation.py" in cd
        assert ".zip" not in cd
        # Kein ZIP-Inhalt — die Datei ist als Rohtext lesbar.
        with pytest.raises(zipfile.BadZipFile):
            zipfile.ZipFile(io.BytesIO(resp.data))
