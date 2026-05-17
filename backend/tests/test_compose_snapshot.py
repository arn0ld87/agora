"""Snapshot-Checks für docker-compose Dev/Prod-Trennung (Slice 2).

Alle Tests skippen sauber, wenn kein Docker/Docker-Compose im Pfad ist.
"""

import json
import os
import shutil
import subprocess

import pytest


def _has_docker():
    return shutil.which("docker") is not None


def _compose_config(*extra_files: str):
    """Run `docker compose config` from repo root and return parsed JSON."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cmd = ["docker", "compose", "-f", "docker-compose.yml"]
    for f in extra_files:
        cmd.extend(["-f", f])
    cmd.extend(["config", "--format", "json"])

    # Provide dummy env for interpolation so it doesn't fail on missing required vars
    env = os.environ.copy()
    env.setdefault("NEO4J_PASSWORD", "dummy")
    env.setdefault("AGORA_AUTH_TOKEN", "dummy")

    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=repo_root, timeout=30, env=env
    )
    if result.returncode != 0:
        pytest.skip(f"docker compose config failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


@pytest.mark.skipif(not _has_docker(), reason="docker not available")
class TestComposeDevDefault:
    """Default `docker compose config` soll Dev-Stage + Loopback-Ports liefern."""

    def test_target_is_dev(self):
        cfg = _compose_config()
        agora = cfg["services"]["agora"]
        build = agora.get("build", {})
        assert build.get("target") == "dev", f"expected target=dev, got {build}"

    def test_frontend_port_loopback(self):
        cfg = _compose_config()
        ports = cfg["services"]["agora"].get("ports", [])
        frontend = [p for p in ports if "5173" in str(p)]
        assert frontend, "frontend port 5173 not found"
        assert any("127.0.0.1" in str(p) for p in frontend), \
            f"frontend not bound to 127.0.0.1: {frontend}"

    def test_backend_port_loopback(self):
        cfg = _compose_config()
        ports = cfg["services"]["agora"].get("ports", [])
        backend = [p for p in ports if "5001" in str(p)]
        assert backend, "backend port 5001 not found"
        assert any("127.0.0.1" in str(p) for p in backend), \
            f"backend not bound to 127.0.0.1: {backend}"

    def test_neo4j_ports_loopback(self):
        cfg = _compose_config()
        ports = cfg["services"]["neo4j"].get("ports", [])
        assert ports, "neo4j has no ports"
        for p in ports:
            assert "127.0.0.1" in str(p), f"neo4j port not bound to 127.0.0.1: {p}"


@pytest.mark.skipif(not _has_docker(), reason="docker not available")
class TestComposeProdOverride:
    """`docker compose -f docker-compose.yml -f docker-compose.prod.yml config`
    soll Vite-Frontend und Neo4j-Host-Ports entfernen."""

    def test_no_frontend_port_in_prod(self):
        cfg = _compose_config("docker-compose.prod.yml")
        ports = cfg["services"]["agora"].get("ports", [])
        frontend = [p for p in ports if "5173" in str(p)]
        assert not frontend, f"frontend port 5173 should not exist in prod: {frontend}"

    def test_no_neo4j_host_ports_in_prod(self):
        cfg = _compose_config("docker-compose.prod.yml")
        ports = cfg["services"]["neo4j"].get("ports", [])
        assert not ports, f"neo4j should have no host ports in prod: {ports}"

    def test_backend_port_loopback_in_prod(self):
        cfg = _compose_config("docker-compose.prod.yml")
        ports = cfg["services"]["agora"].get("ports", [])
        backend = [p for p in ports if "5001" in str(p)]
        assert backend, "backend port 5001 not found in prod"
        assert any("127.0.0.1" in str(p) for p in backend), \
            f"backend not bound to 127.0.0.1 in prod: {backend}"
