"""Regressionstest: nginx darf die Backend-IP nicht beim Config-Load einfrieren.

Defekt vom 13.08.2026: `deploy/nginx/agora.conf` nutzte literale
`proxy_pass http://agora:5001;`-Direktiven. nginx löst einen literalen Hostnamen
genau einmal beim Start auf und cacht die IP prozesslebenslang. Nach einem
Neubau des Backend-Containers wanderte `agora` von 192.168.64.3 auf .4, die alte
IP ging an `agora-redis` — nginx proxyte weiter auf .3:5001 und lieferte für
jeden /api/-Request 502 (`connect() failed (111: Connection refused)`).

Fix: Docker-Resolver 127.0.0.11 + Variablen-`proxy_pass`, damit pro Request neu
aufgelöst wird. Dieser Test hält beide Hälften fest.
"""

import re
from pathlib import Path

import pytest

NGINX_CONF = Path(__file__).resolve().parents[2] / "deploy" / "nginx" / "agora.conf"

# Kommentare zählen nicht als Direktive — sonst schlägt der Test an der
# Fix-Dokumentation im Config-Header selbst an.
_COMMENT = re.compile(r"^\s*#")


def _directive_lines() -> list[str]:
    return [
        line
        for line in NGINX_CONF.read_text(encoding="utf-8").splitlines()
        if not _COMMENT.match(line)
    ]


def test_conf_exists() -> None:
    assert NGINX_CONF.is_file(), f"nginx-Config fehlt: {NGINX_CONF}"


def test_no_literal_backend_hostname_in_proxy_pass() -> None:
    """Literale Upstream-Hostnamen frieren die IP beim Start ein → 502 nach Neubau."""
    offenders = [
        line.strip()
        for line in _directive_lines()
        if "proxy_pass" in line and re.search(r"proxy_pass\s+https?://[a-zA-Z]", line)
    ]
    assert not offenders, (
        "proxy_pass mit literalem Hostnamen gefunden — nginx cacht die IP dann "
        f"prozesslebenslang und liefert nach Container-Neubau 502: {offenders}"
    )


def test_proxy_pass_uses_runtime_variable() -> None:
    """Alle Backend-Routen gehen über die Variable, damit der Resolver greift."""
    proxy_lines = [line.strip() for line in _directive_lines() if "proxy_pass" in line]
    assert proxy_lines, "keine proxy_pass-Direktive gefunden"
    for line in proxy_lines:
        assert "$agora_upstream" in line, f"proxy_pass ohne Variable: {line}"


def test_docker_resolver_configured() -> None:
    """Ohne resolver kann nginx einen Variablen-Upstream gar nicht auflösen."""
    directives = "\n".join(_directive_lines())
    assert re.search(r"^\s*resolver\s+127\.0\.0\.11\b", directives, re.MULTILINE), (
        "resolver 127.0.0.11 (Docker-DNS) fehlt — Variablen-proxy_pass "
        "schlägt sonst zur Laufzeit fehl"
    )
    assert re.search(r"^\s*set\s+\$agora_upstream\s+agora:5001;", directives, re.MULTILINE), (
        "set $agora_upstream agora:5001; fehlt"
    )


@pytest.mark.parametrize("route", ["= /health", "/api/simulation/", "/api/"])
def test_backend_routes_still_present(route: str) -> None:
    """Der Fix darf keine Backend-Route verlieren."""
    assert f"location {route} {{" in NGINX_CONF.read_text(encoding="utf-8")
