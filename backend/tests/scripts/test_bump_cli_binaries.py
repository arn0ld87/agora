"""Bump der gepinnten CLI-Binaries und Flag-Vertrag des Image-Builds (#1861)."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import bump_cli_binaries as bump  # noqa: E402

DOCKERFILE = """\
ARG CODEX_VERSION=rust-v0.1.0
ARG CODEX_SHA256_AMD64={a}
ARG CODEX_SHA256_ARM64={b}
ARG TARGETARCH
ARG CLAUDE_CODE_VERSION=2.1.1
ARG CLAUDE_CODE_SHA256_AMD64={a}
ARG CLAUDE_CODE_SHA256_ARM64={b}
""".format(a="a" * 64, b="b" * 64)

AMD64_BYTES = b"amd64-binary"
ARM64_BYTES = b"arm64-binary"
AMD64_SHA = hashlib.sha256(AMD64_BYTES).hexdigest()
ARM64_SHA = hashlib.sha256(ARM64_BYTES).hexdigest()


def _claude_source(version: str = "2.1.9", arm64_bytes: bytes = ARM64_BYTES) -> dict[str, bytes]:
    base = bump.CLAUDE_BASE_URL
    manifest = {
        "platforms": {
            "linux-x64": {"checksum": AMD64_SHA},
            "linux-arm64": {"checksum": ARM64_SHA},
        }
    }
    return {
        f"{base}/stable": f"{version}\n".encode(),
        f"{base}/{version}/manifest.json": json.dumps(manifest).encode(),
        f"{base}/{version}/linux-x64/claude": AMD64_BYTES,
        f"{base}/{version}/linux-arm64/claude": arm64_bytes,
    }


def _codex_source(tag: str = "rust-v0.2.0", *, prerelease: bool = False) -> dict[str, bytes]:
    release = {
        "tag_name": tag,
        "prerelease": prerelease,
        "assets": [
            {"name": "codex-x86_64-unknown-linux-musl.tar.gz", "digest": f"sha256:{AMD64_SHA}"},
            {"name": "codex-aarch64-unknown-linux-musl.tar.gz", "digest": f"sha256:{ARM64_SHA}"},
            {"name": "codex-symbols-x86_64-unknown-linux-musl.tar.gz", "digest": "sha256:" + "c" * 64},
        ],
    }
    download = f"{bump.CODEX_DOWNLOAD_URL}/{tag}"
    return {
        f"{bump.CODEX_API_URL}/latest": json.dumps(release).encode(),
        f"{download}/codex-x86_64-unknown-linux-musl.tar.gz": AMD64_BYTES,
        f"{download}/codex-aarch64-unknown-linux-musl.tar.gz": ARM64_BYTES,
    }


def _run(tmp_path: Path, tool: str, source: dict[str, bytes], *extra: str) -> tuple[int, str]:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(DOCKERFILE, encoding="utf-8")
    changelog = tmp_path / "changelog.d"
    changelog.mkdir(exist_ok=True)
    code = bump.main(
        ["--tool", tool, "--dockerfile", str(dockerfile), "--changelog-dir", str(changelog), *extra],
        fetch=source.__getitem__,
    )
    return code, dockerfile.read_text(encoding="utf-8")


def test_claude_bump_replaces_only_the_claude_pin(tmp_path):
    code, text = _run(tmp_path, "claude", _claude_source())

    assert code == 0
    assert bump.read_pin(text, bump.TOOLS["claude"]) == bump.Pin("2.1.9", AMD64_SHA, ARM64_SHA)
    assert bump.read_pin(text, bump.TOOLS["codex"]) == bump.Pin("rust-v0.1.0", "a" * 64, "b" * 64)
    fragment = (tmp_path / "changelog.d" / "1861-bump-claude-cli.md").read_text(encoding="utf-8")
    assert "`2.1.1` auf `2.1.9`" in fragment


def test_codex_bump_takes_the_plain_cli_assets(tmp_path):
    code, text = _run(tmp_path, "codex", _codex_source())

    assert code == 0
    assert bump.read_pin(text, bump.TOOLS["codex"]) == bump.Pin("rust-v0.2.0", AMD64_SHA, ARM64_SHA)
    assert "ARG CLAUDE_CODE_VERSION=2.1.1\n" in text


def test_unchanged_pin_writes_nothing(tmp_path, capsys):
    source = _claude_source()
    _run(tmp_path, "claude", source)
    (tmp_path / "changelog.d" / "1861-bump-claude-cli.md").unlink()
    dockerfile = tmp_path / "Dockerfile"
    before = dockerfile.read_text(encoding="utf-8")
    capsys.readouterr()

    code = bump.main(
        ["--tool", "claude", "--dockerfile", str(dockerfile), "--changelog-dir", str(tmp_path / "changelog.d")],
        fetch=source.__getitem__,
    )

    assert code == 0
    assert dockerfile.read_text(encoding="utf-8") == before
    assert not list((tmp_path / "changelog.d").iterdir())
    assert "changed=false" in capsys.readouterr().out


def test_hash_mismatch_of_arm64_download_aborts_without_writing(tmp_path, capsys):
    code, text = _run(tmp_path, "claude", _claude_source(arm64_bytes=b"manipuliert"))

    assert code == 1
    assert text == DOCKERFILE
    assert "Hash-Abweichung" in capsys.readouterr().err


def test_codex_prerelease_is_rejected(tmp_path):
    code, text = _run(tmp_path, "codex", _codex_source(prerelease=True))

    assert code == 1
    assert text == DOCKERFILE


@pytest.mark.parametrize("version", ["latest", "2.1.9; rm -rf /", "../2.1.9"])
def test_version_input_must_match_the_expected_format(tmp_path, version):
    code, text = _run(tmp_path, "claude", _claude_source(), "--version", version)

    assert code == 1
    assert text == DOCKERFILE


# --- Flag-Vertrag: Image-Build prueft, was die Provider wirklich aufrufen ---

_SHORT_FLAGS = {"-p": "--print"}


def _dockerfile_flags(arg_name: str) -> set[str]:
    text = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    match = re.search(rf'^ARG {arg_name}="([^"]+)"$', text, re.M)
    assert match, f"ARG {arg_name} fehlt im Dockerfile"
    return set(match.group(1).split())


def _command_flags(cmd: list[str]) -> set[str]:
    return {_SHORT_FLAGS.get(part, part) for part in cmd if part.startswith("-") and part != "-"}


def test_dockerfile_checks_every_flag_the_claude_provider_passes(monkeypatch):
    from app.llm.providers import claude_cli

    monkeypatch.setattr(claude_cli, "is_claude_cli_available", lambda: True)
    cmd = claude_cli.build_claude_cli_command(model="claude-opus-5-5")

    assert _command_flags(cmd) == _dockerfile_flags("CLAUDE_CODE_REQUIRED_FLAGS")


def test_dockerfile_checks_every_flag_the_codex_provider_passes(monkeypatch):
    from app.llm.providers import codex_cli

    monkeypatch.setattr(codex_cli, "is_codex_cli_available", lambda: True)
    cmd = codex_cli.build_codex_cli_command(model="gpt-test")

    assert cmd[1] == "exec"
    assert _command_flags(cmd) == _dockerfile_flags("CODEX_REQUIRED_EXEC_FLAGS")
