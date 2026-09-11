"""
Guarded outbound HTTP for agent-controlled URLs (SSRF defense).

Every fetch whose URL originates from an LLM, an agent tool call or any other
untrusted source MUST go through :func:`fetch` (or at minimum
:func:`validate_url`). Scattering the checks across call sites is how the
``agent_tools.web_fetch`` hole happened in the first place, so this module is
the single source of truth.

The guard has four layers, all of which are required:

1. **URL shape** — only ``http``/``https``, no embedded credentials, no
   host-less URLs, no Docker/cloud-internal special names.
2. **Address classes** — every address the hostname resolves to must be
   public. A single private answer rejects the whole URL, which is what makes
   DNS round-robin tricks useless.
3. **Connection pinning** — we connect to the *validated* IP literal instead of
   handing the hostname back to the socket layer. Without this the resolver can
   return a public address for the check and a private one microseconds later
   for the actual connection (DNS rebinding / TOCTOU). The original hostname is
   still used for the ``Host`` header, TLS SNI and certificate verification, so
   pinning does not weaken TLS.
4. **Per-hop redirect validation** — redirects are followed manually so that
   every ``Location`` runs through layers 1-3 again. ``allow_redirects=True``
   would let a public URL bounce straight into the metadata service.

Response bodies are streamed and truncated at a byte budget so a hostile or
merely huge target cannot exhaust memory.

Note: this path deliberately does not honour ``HTTP(S)_PROXY``. Pinning and a
proxy are mutually exclusive (the proxy does its own resolution), and silently
dropping the pin would defeat layer 3.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urljoin, urlsplit

import urllib3

from ..utils.logger import get_logger

logger = get_logger('agora.security.outbound_http')

#: Either IP version. ``ipaddress._BaseAddress`` is private and does not
#: expose the ``is_*`` classification flags to type checkers.
type IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

_DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; AgoraAgent/1.0)"

#: Cloud metadata endpoints. Most are already caught by the link-local check;
#: listing them explicitly is defense-in-depth and produces a clearer reason.
_METADATA_IPS: frozenset[str] = frozenset({
    "169.254.169.254",   # AWS / Azure / GCP / DigitalOcean
    "fd00:ec2::254",     # AWS IMDSv2 over IPv6
    "100.100.100.200",   # Alibaba Cloud
})

#: Hostnames that resolve to infrastructure rather than the public web. These
#: are blocked by name because in some runtimes they resolve to an address that
#: looks public (or do not resolve at all on the checking host).
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({
    "metadata.google.internal",
    "metadata",
    "instance-data",
    "host.docker.internal",
    "gateway.docker.internal",
    "kubernetes.default.svc",
    "kubernetes.default",
    "kubernetes",
})

#: Suffixes reserved for local/internal name resolution.
_BLOCKED_HOST_SUFFIXES: tuple[str, ...] = (
    ".localhost",
    ".local",
    ".internal",
    ".intranet",
    ".svc",
    ".svc.cluster.local",
)


class OutboundHttpError(Exception):
    """Die Gegenstelle hat mit einem Fehlerstatus geantwortet.

    Bewusst getrennt von :class:`OutboundRequestBlocked`: ein 404 ist keine
    Richtlinienentscheidung von uns, sondern eine Auskunft der Gegenstelle.
    Beides in einen Topf zu werfen wuerde dem Agenten "blockiert" melden, wo
    "Seite existiert nicht" die Wahrheit ist.
    """

    def __init__(self, status: int, url: str | None = None) -> None:
        self.status = status
        self.url = url
        super().__init__(f"HTTP {status}")


class OutboundRequestBlocked(Exception):
    """Raised when the outbound policy rejects a URL or a redirect hop."""

    def __init__(self, reason: str, url: str | None = None) -> None:
        self.reason = reason
        self.url = url
        super().__init__(reason if not url else f"{reason} ({url})")


@dataclass(frozen=True)
class OutboundHttpPolicy:
    """Limits applied to a guarded outbound request."""

    allowed_schemes: frozenset[str] = frozenset({"http", "https"})
    max_redirects: int = 3
    max_response_bytes: int = 1_000_000
    connect_timeout: float = 5.0
    read_timeout: float = 10.0
    allowed_content_types: tuple[str, ...] = ("text/html", "text/plain")
    user_agent: str = _DEFAULT_USER_AGENT
    #: Hostnames exempt from :data:`_BLOCKED_HOSTNAMES` / suffix blocking.
    #: Addresses are still checked — this never unlocks a private IP.
    allowed_hostnames: frozenset[str] = field(default_factory=frozenset)


DEFAULT_POLICY = OutboundHttpPolicy()


@dataclass(frozen=True)
class ResolvedTarget:
    """A URL that passed validation, together with the address to connect to."""

    url: str
    scheme: str
    host: str
    port: int
    ip: str
    #: ``path?query`` as sent on the wire.
    request_target: str
    #: Value for the ``Host`` header (includes the port when non-default).
    host_header: str


@dataclass(frozen=True)
class FetchResult:
    """Outcome of a successful guarded fetch."""

    url: str
    status: int
    content_type: str
    text: str
    #: True when the body hit ``max_response_bytes`` and was cut short.
    truncated: bool


# --------------------------------------------------------------------------- #
# Address classification
# --------------------------------------------------------------------------- #

def _normalize_ip(raw: str) -> IpAddress | None:
    """Parse an address, stripping IPv6 zone ids and unmapping v4-in-v6.

    ``::ffff:127.0.0.1`` is a loopback address wearing an IPv6 costume; without
    unmapping it, the IPv4 checks below would never see it.
    """
    try:
        ip = ipaddress.ip_address(raw.split("%")[0])
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None:
            return mapped
        if ip.sixtofour is not None:
            return ip.sixtofour
    return ip


def _reject_reason_for_ip(ip: IpAddress) -> str | None:
    """Return a rejection reason, or ``None`` when the address may be used."""
    if str(ip) in _METADATA_IPS:
        return "metadata endpoint blocked"
    # Order matters only for the reason text: several of these overlap
    # (0.0.0.0 is both unspecified and "private" to ipaddress), so the most
    # specific label is checked first.
    if ip.is_unspecified:
        return f"host resolves to non-public address {ip} (unspecified)"
    if ip.is_loopback:
        return f"host resolves to non-public address {ip} (loopback)"
    if ip.is_link_local:
        return f"host resolves to non-public address {ip} (link-local)"
    if ip.is_multicast:
        return f"host resolves to non-public address {ip} (multicast)"
    if ip.is_reserved:
        return f"host resolves to non-public address {ip} (reserved)"
    if ip.is_private:
        return f"host resolves to non-public address {ip} (private)"
    # Catch-all for special-purpose ranges the named flags miss (CGNAT,
    # benchmarking, documentation ranges, ...).
    if not ip.is_global:
        return f"host resolves to non-public address {ip} (non-global)"
    return None


def _hostname_is_blocked(host: str, policy: OutboundHttpPolicy) -> str | None:
    """Rejection reason for an infrastructure hostname, or ``None``.

    Checked before resolution: in some runtimes these names resolve to an
    address that looks public, so the address check alone would let them
    through.
    """
    lowered = host.lower().rstrip(".")
    if lowered in policy.allowed_hostnames:
        return None
    if lowered in _BLOCKED_HOSTNAMES:
        return f"internal hostname blocked: {lowered}"
    for suffix in _BLOCKED_HOST_SUFFIXES:
        if lowered.endswith(suffix):
            return f"internal hostname suffix blocked: {suffix}"
    return None


def _resolve(host: str) -> list[str]:
    """Resolve ``host`` to raw address strings. Raises on failure."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class _UrlShape:
    """The parts of a URL that survived the shape checks."""

    scheme: str
    host: str
    port: int
    request_target: str
    host_header: str


def _check_shape(url: str, policy: OutboundHttpPolicy) -> _UrlShape:
    """Layer 1: everything decidable from the URL text alone."""
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise OutboundRequestBlocked(f"unparsable URL: {exc}", url) from exc

    if parts.scheme not in policy.allowed_schemes:
        raise OutboundRequestBlocked(f"unsupported scheme {parts.scheme!r}", url)

    # Credentials in the URL are both a leak risk in logs and a classic way to
    # smuggle a different authority past naive parsers.
    if parts.username or parts.password:
        raise OutboundRequestBlocked("URL must not contain credentials", url)

    try:
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise OutboundRequestBlocked(f"invalid host or port: {exc}", url) from exc

    if not host:
        raise OutboundRequestBlocked("missing host", url)

    blocked = _hostname_is_blocked(host, policy)
    if blocked:
        raise OutboundRequestBlocked(blocked, url)

    default_port = 443 if parts.scheme == "https" else 80
    port = port or default_port

    request_target = parts.path or "/"
    if parts.query:
        request_target = f"{request_target}?{parts.query}"

    return _UrlShape(
        scheme=parts.scheme,
        host=host,
        port=port,
        request_target=request_target,
        host_header=host if port == default_port else f"{host}:{port}",
    )


def _public_addresses_for(host: str, url: str) -> list[str]:
    """Layer 2: resolve ``host`` and require every answer to be public.

    A hostname with even one non-public answer is rejected outright — a
    round-robin record mixing a public and a private address would otherwise
    be a reliable bypass.
    """
    # A literal IP in the URL never reaches the resolver, so check it directly.
    literal = _normalize_ip(host)
    if literal is not None:
        reason = _reject_reason_for_ip(literal)
        if reason:
            raise OutboundRequestBlocked(reason, url)
        return [host]

    try:
        resolved = _resolve(host)
    except socket.gaierror as exc:
        raise OutboundRequestBlocked(f"dns resolution failed: {exc}", url) from exc
    if not resolved:
        raise OutboundRequestBlocked("dns resolution returned no addresses", url)

    addresses: list[str] = []
    for raw in resolved:
        ip = _normalize_ip(raw)
        if ip is None:
            continue
        reason = _reject_reason_for_ip(ip)
        if reason:
            raise OutboundRequestBlocked(reason, url)
        addresses.append(raw.split("%")[0])

    if not addresses:
        raise OutboundRequestBlocked("no usable address for host", url)
    return addresses


def validate_url(url: str, policy: OutboundHttpPolicy | None = None) -> ResolvedTarget:
    """Validate ``url`` and resolve it to a single connectable public address.

    Raises:
        OutboundRequestBlocked: if any layer of the policy rejects the URL.
    """
    policy = policy or DEFAULT_POLICY
    shape = _check_shape(url, policy)
    addresses = _public_addresses_for(shape.host, url)

    return ResolvedTarget(
        url=url,
        scheme=shape.scheme,
        host=shape.host,
        port=shape.port,
        ip=addresses[0],
        request_target=shape.request_target,
        host_header=shape.host_header,
    )


def is_public_url(url: str, policy: OutboundHttpPolicy | None = None) -> tuple[bool, str]:
    """Backwards-compatible boolean form of :func:`validate_url`."""
    try:
        validate_url(url, policy)
    except OutboundRequestBlocked as exc:
        return False, exc.reason
    return True, ""


# --------------------------------------------------------------------------- #
# Guarded fetch
# --------------------------------------------------------------------------- #

def _open_pinned_pool(target: ResolvedTarget, policy: OutboundHttpPolicy):
    """Build a connection pool bound to the validated IP.

    ``host`` is the IP so urllib3 connects there directly, while
    ``server_hostname``/``assert_hostname`` keep SNI and certificate
    verification anchored to the real hostname.
    """
    timeout = urllib3.Timeout(connect=policy.connect_timeout, read=policy.read_timeout)
    if target.scheme == "https":
        return urllib3.HTTPSConnectionPool(
            host=target.ip,
            port=target.port,
            timeout=timeout,
            retries=False,
            cert_reqs="CERT_REQUIRED",
            assert_hostname=target.host,
            # `server_hostname` ist KEIN benannter Pool-Parameter, sondern
            # wandert ueber `**conn_kw` in die Connection. Als
            # `conn_kw={...}` uebergeben wuerde es dort verschachtelt
            # ankommen und `HTTPSConnection.__init__` mit TypeError brechen.
            server_hostname=target.host,
        )
    return urllib3.HTTPConnectionPool(
        host=target.ip,
        port=target.port,
        timeout=timeout,
        retries=False,
    )


def _read_capped(response, policy: OutboundHttpPolicy) -> tuple[bytes, bool]:
    """Stream the body, stopping once the byte budget is exhausted."""
    chunks: list[bytes] = []
    total = 0
    truncated = False
    for chunk in response.stream(8192, decode_content=True):
        if not chunk:
            continue
        chunks.append(chunk)
        total += len(chunk)
        if total >= policy.max_response_bytes:
            truncated = True
            break
    body = b"".join(chunks)[: policy.max_response_bytes]
    return body, truncated


def _decode(body: bytes, content_type: str) -> str:
    """Decode a body using the declared charset, falling back to UTF-8.

    Never raises: a hostile or broken target must not be able to kill the
    fetch with an unknown or malformed charset, so undecodable bytes are
    replaced rather than propagated.
    """
    charset = "utf-8"
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            charset = part.split("=", 1)[1].strip().strip('"\'') or "utf-8"
            break
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _content_type_allowed(content_type: str, allowed: Iterable[str]) -> bool:
    """Compare the bare media type, ignoring parameters like ``charset``."""
    base = content_type.split(";", 1)[0].strip().lower()
    return any(base == entry.lower() for entry in allowed)


def fetch(url: str, policy: OutboundHttpPolicy | None = None) -> FetchResult:
    """Fetch ``url`` under the outbound policy, following redirects safely.

    Raises:
        OutboundRequestBlocked: if the URL, any redirect hop, or the response
            content type violates the policy.
        urllib3.exceptions.HTTPError: on transport failures.
    """
    policy = policy or DEFAULT_POLICY
    current = url

    for _hop in range(policy.max_redirects + 1):
        target = validate_url(current, policy)
        pool = _open_pinned_pool(target, policy)
        try:
            response = pool.urlopen(
                "GET",
                target.request_target,
                headers={
                    "Host": target.host_header,
                    "User-Agent": policy.user_agent,
                    "Accept-Encoding": "gzip, deflate",
                },
                redirect=False,
                assert_same_host=False,
                preload_content=False,
                decode_content=True,
            )
            try:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        raise OutboundRequestBlocked(
                            f"redirect {response.status} without Location", current
                        )
                    # Resolve relative redirects against the hop we just made,
                    # then loop so the new URL is fully revalidated.
                    current = urljoin(current, location)
                    continue

                # Fehlerstatus vor allem anderen: die HTML-Fehlerseite eines
                # 404 ist kein Seiteninhalt. Ohne diese Pruefung landete sie
                # als "content" beim Modell — der Vorgaengercode hatte dafuer
                # `raise_for_status()`, das beim Umbau verloren ging.
                if response.status >= 400:
                    raise OutboundHttpError(response.status, current)

                content_type = response.headers.get("Content-Type", "")
                if not _content_type_allowed(content_type, policy.allowed_content_types):
                    raise OutboundRequestBlocked(
                        f"unsupported content type: {content_type or 'unknown'}", current
                    )

                body, truncated = _read_capped(response, policy)
                return FetchResult(
                    url=current,
                    status=response.status,
                    content_type=content_type,
                    text=_decode(body, content_type),
                    truncated=truncated,
                )
            finally:
                response.release_conn()
        finally:
            pool.close()

    raise OutboundRequestBlocked(
        f"too many redirects (limit {policy.max_redirects})", url
    )
