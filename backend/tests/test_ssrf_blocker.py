"""
SSRF-Blocker-Regression (Slice 12, F5 of repo review).

Locks ``app.services.web_tools._is_public_url`` against the case classes the
Repo-Review explicitly demanded: loopback (v4 + v6), private RFC1918, AWS
metadata, IPv6 link-local, plus a positive control that public hosts pass.

We monkeypatch ``socket.getaddrinfo`` so the tests work without DNS and don't
hit the network. Public-host case uses a stable static IP (AWS S3 example
range) so we don't depend on real DNS either.
"""

from __future__ import annotations

import socket
from typing import List, Tuple

import pytest

from app.services.web_tools import _is_public_url


def _fake_getaddrinfo_factory(addresses: List[str]):
    """Build a getaddrinfo replacement that returns the given addresses."""

    def _fake(*_args, **_kwargs) -> List[Tuple]:
        out = []
        for addr in addresses:
            family = socket.AF_INET6 if ":" in addr else socket.AF_INET
            out.append((family, socket.SOCK_STREAM, 0, "", (addr, 0)))
        return out

    return _fake


# ── Negative cases (must reject) ────────────────────────────────────────────


@pytest.mark.parametrize(
    "host, ip",
    [
        ("localhost", "127.0.0.1"),
        ("loopback.example", "127.0.0.1"),
        ("internal-vm", "10.0.0.1"),
        # 169.254.169.254 is the AWS/EC2 metadata IP. The link-local prefix
        # 169.254/16 already triggers ``is_link_local``, so the dedicated
        # metadata-blacklist path is defense-in-depth — either reason is a
        # valid reject; we only assert the reject itself.
        ("metadata.example", "169.254.169.254"),
        ("ipv6-loopback.example", "::1"),
        ("ipv6-link-local.example", "fe80::1"),
    ],
)
def test_blocks_non_public_targets(monkeypatch, host: str, ip: str):
    """Each non-public target class returns ``(False, <some reason>)``."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo_factory([ip]))

    ok, reason = _is_public_url(f"https://{host}/path")

    assert ok is False
    assert reason, "reject must come with a non-empty reason"


def test_blocks_unsupported_scheme():
    """ftp://, file://, gopher:// etc. are rejected before DNS even happens."""
    ok, reason = _is_public_url("ftp://example.com/secret")
    assert ok is False
    assert "scheme" in reason


def test_blocks_dns_resolution_failure(monkeypatch):
    """When DNS itself fails, the URL is rejected (not silently passed)."""

    def _raise(*_args, **_kwargs):
        raise socket.gaierror("nodename nor servname provided")

    monkeypatch.setattr(socket, "getaddrinfo", _raise)

    ok, reason = _is_public_url("https://does-not-resolve.invalid/")
    assert ok is False
    assert "dns" in reason.lower()


def test_blocks_when_any_resolution_is_internal(monkeypatch):
    """Multi-result DNS where one entry is private must reject the whole URL."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _fake_getaddrinfo_factory(["93.184.216.34", "10.0.0.5"]),
    )

    ok, reason = _is_public_url("https://dual-homed.example/")
    assert ok is False
    assert "10.0.0.5" in reason or "non-public" in reason


# ── Positive control (must pass) ─────────────────────────────────────────────


def test_allows_public_target(monkeypatch):
    """A canonical public IP passes through."""
    # 93.184.216.34 is example.com's stable IP and unambiguously public.
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo_factory(["93.184.216.34"]))

    ok, reason = _is_public_url("https://example.com/some/path")
    assert ok is True
    assert reason == ""
