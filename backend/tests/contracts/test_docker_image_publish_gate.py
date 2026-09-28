"""Publish-Invarianten fuer `.github/workflows/docker-image.yml` (#1708).

Bis #1708 erreichte der `publish`-Job GHCR praktisch nie. Er hing am
`prod-proxy-smoke`, und der baute das nginx-Image im Job selbst — hinter
einer Egress-Allowlist ohne `dl-cdn.alpinelinux.org`, `deb.debian.org` und
`registry.npmjs.org`. Beim Tag v0.9.6 (Run 35517075897) lief der Build so
bis zum 30-Minuten-Timeout, `publish` wurde uebersprungen. armserver baute
deshalb weiter lokal und scheiterte dort unter Last.

Seitdem gilt:

- `build-only` baut beide ausgelieferten Images (agora, agora-proxy); der
  Smoke startet sie mit `--no-build` und kann keinen Build mehr anstossen.
- `publish` laeuft auf main-Pushes ohne Smoke, aber nur nach gruenem
  `build-only` und nur unter `sha-<7>`/`edge`. `latest` bleibt an einen
  Release-Tag gebunden, der den Smoke passiert hat.
- Prod- und Proxy-Build schreiben in getrennte GHA-Cache-Scopes.

Rohtext-Parser aus `test_docker_image_artifact_gate` (keine YAML-Dependency,
siehe dortiger Docstring).
"""

from __future__ import annotations

from tests.contracts.test_docker_image_artifact_gate import (
    _job_block,
    _normalize_condition,
    _scalar_value,
    _step_block,
)

GHCR_METADATA_STEPS = ("Extract GHCR metadata", "Extract GHCR proxy metadata")


def _joined(lines: list[str]) -> str:
    return "\n".join(lines)


def test_smoke_starts_prebuilt_images_without_building() -> None:
    """Der Smoke darf keinen Compose-Build mehr ausloesen.

    Seine Egress-Allowlist laesst die Paketquellen fuer den Proxy-Build nicht
    durch; ein impliziter Build haengt bis zum Job-Timeout, statt zu scheitern.
    """
    step = _step_block(_job_block("prod-proxy-smoke"), "Compose-Stack starten")

    assert "up -d --no-build" in _joined(step)


def test_smoke_loads_both_images_from_the_artifact() -> None:
    smoke = _joined(_step_block(_job_block("prod-proxy-smoke"), "Images laden und für Compose umtaggen"))
    upload = _joined(_step_block(_job_block("build-only"), "Image-Artefakt hochladen"))

    for tar in ("/tmp/image.tar", "/tmp/proxy-image.tar"):
        assert tar in upload, f"{tar} fehlt im Artefakt-Upload von build-only"
        assert f"docker load -i {tar}" in smoke, f"{tar} wird im Smoke nicht geladen"


def test_proxy_image_is_built_with_default_args_in_build_only() -> None:
    """Das oeffentlich publizierte Proxy-Image traegt kein Build-Time-Token."""
    step = _joined(_step_block(_job_block("build-only"), "Build proxy image (kein Push)"))

    assert "target: proxy" in step
    assert "build-args" not in step
    assert "ALLOW_BUILD_TIME_TOKEN" not in step


def test_publish_requires_green_build_only() -> None:
    block = _job_block("publish")
    condition = _normalize_condition(_scalar_value(block, "if"))

    assert "needs: [build-only, prod-proxy-smoke]" in _joined(block)
    assert condition.startswith("always() && needs.build-only.result == 'success' && ("), condition


def test_publish_without_smoke_only_on_main_push() -> None:
    """Ein uebersprungener Smoke oeffnet publish ausschliesslich fuer main-Pushes.

    PRs skippen den Smoke ebenfalls; ohne die Event-/Ref-Bindung wuerde jeder
    PR ein Image publizieren.
    """
    condition = _normalize_condition(_scalar_value(_job_block("publish"), "if"))

    assert (
        "(github.event_name == 'push' && github.ref == 'refs/heads/main' "
        "&& needs.prod-proxy-smoke.result == 'skipped')"
    ) in condition
    assert condition.count("'skipped'") == 1


def test_latest_is_bound_to_release_tags_for_both_images() -> None:
    """`latest` bedeutet 'letztes Release mit gruenem Smoke', nie main."""
    block = _job_block("publish")

    for step_name in GHCR_METADATA_STEPS:
        tags = _joined(_step_block(block, step_name))
        assert "type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/v') }}" in tags
        assert "value=latest,enable={{is_default_branch}}" not in tags
        assert "type=sha,prefix=sha-" in tags
        assert "type=raw,value=edge,enable={{is_default_branch}}" in tags


def test_proxy_publish_is_attested() -> None:
    block = _job_block("publish")
    attest = _joined(_step_block(block, "Generate GHCR proxy build provenance"))

    assert "agora-proxy" in attest
    assert "steps.build_proxy.outputs.digest" in attest


def test_prod_and_proxy_use_separate_cache_scopes() -> None:
    for job in ("build-only", "publish"):
        text = _joined(_job_block(job))
        assert "cache-from: type=gha\n" not in text + "\n", f"{job}: GHA-Cache ohne scope"
        assert "scope=prod" in text
        assert "scope=proxy" in text
