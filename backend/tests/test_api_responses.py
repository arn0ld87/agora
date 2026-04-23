"""Tests for app.utils.api_responses."""

from unittest.mock import patch

from flask import Flask

from app.utils.api_responses import handle_api_errors, json_error, json_success


def _build_app():
    app = Flask(__name__)
    return app


def test_json_success_minimal_envelope():
    app = _build_app()
    with app.test_request_context():
        response, status = json_success()
        payload = response.get_json()
        assert status == 200
        assert payload == {"success": True}


def test_json_success_wraps_data_and_extra_fields():
    app = _build_app()
    with app.test_request_context():
        response, status = json_success({"foo": "bar"}, count=2, meta={"x": 1})
        payload = response.get_json()
        assert status == 200
        assert payload == {
            "success": True,
            "data": {"foo": "bar"},
            "count": 2,
            "meta": {"x": 1},
        }


def test_json_error_default_is_400_without_traceback():
    app = _build_app()
    with app.test_request_context():
        response, status = json_error("boom")
        payload = response.get_json()
        assert status == 400
        assert payload == {"success": False, "error": "boom"}


def test_json_error_includes_code_and_traceback_when_requested():
    app = _build_app()
    with app.test_request_context():
        try:
            raise RuntimeError("kapow")
        except RuntimeError:
            response, status = json_error(
                "kapow",
                status=500,
                code="internal",
                include_traceback=True,
            )
            payload = response.get_json()
        assert status == 500
        assert payload["success"] is False
        assert payload["error"] == "kapow"
        assert payload["code"] == "internal"
        assert "Traceback" in payload["traceback"]


def test_handle_api_errors_passes_through_success_tuple():
    app = _build_app()

    @handle_api_errors
    def view():
        return json_success({"ok": True})

    with app.test_request_context():
        response, status = view()
    assert status == 200
    assert response.get_json() == {"success": True, "data": {"ok": True}}


def test_handle_api_errors_maps_value_error_to_400():
    app = _build_app()

    @handle_api_errors(log_prefix="Boom")
    def view():
        raise ValueError("bad input")

    with app.test_request_context():
        response, status = view()
    assert status == 400
    assert response.get_json() == {"success": False, "error": "bad input"}


def test_handle_api_errors_maps_timeout_to_504():
    app = _build_app()

    @handle_api_errors(log_prefix="Stuck")
    def view():
        raise TimeoutError("too slow")

    with app.test_request_context():
        response, status = view()
    assert status == 504
    payload = response.get_json()
    assert payload["success"] is False
    assert "timeout" in payload["error"].lower()
    assert "too slow" in payload["error"]


def test_handle_api_errors_maps_unknown_to_500_and_hides_traceback_outside_debug():
    app = _build_app()

    @handle_api_errors(log_prefix="Unexpected")
    def view():
        raise RuntimeError("kapow")

    with patch("app.utils.api_responses.Config") as mock_config:
        mock_config.DEBUG = False
        with app.test_request_context():
            response, status = view()
    payload = response.get_json()
    assert status == 500
    assert payload["success"] is False
    assert payload["error"] == "kapow"
    assert "traceback" not in payload


def test_handle_api_errors_includes_traceback_in_debug_mode():
    app = _build_app()

    @handle_api_errors(log_prefix="Unexpected")
    def view():
        raise RuntimeError("kapow")

    with patch("app.utils.api_responses.Config") as mock_config:
        mock_config.DEBUG = True
        with app.test_request_context():
            response, status = view()
    payload = response.get_json()
    assert status == 500
    assert "Traceback" in payload["traceback"]
