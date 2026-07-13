"""Tests fuer ``embedding_ollama_pull`` (Onboarding Slice 4.3)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.embedding_ollama_pull import (
    DEFAULT_TIMEOUT_SECONDS,
    OllamaPullError,
    pull_model,
    validate_model_name,
)


# ----------------------------------------------------------------------
# Model-Name-Validierung (Security)
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "nomic-embed-text",
        "mxbai-embed-large",
        "all-minilm",
        "snowflake-arctic-embed:335m",
        "model.v1",
        "bge-m3",
    ],
)
def test_validate_model_name_accepts_valid_names(name: str) -> None:
    assert validate_model_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        "name with spaces",
        "name;rm -rf /",
        "$(echo evil)",
        "name`backtick`",
        "name|pipe",
        "name\nnewline",
        "a" * 200,  # zu lang
        "naïve",  # Unicode
        "naïve-model",  # Unicode im Namen
    ],
)
def test_validate_model_name_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(ValueError):
        validate_model_name(name)


# ----------------------------------------------------------------------
# Base-URL-Validierung
# ----------------------------------------------------------------------


def test_pull_model_rejects_non_http_base_url() -> None:
    with pytest.raises(OllamaPullError, match="http"):
        pull_model(model="nomic-embed-text", base_url="ftp://evil.test")


# ----------------------------------------------------------------------
# HTTP-Stream-Parsing
# ----------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, events: list[dict], status_code: int = 200) -> None:
        self._events = events
        self.status_code = status_code
        self.text = ""

    def iter_lines(self) -> list[bytes]:
        return [json.dumps(event).encode("utf-8") for event in self._events]


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[dict] = []

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def post(
        self, url: str, json: dict, headers: dict, timeout: float, stream: bool
    ) -> _FakeResponse:
        self.calls.append(
            {"url": url, "json": json, "headers": headers, "stream": stream}
        )
        return self._response


def test_pull_model_reports_success_on_complete_stream() -> None:
    events = [
        {"status": "pulling manifest"},
        {"status": "downloading", "digest": "sha256:abc", "total": 1000, "completed": 250},
        {"status": "downloading", "digest": "sha256:abc", "total": 1000, "completed": 1000},
        {"status": "verifying"},
        {"status": "success", "digest": "sha256:abc"},
    ]
    fake_session = _FakeSession(_FakeResponse(events))
    report = pull_model(
        model="nomic-embed-text",
        base_url="http://localhost:11434",
        session_factory=lambda: fake_session,
    )

    assert report.status == "success"
    assert report.digest == "sha256:abc"
    assert report.total_bytes == 1000
    assert report.completed_bytes == 1000
    assert report.layers_downloaded == 1
    assert report.error_message is None
    # Authorization-Header fehlt (kein API-Key).
    assert "Authorization" not in fake_session.calls[0]["headers"]


def test_pull_model_sends_bearer_when_api_key_is_set() -> None:
    events = [{"status": "success", "digest": "sha256:abc"}]
    fake_session = _FakeSession(_FakeResponse(events))
    report = pull_model(
        model="nomic-embed-text",
        base_url="https://ollama.com",
        api_key="sk-abc",
        session_factory=lambda: fake_session,
    )
    assert report.status == "success"
    assert fake_session.calls[0]["headers"]["Authorization"] == "Bearer sk-abc"
    # Base-URL wird mit /api/pull ergaenzt.
    assert fake_session.calls[0]["url"] == "https://ollama.com/api/pull"
    # Payload sendet model + stream=True.
    assert fake_session.calls[0]["json"] == {
        "name": "nomic-embed-text",
        "stream": True,
    }


def test_pull_model_reports_error_on_stream_error_event() -> None:
    events = [
        {"status": "pulling manifest"},
        {"error": "model not found"},
    ]
    fake_session = _FakeSession(_FakeResponse(events))
    with pytest.raises(OllamaPullError, match="model not found"):
        pull_model(
            model="nomic-embed-text",
            base_url="http://localhost:11434",
            session_factory=lambda: fake_session,
        )


def test_pull_model_reports_error_on_auth_failure() -> None:
    fake_session = _FakeSession(_FakeResponse([], status_code=401))
    with pytest.raises(OllamaPullError, match="Authentifizierung"):
        pull_model(
            model="nomic-embed-text",
            base_url="https://ollama.com",
            api_key="wrong-key",
            session_factory=lambda: fake_session,
        )


def test_pull_model_handles_empty_stream() -> None:
    fake_session = _FakeSession(_FakeResponse([]))
    report = pull_model(
        model="nomic-embed-text",
        base_url="http://localhost:11434",
        session_factory=lambda: fake_session,
    )
    assert report.status == "error"
    assert "letzter Status=None" in (report.error_message or "")


# ----------------------------------------------------------------------
# Default-Timeout-Konfiguration
# ----------------------------------------------------------------------


def test_default_timeout_is_10_minutes() -> None:
    assert DEFAULT_TIMEOUT_SECONDS == 600
