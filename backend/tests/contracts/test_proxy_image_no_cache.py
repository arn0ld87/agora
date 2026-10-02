"""Die proxy-Stage darf in den Docker-Workflows nicht aus dem Layer-Cache kommen (#1751).

Ihr ``apk upgrade`` ist der einzige Weg, auf dem Alpine-Fixes ins Proxy-Image
gelangen: Auch der aktuelle ``nginx:alpine``-Digest enthält noch
``pcre2`` 10.48-r0. Mit GHA-Layer-Cache blieb das Upgrade-Ergebnis eingefroren,
und der Trivy-Proxy-Scan in ``build-only`` scheiterte an CVE-2026-103111.
"""
from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "docker-image.yml"


def _proxy_build_steps() -> list[dict]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            uses = step.get("uses", "")
            with_ = step.get("with") or {}
            if uses.startswith("docker/build-push-action@") and with_.get("target") == "proxy":
                steps.append(step)
    return steps


def test_every_proxy_build_skips_the_layer_cache_for_the_proxy_stage() -> None:
    steps = _proxy_build_steps()

    assert len(steps) >= 2, "build-only und publish-build bauen beide das Proxy-Image"
    for step in steps:
        filters = str(step["with"].get("no-cache-filters", "")).replace(",", " ").split()
        assert "proxy" in filters, f"{step.get('name')}: no-cache-filters: proxy fehlt"
