"""API-Tests für /api/profile (Onboarding Slice 2).

Blueprint-/Client-Konventionen exakt gespiegelt von
``tests/api/test_api_keys_api.py``: eigenständige Flask-App pro Testdatei,
Blueprint direkt registriert, kein Auth-Header (Slice 2 hat noch keine
API-Key-Pflicht für diese Endpunkte).
"""
from __future__ import annotations

import io
import re

import pytest
from flask import Flask

from app.api import user_profile_bp
from app.contracts.user_profile_contract import MAX_AVATAR_BYTES
from app.services.user_profile_store import reset_user_profile_store_for_tests

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_MINIMAL_PNG = _PNG_MAGIC + b"\x00" * 32
_SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
_AVATAR_REF_RE = re.compile(r"^avatar-[0-9a-f]{32}\.png$")


@pytest.fixture(autouse=True)
def _reset_store(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    reset_user_profile_store_for_tests()
    yield
    reset_user_profile_store_for_tests()


@pytest.fixture
def app() -> Flask:
    flask_app = Flask(__name__)
    flask_app.register_blueprint(user_profile_bp, url_prefix="/api/profile")
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app: Flask):
    return app.test_client()


def _create_profile(client, display_name: str = "Alex Schneider") -> dict:
    resp = client.put("/api/profile", json={"display_name": display_name})
    assert resp.status_code == 200
    return resp.get_json()["data"]["profile"]


class TestGetProfile:
    def test_returns_null_profile_when_none_exists(self, client) -> None:
        resp = client.get("/api/profile")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["profile"] is None

    def test_returns_profile_after_creation(self, client) -> None:
        _create_profile(client)
        resp = client.get("/api/profile")
        assert resp.status_code == 200
        profile = resp.get_json()["data"]["profile"]
        assert profile["display_name"] == "Alex Schneider"


class TestPutProfile:
    def test_invalid_schema_returns_400(self, client) -> None:
        resp = client.put("/api/profile", json={"theme": "not-a-real-theme"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert body["code"] == "invalid_request"

    def test_extra_field_returns_400_invalid_request(self, client) -> None:
        resp = client.put(
            "/api/profile", json={"display_name": "Alex", "avatar_ref": "x"}
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "invalid_request"

    def test_create_without_display_name_returns_display_name_required(
        self, client
    ) -> None:
        resp = client.put("/api/profile", json={"role": "Redakteurin"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert body["code"] == "display_name_required"

    def test_happy_path_creates_profile(self, client) -> None:
        resp = client.put(
            "/api/profile", json={"display_name": "Alex Schneider", "role": "Lead"}
        )
        assert resp.status_code == 200
        profile = resp.get_json()["data"]["profile"]
        assert profile["display_name"] == "Alex Schneider"
        assert profile["role"] == "Lead"

    def test_merge_update_preserves_untouched_fields(self, client) -> None:
        _create_profile(client)
        resp = client.put("/api/profile", json={"role": "Redakteurin"})
        assert resp.status_code == 200
        profile = resp.get_json()["data"]["profile"]
        assert profile["display_name"] == "Alex Schneider"
        assert profile["role"] == "Redakteurin"


class TestPostAvatar:
    def test_missing_file_returns_400(self, client) -> None:
        resp = client.post(
            "/api/profile/avatar", data={}, content_type="multipart/form-data"
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "missing_file"

    def test_without_profile_returns_409_profile_required(self, client) -> None:
        resp = client.post(
            "/api/profile/avatar",
            data={"file": (io.BytesIO(_MINIMAL_PNG), "avatar.png", "image/png")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "profile_required"

    def test_oversized_file_returns_413(self, client) -> None:
        _create_profile(client)
        oversized = _PNG_MAGIC + b"\x00" * (MAX_AVATAR_BYTES + 1)
        resp = client.post(
            "/api/profile/avatar",
            data={"file": (io.BytesIO(oversized), "avatar.png", "image/png")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 413
        assert resp.get_json()["code"] == "avatar_too_large"

    def test_svg_with_faked_png_content_type_is_rejected(self, client) -> None:
        _create_profile(client)
        resp = client.post(
            "/api/profile/avatar",
            data={"file": (io.BytesIO(_SVG_BYTES), "avatar.png", "image/png")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 415
        assert resp.get_json()["code"] == "unsupported_media_type"

    def test_valid_png_upload_returns_201_with_avatar_ref(self, client) -> None:
        _create_profile(client)
        resp = client.post(
            "/api/profile/avatar",
            data={"file": (io.BytesIO(_MINIMAL_PNG), "avatar.png", "image/png")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201
        profile = resp.get_json()["data"]["profile"]
        assert _AVATAR_REF_RE.match(profile["avatar_ref"])


class TestGetAvatar:
    def test_returns_404_without_avatar(self, client) -> None:
        _create_profile(client)
        resp = client.get("/api/profile/avatar")
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "avatar_not_found"

    def test_returns_image_after_upload(self, client) -> None:
        _create_profile(client)
        client.post(
            "/api/profile/avatar",
            data={"file": (io.BytesIO(_MINIMAL_PNG), "avatar.png", "image/png")},
            content_type="multipart/form-data",
        )
        resp = client.get("/api/profile/avatar")
        assert resp.status_code == 200
        assert resp.headers["Content-Type"].startswith("image/")
        assert resp.data.startswith(_PNG_MAGIC)


class TestDeleteAvatar:
    def test_without_profile_returns_409(self, client) -> None:
        resp = client.delete("/api/profile/avatar")
        assert resp.status_code == 409
        assert resp.get_json()["success"] is False

    def test_removes_avatar_reference(self, client) -> None:
        _create_profile(client)
        client.post(
            "/api/profile/avatar",
            data={"file": (io.BytesIO(_MINIMAL_PNG), "avatar.png", "image/png")},
            content_type="multipart/form-data",
        )
        resp = client.delete("/api/profile/avatar")
        assert resp.status_code == 200
        profile = resp.get_json()["data"]["profile"]
        assert profile["avatar_ref"] is None

        # Datei tatsächlich entfernt: erneuter GET liefert wieder 404.
        follow_up = client.get("/api/profile/avatar")
        assert follow_up.status_code == 404
