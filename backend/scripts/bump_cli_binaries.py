"""Hebt die gepinnten CLI-Provider-Binaries im Dockerfile an (#1861).

Das Dockerfile pinnt ``claude`` und ``codex`` je mit Version und zwei SHA256-
Werten (amd64, arm64). Dependabot erfasst solche ``ARG``-Downloads nicht.
Dieses Skript ermittelt die Zielversion, liest die Hashes aus der
Herstellerquelle, prueft sie gegen die tatsaechlich ausgelieferten Dateien
und ersetzt die drei ``ARG``-Zeilen. Aufrufer ist
``.github/workflows/cli-binaries-bump.yml``.

Quellen:
    claude: ``downloads.claude.ai/claude-code-releases/<kanal>`` (Klartext-
            Version) und ``.../<version>/manifest.json``.
    codex:  GitHub-Releases-API von ``openai/codex`` (``digest`` je Asset).

Aufruf:
    uv run python scripts/bump_cli_binaries.py --tool claude
    uv run python scripts/bump_cli_binaries.py --tool codex --version rust-v0.162.1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_BASE_URL = "https://downloads.claude.ai/claude-code-releases"
CLAUDE_CHANNEL = "stable"
CODEX_API_URL = "https://api.github.com/repos/openai/codex/releases"
CODEX_DOWNLOAD_URL = "https://github.com/openai/codex/releases/download"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CLAUDE_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_CODEX_VERSION_RE = re.compile(r"^rust-v\d+\.\d+\.\d+$")

Fetch = Callable[[str], bytes]


class BumpError(RuntimeError):
    """Zielversion oder Hashes liessen sich nicht verlaesslich bestimmen."""


@dataclass(frozen=True)
class Pin:
    version: str
    sha256_amd64: str
    sha256_arm64: str


@dataclass(frozen=True)
class Tool:
    label: str
    arg_prefix: str
    version_re: re.Pattern[str]


TOOLS = {
    "claude": Tool("Claude Code", "CLAUDE_CODE", _CLAUDE_VERSION_RE),
    "codex": Tool("Codex", "CODEX", _CODEX_VERSION_RE),
}


def http_get(url: str) -> bytes:
    headers = {"User-Agent": "agora-cli-bump"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 - feste https-Quellen
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        return response.read()


def _checked_sha(value: object, where: str) -> str:
    sha = str(value).removeprefix("sha256:")
    if not _SHA256_RE.match(sha):
        raise BumpError(f"{where}: kein SHA256-Wert ({value!r})")
    return sha


def _checked_version(tool: Tool, version: str) -> str:
    version = version.strip()
    if not tool.version_re.match(version):
        raise BumpError(f"{tool.label}: unerwartetes Versionsformat {version!r}")
    return version


def resolve_claude(fetch: Fetch, version: str | None) -> tuple[Pin, dict[str, str]]:
    tool = TOOLS["claude"]
    if version is None:
        version = fetch(f"{CLAUDE_BASE_URL}/{CLAUDE_CHANNEL}").decode()
    version = _checked_version(tool, version)
    manifest = json.loads(fetch(f"{CLAUDE_BASE_URL}/{version}/manifest.json"))
    platforms = manifest.get("platforms", {})
    try:
        amd64 = _checked_sha(platforms["linux-x64"]["checksum"], "manifest linux-x64")
        arm64 = _checked_sha(platforms["linux-arm64"]["checksum"], "manifest linux-arm64")
    except (KeyError, TypeError) as exc:
        raise BumpError(f"manifest.json von {version} ohne Linux-Checksummen") from exc
    urls = {
        amd64: f"{CLAUDE_BASE_URL}/{version}/linux-x64/claude",
        arm64: f"{CLAUDE_BASE_URL}/{version}/linux-arm64/claude",
    }
    return Pin(version, amd64, arm64), urls


def resolve_codex(fetch: Fetch, version: str | None) -> tuple[Pin, dict[str, str]]:
    tool = TOOLS["codex"]
    # ``releases/latest`` liefert laut GitHub-API nie ein Prerelease oder einen Draft.
    endpoint = "latest" if version is None else f"tags/{_checked_version(tool, version)}"
    release = json.loads(fetch(f"{CODEX_API_URL}/{endpoint}"))
    if release.get("prerelease") or release.get("draft"):
        raise BumpError(f"Codex-Release {release.get('tag_name')!r} ist ein Prerelease/Draft")
    version = _checked_version(tool, str(release.get("tag_name", "")))
    digests = {asset["name"]: asset.get("digest") for asset in release.get("assets", [])}
    names = {
        "amd64": "codex-x86_64-unknown-linux-musl.tar.gz",
        "arm64": "codex-aarch64-unknown-linux-musl.tar.gz",
    }
    for name in names.values():
        if not digests.get(name):
            raise BumpError(f"Codex-Release {version} ohne Digest fuer {name}")
    amd64 = _checked_sha(digests[names["amd64"]], names["amd64"])
    arm64 = _checked_sha(digests[names["arm64"]], names["arm64"])
    urls = {
        amd64: f"{CODEX_DOWNLOAD_URL}/{version}/{names['amd64']}",
        arm64: f"{CODEX_DOWNLOAD_URL}/{version}/{names['arm64']}",
    }
    return Pin(version, amd64, arm64), urls


RESOLVERS = {"claude": resolve_claude, "codex": resolve_codex}


def verify_downloads(fetch: Fetch, urls: dict[str, str]) -> None:
    """Der PR-Build prueft nur amd64 — arm64 entstuende erst beim Publish.

    Deshalb werden beide Dateien hier geladen und gegen die Herstellerangabe
    gehasht, bevor ein Pin ueberhaupt in einen PR gelangt.
    """
    for expected, url in urls.items():
        actual = hashlib.sha256(fetch(url)).hexdigest()
        if actual != expected:
            raise BumpError(f"Hash-Abweichung fuer {url}: erwartet {expected}, erhalten {actual}")


def read_pin(dockerfile_text: str, tool: Tool) -> Pin:
    values = []
    for suffix in ("VERSION", "SHA256_AMD64", "SHA256_ARM64"):
        matches = re.findall(rf"^ARG {tool.arg_prefix}_{suffix}=(\S+)$", dockerfile_text, re.M)
        if len(matches) != 1:
            raise BumpError(f"ARG {tool.arg_prefix}_{suffix} nicht genau einmal im Dockerfile")
        values.append(matches[0])
    return Pin(*values)


def write_pin(dockerfile_text: str, tool: Tool, pin: Pin) -> str:
    for suffix, value in (
        ("VERSION", pin.version),
        ("SHA256_AMD64", pin.sha256_amd64),
        ("SHA256_ARM64", pin.sha256_arm64),
    ):
        dockerfile_text = re.sub(
            rf"^(ARG {tool.arg_prefix}_{suffix}=)\S+$",
            rf"\g<1>{value}",
            dockerfile_text,
            flags=re.M,
        )
    return dockerfile_text


def changelog_fragment(tool: Tool, old: Pin, new: Pin) -> str:
    return (
        "### Changed\n\n"
        f"- **{tool.label}-Binary im Image von `{old.version}` auf `{new.version}` angehoben.** "
        "Version und beide SHA256-Werte (amd64, arm64) im `Dockerfile` stammen aus der "
        "Herstellerquelle und wurden vor dem Pull Request gegen die ausgelieferten Dateien "
        "geprüft (automatischer Bump, #1861).\n"
    )


def _emit_outputs(values: dict[str, str]) -> None:
    lines = "".join(f"{key}={value}\n" for key, value in values.items())
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(lines)
    sys.stdout.write(lines)


def main(argv: list[str] | None = None, *, fetch: Fetch = http_get) -> int:
    parser = argparse.ArgumentParser(description="Hebt die gepinnten CLI-Binaries im Dockerfile an.")
    parser.add_argument("--tool", choices=sorted(TOOLS), required=True)
    parser.add_argument("--version", default=None, help="Zielversion statt Kanal/neuestem Release")
    parser.add_argument("--dockerfile", type=Path, default=REPO_ROOT / "Dockerfile")
    parser.add_argument("--changelog-dir", type=Path, default=REPO_ROOT / "changelog.d")
    args = parser.parse_args(argv)

    tool = TOOLS[args.tool]
    text = args.dockerfile.read_text(encoding="utf-8")
    try:
        old = read_pin(text, tool)
        new, urls = RESOLVERS[args.tool](fetch, args.version or None)
        if new == old:
            _emit_outputs({"changed": "false", "old_version": old.version, "new_version": new.version})
            return 0
        verify_downloads(fetch, urls)
    except BumpError as exc:
        sys.stderr.write(f"bump_cli_binaries: {exc}\n")
        return 1

    args.dockerfile.write_text(write_pin(text, tool, new), encoding="utf-8")
    # Ein Fragment je Werkzeug: ein nachgezogener Bump-PR ueberschreibt es.
    fragment = args.changelog_dir / f"1861-bump-{args.tool}-cli.md"
    fragment.write_text(changelog_fragment(tool, old, new), encoding="utf-8")
    _emit_outputs({"changed": "true", "old_version": old.version, "new_version": new.version})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
