"""
SSRF regression suite for the guarded outbound fetcher.

Covers the four layers of ``app.security.outbound_http``: URL shape, address
classification, connection pinning and per-hop redirect validation. Nothing
here touches the network — DNS is faked via ``socket.getaddrinfo`` and the
transport via ``_open_pinned_pool`` — so the suite is deterministic and safe to
run in CI.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from typing import Iterator

import pytest

from app.security import outbound_http
from app.security.outbound_http import (
    DEFAULT_POLICY,
    OutboundHttpPolicy,
    OutboundRequestBlocked,
    ResolvedTarget,
    fetch,
    validate_url,
)

PUBLIC_IP = "93.184.216.34"
OTHER_PUBLIC_IP = "203.0.113.10"  # TEST-NET-3, reserved → only used as a DNS answer


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

def _fake_dns(monkeypatch, mapping: dict[str, list[str]]) -> None:
    """Route ``socket.getaddrinfo`` through a hostname → addresses table."""

    def _fake(host, *_args, **_kwargs):
        try:
            addresses = mapping[host]
        except KeyError:
            raise socket.gaierror(f"unknown host {host}") from None
        return [
            (
                socket.AF_INET6 if ":" in addr else socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (addr, 0),
            )
            for addr in addresses
        ]

    monkeypatch.setattr(socket, "getaddrinfo", _fake)


@dataclass
class Hop:
    """One canned HTTP response."""

    status: int = 200
    headers: dict = field(default_factory=lambda: {"Content-Type": "text/html"})
    body: bytes = b"<html><body>hello</body></html>"


class _FakeResponse:
    def __init__(self, hop: Hop) -> None:
        self.status = hop.status
        self.headers = hop.headers
        self._body = hop.body
        self.released = False

    def stream(self, amt: int, decode_content: bool = True) -> Iterator[bytes]:
        for i in range(0, len(self._body), amt):
            yield self._body[i : i + amt]

    def release_conn(self) -> None:
        self.released = True


class _FakePool:
    def __init__(self, hop: Hop, recorder: "_Recorder") -> None:
        self._hop = hop
        self._recorder = recorder
        self.closed = False

    def urlopen(self, method, url, headers=None, **kwargs):
        self._recorder.requests.append(
            {"method": method, "url": url, "headers": dict(headers or {}), "kwargs": kwargs}
        )
        return _FakeResponse(self._hop)

    def close(self) -> None:
        self.closed = True


@dataclass
class _Recorder:
    targets: list = field(default_factory=list)
    requests: list = field(default_factory=list)


def _install_transport(monkeypatch, hops: list[Hop]) -> _Recorder:
    """Replace the pinned pool with a scripted fake, recording every hop."""
    recorder = _Recorder()
    remaining = list(hops)

    def _factory(target, policy):
        recorder.targets.append(target)
        assert remaining, "transport called more often than the script allows"
        return _FakePool(remaining.pop(0), recorder)

    monkeypatch.setattr(outbound_http, "_open_pinned_pool", _factory)
    return recorder


# --------------------------------------------------------------------------- #
# Layer 1 — URL shape
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/secret",
        "file:///etc/passwd",
        "gopher://example.com/",
        "redis://example.com:6379/",
    ],
)
def test_rejects_non_http_schemes(url):
    with pytest.raises(OutboundRequestBlocked) as exc:
        validate_url(url)
    assert "scheme" in str(exc.value)


def test_rejects_url_with_credentials(monkeypatch):
    """Userinfo is both a log-leak risk and an authority-confusion trick."""
    _fake_dns(monkeypatch, {"example.com": [PUBLIC_IP]})
    with pytest.raises(OutboundRequestBlocked) as exc:
        validate_url("https://user:secret@example.com/")
    assert "credentials" in str(exc.value)
    # The secret must not be echoed back in the reason.
    assert "secret" not in exc.value.reason


def test_rejects_missing_host():
    with pytest.raises(OutboundRequestBlocked):
        validate_url("http:///just-a-path")


@pytest.mark.parametrize(
    "host",
    [
        "metadata.google.internal",
        "host.docker.internal",
        "kubernetes.default.svc",
        "anything.internal",
        "printer.local",
        "foo.localhost",
    ],
)
def test_rejects_internal_hostnames(monkeypatch, host):
    """Blocked by name — these must not even reach the resolver."""
    # Deliberately map them to a *public* IP: if the name check were missing,
    # the address check would wave them through.
    _fake_dns(monkeypatch, {host: [PUBLIC_IP]})
    with pytest.raises(OutboundRequestBlocked):
        validate_url(f"http://{host}/")


# --------------------------------------------------------------------------- #
# Layer 2 — address classification
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",        # loopback v4
        "::1",              # loopback v6
        "10.0.0.5",         # RFC1918
        "172.16.4.1",       # RFC1918
        "192.168.1.1",      # RFC1918
        "169.254.169.254",  # cloud metadata
        "fd00:ec2::254",    # cloud metadata over IPv6
        "100.100.100.200",  # Alibaba metadata
        "fe80::1",          # link-local v6
        "169.254.10.1",     # link-local v4
        "0.0.0.0",          # unspecified
        "100.64.0.1",       # CGNAT
        "224.0.0.1",        # multicast
        "fc00::1",          # unique local
    ],
)
def test_blocks_non_public_resolution(monkeypatch, ip):
    _fake_dns(monkeypatch, {"target.example": [ip]})
    with pytest.raises(OutboundRequestBlocked) as exc:
        validate_url("https://target.example/path")
    assert exc.value.reason


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::ffff:127.0.0.1]/",   # IPv4-mapped IPv6 loopback
        "http://[::ffff:10.0.0.1]/",    # IPv4-mapped IPv6 RFC1918
    ],
)
def test_blocks_literal_non_public_addresses(url):
    """Literal IPs never reach the resolver, so they need their own check."""
    with pytest.raises(OutboundRequestBlocked):
        validate_url(url)


def test_blocks_when_any_dns_answer_is_private(monkeypatch):
    """A single private answer poisons the whole hostname (DNS round-robin)."""
    _fake_dns(monkeypatch, {"dual.example": [PUBLIC_IP, "10.0.0.5"]})
    with pytest.raises(OutboundRequestBlocked) as exc:
        validate_url("https://dual.example/")
    assert "10.0.0.5" in exc.value.reason


def test_blocks_dns_failure(monkeypatch):
    _fake_dns(monkeypatch, {})
    with pytest.raises(OutboundRequestBlocked) as exc:
        validate_url("https://nope.invalid/")
    assert "dns" in exc.value.reason.lower()


def test_allows_public_target(monkeypatch):
    _fake_dns(monkeypatch, {"example.com": [PUBLIC_IP]})
    target = validate_url("https://example.com/some/path?q=1")
    assert target.ip == PUBLIC_IP
    assert target.host == "example.com"
    assert target.port == 443
    assert target.request_target == "/some/path?q=1"


# --------------------------------------------------------------------------- #
# Layer 3 — connection pinning
# --------------------------------------------------------------------------- #

def test_connects_to_validated_ip_not_hostname(monkeypatch):
    """The whole point of pinning: the socket goes to the address we checked.

    Re-resolving the hostname at connect time is the DNS-rebinding window.
    """
    _fake_dns(monkeypatch, {"example.com": [PUBLIC_IP]})
    recorder = _install_transport(monkeypatch, [Hop()])

    fetch("http://example.com/page")

    assert recorder.targets[0].ip == PUBLIC_IP
    # ...while the Host header keeps the real name, so vhosts and TLS still work.
    assert recorder.requests[0]["headers"]["Host"] == "example.com"


def test_host_header_carries_non_default_port(monkeypatch):
    _fake_dns(monkeypatch, {"example.com": [PUBLIC_IP]})
    recorder = _install_transport(monkeypatch, [Hop()])

    fetch("http://example.com:8080/page")

    assert recorder.requests[0]["headers"]["Host"] == "example.com:8080"


# --------------------------------------------------------------------------- #
# Layer 4 — redirects
# --------------------------------------------------------------------------- #

def test_redirect_to_private_address_is_blocked(monkeypatch):
    """The classic bypass: a public URL that 302s into the metadata service."""
    _fake_dns(
        monkeypatch,
        {"public.example": [PUBLIC_IP], "evil.example": ["169.254.169.254"]},
    )
    _install_transport(
        monkeypatch,
        [Hop(status=302, headers={"Location": "http://evil.example/latest/meta-data/"})],
    )

    with pytest.raises(OutboundRequestBlocked) as exc:
        fetch("https://public.example/start")
    assert exc.value.reason


def test_redirect_to_literal_metadata_ip_is_blocked(monkeypatch):
    _fake_dns(monkeypatch, {"public.example": [PUBLIC_IP]})
    _install_transport(
        monkeypatch,
        [Hop(status=301, headers={"Location": "http://169.254.169.254/"})],
    )

    with pytest.raises(OutboundRequestBlocked):
        fetch("https://public.example/start")


def test_relative_redirect_between_public_targets_is_followed(monkeypatch):
    _fake_dns(monkeypatch, {"public.example": [PUBLIC_IP]})
    recorder = _install_transport(
        monkeypatch,
        [
            Hop(status=302, headers={"Location": "/final"}),
            Hop(body=b"<html>done</html>"),
        ],
    )

    result = fetch("https://public.example/start")

    assert result.url == "https://public.example/final"
    assert "done" in result.text
    assert [r["url"] for r in recorder.requests] == ["/start", "/final"]


def test_redirect_limit_is_enforced(monkeypatch):
    _fake_dns(monkeypatch, {"public.example": [PUBLIC_IP]})
    policy = OutboundHttpPolicy(max_redirects=2)
    _install_transport(
        monkeypatch,
        [Hop(status=302, headers={"Location": "/next"}) for _ in range(3)],
    )

    with pytest.raises(OutboundRequestBlocked) as exc:
        fetch("https://public.example/start", policy)
    assert "redirect" in exc.value.reason.lower()


def test_redirect_without_location_is_rejected(monkeypatch):
    _fake_dns(monkeypatch, {"public.example": [PUBLIC_IP]})
    _install_transport(monkeypatch, [Hop(status=302, headers={})])

    with pytest.raises(OutboundRequestBlocked):
        fetch("https://public.example/start")


# --------------------------------------------------------------------------- #
# Response handling
# --------------------------------------------------------------------------- #

def test_body_is_capped_and_marked_truncated(monkeypatch):
    _fake_dns(monkeypatch, {"public.example": [PUBLIC_IP]})
    policy = OutboundHttpPolicy(max_response_bytes=1000)
    _install_transport(monkeypatch, [Hop(body=b"x" * 50_000)])

    result = fetch("https://public.example/big", policy)

    assert result.truncated is True
    assert len(result.text) <= 1000


def test_rejects_unsupported_content_type(monkeypatch):
    _fake_dns(monkeypatch, {"public.example": [PUBLIC_IP]})
    _install_transport(
        monkeypatch,
        [Hop(headers={"Content-Type": "application/octet-stream"}, body=b"\x00" * 10)],
    )

    with pytest.raises(OutboundRequestBlocked) as exc:
        fetch("https://public.example/blob")
    assert "content type" in exc.value.reason.lower()


def test_decodes_declared_charset(monkeypatch):
    _fake_dns(monkeypatch, {"public.example": [PUBLIC_IP]})
    _install_transport(
        monkeypatch,
        [
            Hop(
                headers={"Content-Type": "text/html; charset=iso-8859-1"},
                body="Grüße".encode("iso-8859-1"),
            )
        ],
    )

    result = fetch("https://public.example/page")
    assert "Grüße" in result.text


# --------------------------------------------------------------------------- #
# Echte Pool-Konstruktion — ohne Mock
# --------------------------------------------------------------------------- #
#
# Die Tests oben ersetzen `_open_pinned_pool` vollstaendig. Dadurch blieb
# ausgerechnet das sicherheitskritischste Stueck — das Pinning selbst — in
# jedem Lauf unausgefuehrt, und ein `TypeError` beim Verbindungsaufbau fiel
# nicht auf: `server_hostname` war als `conn_kw={...}` uebergeben worden und
# kam dort verschachtelt an. Jeder echte HTTPS-Abruf waere abgestuerzt.
#
# Diese Tests bauen Pool und Connection wirklich. `_new_conn()` erzeugt nur das
# Connection-Objekt und oeffnet noch keinen Socket — die Tests bleiben damit
# netzfrei und deterministisch.

class TestPinnedPoolConstruction:
    def _target(self, scheme: str = "https", port: int = 443) -> ResolvedTarget:
        return ResolvedTarget(
            url=f"{scheme}://example.com/x",
            scheme=scheme,
            host="example.com",
            port=port,
            ip=PUBLIC_IP,
            request_target="/x",
            host_header="example.com",
        )

    def test_https_connection_is_pinned_to_the_validated_ip(self):
        pool = outbound_http._open_pinned_pool(self._target(), DEFAULT_POLICY)
        try:
            conn = pool._new_conn()
        finally:
            pool.close()

        # Verbunden wird mit der geprueften Adresse …
        assert conn.host == PUBLIC_IP

    def test_https_connection_keeps_tls_anchored_to_the_hostname(self):
        """Pinning darf TLS nicht schwaechen.

        SNI und Zertifikatspruefung muessen am echten Hostnamen haengen,
        sonst wuerde das Zertifikat gegen eine IP geprueft und der Abruf
        entweder scheitern oder — schlimmer — ungeprueft durchgehen.
        """
        pool = outbound_http._open_pinned_pool(self._target(), DEFAULT_POLICY)
        try:
            conn = pool._new_conn()
        finally:
            pool.close()

        assert conn.server_hostname == "example.com"
        assert conn.assert_hostname == "example.com"
        assert conn.cert_reqs == "CERT_REQUIRED"

    def test_plain_http_pool_is_pinned_too(self):
        target = self._target(scheme="http", port=80)
        pool = outbound_http._open_pinned_pool(target, DEFAULT_POLICY)
        try:
            conn = pool._new_conn()
        finally:
            pool.close()

        assert conn.host == PUBLIC_IP

    def test_non_default_port_is_honoured(self):
        target = self._target(scheme="https", port=8443)
        pool = outbound_http._open_pinned_pool(target, DEFAULT_POLICY)
        try:
            assert pool.port == 8443
        finally:
            pool.close()


# --------------------------------------------------------------------------- #
# Fehlerstatus der Gegenstelle
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 500, 502, 503])
def test_error_status_is_raised_not_returned_as_content(monkeypatch, status: int):
    """Die HTML-Fehlerseite eines 404 ist kein Seiteninhalt.

    Der Vorgaengercode hatte dafuer `raise_for_status()`; beim Umbau ging das
    verloren, und eine Fehlerseite waere als `content` beim Modell gelandet.
    """
    _fake_dns(monkeypatch, {"public.example": [PUBLIC_IP]})
    _install_transport(
        monkeypatch,
        [Hop(status=status, body=b"<html>Not found</html>")],
    )

    with pytest.raises(outbound_http.OutboundHttpError) as exc:
        fetch("https://public.example/missing")
    assert exc.value.status == status


@pytest.mark.parametrize("status", [200, 203, 204])
def test_success_status_is_returned(monkeypatch, status: int):
    _fake_dns(monkeypatch, {"public.example": [PUBLIC_IP]})
    _install_transport(monkeypatch, [Hop(status=status, body=b"<html>ok</html>")])

    result = fetch("https://public.example/page")
    assert result.status == status


# --------------------------------------------------------------------------- #
# Aus dem Review: Userinfo und IPv6-Literale
# --------------------------------------------------------------------------- #

def test_exception_message_does_not_leak_url_credentials(monkeypatch):
    """Der Ablehnungsgrund ist harmlos, die URL nicht.

    Sie steht in der Exception-Message und landet damit in jedem Traceback und
    in jedem generischen Handler, der `str(e)` protokolliert oder
    zurueckgibt — etwa `AgentToolRegistry.execute`.
    """
    with pytest.raises(OutboundRequestBlocked) as exc:
        validate_url("https://user:sup3rgeheim@example.com/x")

    assert "sup3rgeheim" not in str(exc.value)
    assert "user:" not in str(exc.value)
    assert "***@example.com" in str(exc.value)
    # Das Ziel bleibt erkennbar — redigiert wird nur die Userinfo.
    assert "example.com" in str(exc.value)


def test_blocked_url_attribute_is_redacted_too():
    """Auch `exc.url` wird protokolliert, nicht nur die Message."""
    with pytest.raises(OutboundRequestBlocked) as exc:
        validate_url("https://user:sup3rgeheim@example.com/x")
    assert "sup3rgeheim" not in (exc.value.url or "")


@pytest.mark.parametrize(
    "url, expected",
    [
        ("http://[2606:4700::1111]:8080/x", "[2606:4700::1111]:8080"),
        ("http://[2606:4700::1111]/x", "[2606:4700::1111]"),
        ("http://93.184.216.34:8080/x", "93.184.216.34:8080"),
        ("https://example.com/x", "example.com"),
    ],
)
def test_host_header_brackets_ipv6_literals(url: str, expected: str):
    """RFC 7230 verlangt eckige Klammern fuer IP-Literale im Host-Header.

    `urlsplit().hostname` liefert sie ohne — aus `[2001:db8::1]:8080` wuerde
    sonst der ungueltige Header `Host: 2001:db8::1:8080`, und die Gegenstelle
    antwortet mit einem Fehler oder liefert den falschen vHost.
    """
    assert outbound_http._check_shape(url, DEFAULT_POLICY).host_header == expected
