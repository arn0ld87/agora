"""Tests for app.utils.api_responses."""

from unittest.mock import patch

from flask import Flask, abort

from app.utils.api_responses import (
    handle_api_errors,
    install_api_error_handlers,
    json_error,
    json_success,
)


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


def test_json_error_keeps_traceback_out_of_response_when_requested():
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
        assert "traceback" not in payload


def test_handle_api_errors_passes_through_success_tuple():
    app = _build_app()

    @handle_api_errors
    def view():
        return json_success({"ok": True})

    with app.test_request_context():
        response, status = view()
    assert status == 200
    assert response.get_json() == {"success": True, "data": {"ok": True}}


def test_handle_api_errors_wraps_raw_dict_return():
    app = _build_app()

    @handle_api_errors
    def view():
        return {"ok": True}

    with patch("app.utils.api_responses.Config") as mock_config:
        mock_config.DEBUG = False
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


def test_handle_api_errors_maps_timeout_to_504_without_leaking_detail_outside_debug():
    app = _build_app()

    @handle_api_errors(log_prefix="Stuck")
    def view():
        raise TimeoutError("too slow")

    with patch("app.utils.api_responses.Config") as mock_config:
        mock_config.DEBUG = False
        with app.test_request_context():
            response, status = view()
    assert status == 504
    payload = response.get_json()
    assert payload == {
        "success": False,
        "error": "request timed out",
        "code": "timeout",
    }


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
    assert payload == {
        "success": False,
        "error": "internal server error",
        "code": "internal_error",
    }
    assert "traceback" not in payload
    assert "kapow" not in payload.values()


def test_handle_api_errors_in_debug_mode_exposes_error_class_but_not_message():
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
    assert payload["error"] == "internal server error"
    assert payload["code"] == "internal_error"
    assert payload["debug_error_class"] == "builtins.RuntimeError"
    assert "debug_error" not in payload
    assert "kapow" not in payload.values()
    assert "traceback" not in payload


def test_install_api_error_handlers_envelopes_api_404():
    app = _build_app()
    install_api_error_handlers(app)
    client = app.test_client()

    response = client.get("/api/missing")

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "error": "not found",
        "code": "not_found",
    }


def test_install_api_error_handlers_envelopes_api_405():
    app = _build_app()

    @app.route("/api/items", methods=["GET"])
    def get_items():
        return json_success([])

    install_api_error_handlers(app)
    client = app.test_client()

    response = client.post("/api/items")

    assert response.status_code == 405
    assert response.get_json() == {
        "success": False,
        "error": "method not allowed",
        "code": "method_not_allowed",
    }


def test_install_api_error_handlers_envelopes_generic_api_http_errors():
    app = _build_app()

    @app.route("/api/bad-request")
    def bad_request():
        abort(400, description="invalid payload")

    install_api_error_handlers(app)
    client = app.test_client()

    response = client.get("/api/bad-request")

    assert response.status_code == 400
    assert response.get_json() == {
        "success": False,
        "error": "invalid payload",
        "code": "bad_request",
    }


def test_install_api_error_handlers_envelopes_uncaught_api_exceptions_safely():
    app = _build_app()

    @app.route("/api/explodes")
    def explodes():
        raise RuntimeError("database password is hunter2")

    install_api_error_handlers(app)
    client = app.test_client()

    with patch("app.utils.api_responses.Config") as mock_config:
        mock_config.DEBUG = False
        response = client.get("/api/explodes")

    assert response.status_code == 500
    assert response.get_json() == {
        "success": False,
        "error": "internal server error",
        "code": "internal_error",
    }


def test_install_api_error_handlers_preserves_non_api_404():
    app = _build_app()
    install_api_error_handlers(app)
    client = app.test_client()

    response = client.get("/missing")

    assert response.status_code == 404
    assert response.is_json is False


def test_json_error_sanitizes_pydantic_validation_error_payload():
    """Regression: Pydantic v2 ``ValidationError.errors()`` may carry live
    ``ValueError`` instances in the ``ctx`` field. Without sanitization,
    ``flask.jsonify`` would crash and turn a 4xx into a 500.
    """
    from pydantic import BaseModel, Field, ValidationError

    class _Probe(BaseModel):
        extra_config: dict[str, int] = Field(default_factory=dict)

    try:
        _Probe.model_validate({"extra_config": {"not_int": "boom"}})
    except ValidationError as exc:
        raw_errors = exc.errors(include_url=False)

    app = _build_app()
    with app.test_request_context():
        response, status = json_error(
            "Invalid request",
            status=400,
            code="invalid_request",
            extra={"errors": raw_errors},
        )
        payload = response.get_json()

    assert status == 400
    assert payload["success"] is False
    assert payload["code"] == "invalid_request"
    # Alle ``ctx``-Werte muessen serialisierbar sein; ValueError-Instanzen
    # werden via ``_to_jsonable`` zu Strings.
    for entry in payload["errors"]:
        if "ctx" in entry:
            ctx = entry["ctx"]
            assert isinstance(ctx, dict)
            for v in ctx.values():
                assert not isinstance(v, BaseException)


def test_debug_extra_redacts_exception_message():
    """_debug_extra darf die Exception-Message nicht in den Response leaken.

    Regression-Test fuer Issue #1058: in DEBUG-Modus wurde str(exc) inkl.
    Sentinel/Pfade/Secrets in den Response-Body geschrieben. Nach dem Fix
    enthaelt das Response-Extra nur den Klassennamen.
    """
    from app.utils.api_responses import _debug_extra

    secret = "sk-upl-deadbeef-leak-do-not-ship"
    exc = OSError(f"disk write failed: {secret} on /tmp/secret/path")

    with patch("app.utils.api_responses.Config") as mock_config:
        mock_config.DEBUG = True
        extra = _debug_extra(exc)

    assert extra is not None
    assert "debug_error_class" in extra
    assert secret not in str(extra)
    assert "/tmp/secret/path" not in str(extra)
    # Klassennamen-String ist nicht leer und kein Leerstring-Workaround
    assert extra["debug_error_class"]
    assert isinstance(extra["debug_error_class"], str)
    # Sanity: Klassenname enthaelt "OSError"
    assert "OSError" in extra["debug_error_class"]


def test_json_error_falls_back_to_string_for_unknown_objects():
    """Gemini-Finding (HIGH): ``_to_jsonable`` muss auch fuer Objekte, die
    weder Pydantic noch der Exception-Klausel bekannt sind, eine JSON-
    kompatible Form liefern. Sonst kippt die Sanitizer-Sicherheit.
    """

    class _Weird:
        def __repr__(self) -> str:
            return "<weird>"

    app = _build_app()
    with app.test_request_context():
        response, status = json_error(
            "boom",
            status=400,
            extra={"weird": _Weird(), "container": {"nested": _Weird()}},
        )
        payload = response.get_json()

    assert status == 400
    assert payload["weird"] == "<weird>"
    assert payload["container"] == {"nested": "<weird>"}

