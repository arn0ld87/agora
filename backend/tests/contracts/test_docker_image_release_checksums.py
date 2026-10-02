"""Release-Checksummen in `.github/workflows/docker-image.yml` (#1661).

Freigabekriterium fuer 1.0: „Release-Artefakte, Checksummen und SBOM
vorhanden". Bis #1661 erzeugte der Workflow SBOMs und Provenance, aber keine
Checksummen, und nichts davon landete am GitHub Release. Wer ein Release
pruefen wollte, musste die SBOM aus einem Workflow-Artefakt ziehen, das nach
90 Tagen verfaellt.

Seitdem gilt:

- `publish` schreibt die Digests beider ausgelieferten Images (agora,
  agora-proxy) in `agora-image-digests.txt`, erzeugt fuer beide Images eine
  SBOM und bildet `SHA256SUMS` ueber alle drei Dateien.
- Ein eigener Job `release-assets` haengt die Dateien nur bei `v*`-Tags an
  das GitHub Release. Er ist der einzige Job mit `contents: write`; der
  Build- und Push-Pfad bleibt bei `contents: read`.
- Vor dem Anhaengen prueft `release-assets` die Checksummen erneut, damit
  eine beim Artefakt-Transfer veraenderte Datei nicht als Release-Asset
  erscheint.

Rohtext-Parser aus `test_docker_image_artifact_gate` (keine YAML-Dependency,
siehe dortiger Docstring).
"""

from __future__ import annotations

from tests.contracts.test_docker_image_artifact_gate import (
    WORKFLOW_PATH,
    _job_block,
    _normalize_condition,
    _scalar_value,
    _step_block,
    _step_names,
)

RELEASE_JOB = "release-assets"
SUMS_FILE = "SHA256SUMS"
DIGEST_FILE = "agora-image-digests.txt"
HASHED_FILES = ("agora-image.spdx.json", "agora-proxy-image.spdx.json", DIGEST_FILE)
RELEASE_FILES = (SUMS_FILE, *HASHED_FILES)

CHECKSUM_STEP = "Release-Checksummen erzeugen (SHA256SUMS)"
ARTIFACT_STEP = "Release-Artefakte hochladen"
VERIFY_STEP = "Checksummen pruefen"
ATTACH_STEP = "An GitHub Release anhaengen"


def _joined(lines: list[str]) -> str:
    return "\n".join(lines)


def test_proxy_image_gets_its_own_sbom() -> None:
    """agora-proxy wird oeffentlich publiziert, also braucht es eine SBOM."""
    step = _joined(_step_block(_job_block("publish"), "Generate GHCR proxy SBOM"))

    assert "agora-proxy@${{ steps.build_proxy.outputs.digest }}" in step
    assert "output-file: agora-proxy-image.spdx.json" in step
    assert "format: spdx-json" in step


def test_digest_file_records_both_published_images() -> None:
    step = _joined(_step_block(_job_block("publish"), CHECKSUM_STEP))

    assert "steps.build_ghcr.outputs.digest" in step
    assert "steps.build_proxy.outputs.digest" in step
    assert DIGEST_FILE in step


def test_sha256sums_cover_every_release_file_and_self_check() -> None:
    step = _joined(_step_block(_job_block("publish"), CHECKSUM_STEP))
    hash_line = next(line for line in step.splitlines() if f"> {SUMS_FILE}" in line)

    assert hash_line.strip().startswith("sha256sum ")
    for name in HASHED_FILES:
        assert name in hash_line, f"{name} fehlt in {SUMS_FILE}"
    assert f"sha256sum -c {SUMS_FILE}" in step


def test_release_files_are_kept_as_workflow_artifact() -> None:
    """Auch ohne Tag (release/**, rc/**, Dispatch) bleiben die Dateien abrufbar."""
    step = _step_block(_job_block("publish"), ARTIFACT_STEP)
    text = _joined(step)

    assert "name: agora-release-artifacts" in text
    assert "if-no-files-found: error" in text
    for name in RELEASE_FILES:
        assert name in text, f"{name} fehlt im Artefakt-Upload"
    assert not any(line.strip().startswith("if:") for line in step)


def test_release_assets_runs_only_on_tags_after_successful_publish() -> None:
    """`always()` haelt den Break-glass-Pfad offen (Smoke rot, force_publish).

    Ohne `always()` wuerde ein roter Smoke in der Kette den Job auch dann
    ueberspringen, wenn `publish` per force_publish erfolgreich war.
    """
    block = _job_block(RELEASE_JOB)
    condition = _normalize_condition(_scalar_value(block, "if"))

    assert "needs: [publish]" in _joined(block)
    assert condition == (
        "always() && needs.publish.result == 'success' "
        "&& startsWith(github.ref, 'refs/tags/v')"
    ), condition


def test_contents_write_is_confined_to_release_assets() -> None:
    publish = _joined(_job_block("publish"))
    release = _joined(_job_block(RELEASE_JOB))

    assert "contents: read" in publish
    assert "contents: write" not in publish
    assert "contents: write" in release
    assert WORKFLOW_PATH.read_text(encoding="utf-8").count("contents: write") == 1


def test_release_assets_verifies_before_attaching() -> None:
    block = _job_block(RELEASE_JOB)
    names = _step_names(block)
    verify = _joined(_step_block(block, VERIFY_STEP))
    attach = _joined(_step_block(block, ATTACH_STEP))

    assert names.index(VERIFY_STEP) < names.index(ATTACH_STEP)
    assert f"sha256sum -c {SUMS_FILE}" in verify
    assert "gh release upload" in attach
    assert "--clobber" in attach
    for name in RELEASE_FILES:
        assert name in attach, f"{name} wird nicht ans Release gehaengt"


def test_tag_name_reaches_the_shell_only_via_env() -> None:
    """Kein `${{ github.ref_name }}` im run:-Block (Template-Injection)."""
    attach = _step_block(_job_block(RELEASE_JOB), ATTACH_STEP)
    run_index = next(i for i, line in enumerate(attach) if line.strip().startswith("run:"))

    assert "TAG: ${{ github.ref_name }}" in _joined(attach[:run_index])
    assert "${{" not in _joined(attach[run_index:])


def test_release_assets_egress_allows_asset_uploads() -> None:
    step = _joined(_step_block(_job_block(RELEASE_JOB), "Harden Runner"))

    assert "egress-policy: block" in step
    for endpoint in ("api.github.com:443", "uploads.github.com:443"):
        assert endpoint in step, f"{endpoint} fehlt in der Egress-Allowlist"
