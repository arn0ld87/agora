"""
Regression: ``AgentToolRegistry.web_fetch`` must not fetch untrusted URLs raw.

Before the fix this method called ``requests.get(url, allow_redirects=True)``
with a model-supplied URL, which made the simulation subprocess a confused
deputy for anything reachable from the container — including the cloud
metadata service. These tests fail loudly if that path ever comes back.
"""

from __future__ import annotations

import importlib
import socket
import sys
from pathlib import Path

import pytest

# backend/scripts auf sys.path, wie zur Laufzeit des OASIS-Subprozesses.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

agent_tools = importlib.import_module("agent_tools")


@pytest.fixture
def registry():
    return agent_tools.AgentToolRegistry()


@pytest.fixture(autouse=True)
def _no_raw_network(monkeypatch):
    """Any direct ``requests`` call from web_fetch is a test failure."""

    def _boom(*_args, **_kwargs):
        raise AssertionError("web_fetch must not call requests directly")

    monkeypatch.setattr(agent_tools.requests, "get", _boom)
    monkeypatch.setattr(agent_tools.requests, "request", _boom, raising=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://127.0.0.1:5001/api/status",
        "http://[::1]/",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/admin",
        "file:///etc/passwd",
        "http://host.docker.internal/",
    ],
)
def test_web_fetch_refuses_non_public_targets(registry, url):
    result = registry.web_fetch(url=url)

    assert "error" in result, f"expected a refusal for {url}, got {result!r}"
    assert "content" not in result
    assert "Blocked by outbound policy" in result["error"]


def test_web_fetch_goes_through_the_guard(registry, monkeypatch):
    """The happy path is served by the guarded fetcher, not by requests."""
    from app.security import outbound_http

    calls = []

    def _fake_fetch(url, policy=None):
        calls.append(url)
        return outbound_http.FetchResult(
            url=url,
            status=200,
            content_type="text/html",
            text="<html><body><p>Hallo Welt</p><script>x</script></body></html>",
            truncated=False,
        )

    monkeypatch.setattr(outbound_http, "fetch", _fake_fetch)

    result = registry.web_fetch(url="https://example.com/post", max_chars=100)

    assert calls == ["https://example.com/post"]
    assert result["url"] == "https://example.com/post"
    assert "Hallo Welt" in result["content"]
    # Script bodies are stripped before the text reaches the model.
    assert "<script>" not in result["content"]


def test_web_fetch_reports_final_url_after_redirect(registry, monkeypatch):
    from app.security import outbound_http

    monkeypatch.setattr(
        outbound_http,
        "fetch",
        lambda url, policy=None: outbound_http.FetchResult(
            url="https://example.com/final",
            status=200,
            content_type="text/html",
            text="<html>done</html>",
            truncated=False,
        ),
    )

    result = registry.web_fetch(url="https://example.com/start")
    assert result["url"] == "https://example.com/final"


def test_web_fetch_does_not_resolve_blocked_literals(registry, monkeypatch):
    """Literal non-public IPs are rejected without touching the resolver."""

    def _boom(*_args, **_kwargs):
        raise AssertionError("literal IP must not hit DNS")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)

    result = registry.web_fetch(url="http://169.254.169.254/")
    assert "error" in result


def test_http_error_is_reported_as_such_not_as_a_block(registry, monkeypatch):
    """404 ist keine Richtlinienentscheidung.

    Meldete web_fetch hier "Blocked by outbound policy", suchte das Modell ein
    Rechteproblem, das es nicht gibt — statt zu erkennen, dass die Seite nicht
    existiert.
    """
    from app.security import outbound_http

    def _raise(url, policy=None):
        raise outbound_http.OutboundHttpError(404, url)

    monkeypatch.setattr(outbound_http, "fetch", _raise)

    result = registry.web_fetch(url="https://example.com/weg")

    assert result["error"] == "HTTP 404"
    assert "Blocked" not in result["error"]


def test_error_page_body_never_reaches_the_model(registry, monkeypatch):
    """Der Fehlerstatus schlaegt durch, nicht der Inhalt der Fehlerseite."""
    from app.security import outbound_http

    monkeypatch.setattr(
        outbound_http,
        "fetch",
        lambda url, policy=None: (_ for _ in ()).throw(
            outbound_http.OutboundHttpError(500, url)
        ),
    )

    result = registry.web_fetch(url="https://example.com/kaputt")
    assert "content" not in result
