"""Vertrag: der Prod-Proxy-Smoke macht jeden schreibenden Bind-Mount beschreibbar.

Der Smoke-Job in ``docker-image.yml`` läuft nur auf Tags, RC-Branches und
``workflow_dispatch``. Auf dem GitHub-Runner gehört der Checkout uid 1001, der
Prod-Container läuft als uid 1000. Jeder ``./backend/<dir>``-Bind-Mount aus
``docker-compose.yml`` braucht deshalb vor ``compose up`` eine ACL für uid 1000.

Beim Tag ``v0.9.7`` fehlte ``backend/data``: ``verify-deploy.sh`` meldete
„backend/data im Container schreibbar“ als FAIL, und Publish sowie
Release-Assets wurden übersprungen. Ein neuer Bind-Mount ohne passende ACL
fällt erst beim nächsten Tag auf; dieser Test hält ihn schon auf dem PR auf.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]

# Bind-Mounts, die der Smoke bewusst nicht vorbereitet: der HuggingFace-Cache
# wird im Smoke nicht beschrieben (keine Simulation) und ist im Repo per
# ``.gitkeep`` angelegt.
_NOT_WRITTEN_IN_SMOKE = {"backend/.cache/huggingface"}


def _backend_bind_sources() -> set[str]:
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    sources: set[str] = set()
    for volume in compose["services"]["agora"].get("volumes", []):
        if not isinstance(volume, str):
            continue
        parts = volume.split(":")
        source = parts[0]
        read_only = len(parts) > 2 and "ro" in parts[2].split(",")
        if source.startswith("./backend/") and not read_only:
            sources.add(source.removeprefix("./"))
    return sources


def _smoke_prepare_step() -> str:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "docker-image.yml").read_text(encoding="utf-8")
    )
    for step in workflow["jobs"]["prod-proxy-smoke"]["steps"]:
        if step.get("name", "").startswith("Bind-Mount-Verzeichnisse"):
            return step["run"]
    raise AssertionError("Schritt 'Bind-Mount-Verzeichnisse …' fehlt im prod-proxy-smoke-Job")


def test_every_writable_backend_bind_mount_gets_uid_1000_acl() -> None:
    run = _smoke_prepare_step()
    setfacl_lines = [line for line in run.splitlines() if line.strip().startswith("setfacl")]
    assert setfacl_lines, "kein setfacl-Aufruf im Vorbereitungsschritt"
    granted = set(" ".join(setfacl_lines).split())

    expected = _backend_bind_sources() - _NOT_WRITTEN_IN_SMOKE
    assert {"backend/uploads", "backend/data", "backend/instance"} <= expected, expected
    missing = sorted(expected - granted)
    assert not missing, f"Bind-Mounts ohne ACL für uid 1000 im Smoke: {missing}"
