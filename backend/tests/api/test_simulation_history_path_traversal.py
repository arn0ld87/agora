"""SEC-1 / #1669 Slice B: CodeQL py/path-injection in ``GET .../posts``.

Alert #27 (``backend/app/api/simulation_history.py:312`` auf ``origin/main``
@ ``9eb20a931``): ``simulation_id`` wird ueber ``validate_simulation_id``
geprueft, ``platform`` (Query-Parameter) landete dagegen ungeprueft im
Dateinamen, den ``ArtifactLocator.simulation_file`` an ``os.path.exists``
weiterreicht (``f"{platform}_simulation.db"``). Diese Suite fixiert, dass ein
Traversal-Versuch in ``platform`` mit HTTP 400 abgelehnt wird, bevor er das
Dateisystem erreicht.
"""

from __future__ import annotations

import pytest
from flask import Flask

from app.api import simulation_bp


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


VALID_SIM_ID = "sim_" + "a" * 12


@pytest.mark.parametrize(
    "platform",
    [
        "../etc",
        "../../etc/passwd",
        "a/b",
        "..",
        "/etc/passwd",
    ],
)
def test_get_simulation_posts_rejects_platform_traversal(client, platform):
    response = client.get(
        f"/api/simulation/{VALID_SIM_ID}/posts",
        query_string={"platform": platform},
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
