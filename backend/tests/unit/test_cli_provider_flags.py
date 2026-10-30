"""CLI-Flag- und Supply-Chain-Contract-Tests (#1861).

Dieser Testblock stellt sicher, dass:
1. Dockerfile exakte Semver-/Release-Pins und 64-stellige Hex-SHA-256-Checksummen
   für alle im Container installierten CLI-Binaries (Claude Code, Codex) besitzt.
2. DISABLE_AUTOUPDATER=1 in base und prod gesetzt ist, um unkontrollierte
   Hintergrund-Bumps im laufenden Container zu verhindern.
3. Die von den Providern (claude_cli.py, codex_cli.py) erzeugten Kommandos
   exakt mit den im Dockerfile definierten REQUIRED_FLAGS übereinstimmen.
4. Gemini weiterhin als reiner API-Provider klassifiziert ist (kein CLI-Binary).
5. Das Dockerfile-Gate gegen `--help`-Ausgaben mit der im Dockerfile genutzten
   Regex-Erkennung kompatibel ist.
6. Der Branch-Protection-Gate-Job `Image-Build-Gate` in docker-image.yml
   strukturell korrekt konfiguriert ist.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent
_DOCKERFILE_PATH = _REPO_ROOT / "Dockerfile"
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "docker-image.yml"

_HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SEMVER_OR_TAG_PATTERN = re.compile(r"^(?:rust-)?v?\d+\.\d+\.\d+(?:-[\w.]+)?$")

_SHORT_TO_LONG_FLAGS = {
    "-p": "--print",
}


def _read_dockerfile() -> str:
    assert _DOCKERFILE_PATH.is_file(), f"Dockerfile nicht gefunden unter {_DOCKERFILE_PATH}"
    return _DOCKERFILE_PATH.read_text(encoding="utf-8")


def _get_dockerfile_arg(dockerfile_text: str, arg_name: str) -> str:
    match = re.search(rf'^ARG\s+{arg_name}=(?:"([^"]+)"|([^\s\n]+))', dockerfile_text, re.MULTILINE)
    assert match, f"ARG {arg_name} nicht im Dockerfile gefunden"
    return match.group(1) or match.group(2)


def _get_command_flags(cmd: list[str]) -> set[str]:
    """Extrahiert alle CLI-Flags aus einer Argumentliste (inklusive Flag-Normalisierung)."""
    flags: set[str] = set()
    for token in cmd:
        if token.startswith("-") and token != "-":
            normalized = _SHORT_TO_LONG_FLAGS.get(token, token)
            flags.add(normalized)
    return flags


# ===========================================================================
# 1. Supply-Chain: Pins, Checksummen und Auto-Updater
# ===========================================================================


class TestCliBinarySupplyChainPins:
    """Prüft die kryptografische und versionsbezogene Pin-Integrität im Dockerfile."""

    def test_codex_pins_are_exact_and_valid_hashes(self) -> None:
        dockerfile = _read_dockerfile()
        version = _get_dockerfile_arg(dockerfile, "CODEX_VERSION")
        sha_amd64 = _get_dockerfile_arg(dockerfile, "CODEX_SHA256_AMD64")
        sha_arm64 = _get_dockerfile_arg(dockerfile, "CODEX_SHA256_ARM64")

        # Keine Platzhalter oder dynamischen Tags
        assert _SEMVER_OR_TAG_PATTERN.match(version), (
            f"CODEX_VERSION '{version}' ist kein valider Tag/Semver"
        )
        assert "latest" not in version.lower()
        assert not any(char in version for char in ["^", "~", "*", "<", ">"])

        # Exakt 64-stellige Hex-Hashes für amd64 und arm64
        assert _HEX_64_PATTERN.match(sha_amd64), (
            f"CODEX_SHA256_AMD64 '{sha_amd64}' ist kein 64-Zeichen Hex-Hash"
        )
        assert _HEX_64_PATTERN.match(sha_arm64), (
            f"CODEX_SHA256_ARM64 '{sha_arm64}' ist kein 64-Zeichen Hex-Hash"
        )
        assert sha_amd64 != sha_arm64, "amd64- und arm64-Hashes dürfen nicht identisch sein"

    def test_claude_code_pins_are_exact_and_valid_hashes(self) -> None:
        dockerfile = _read_dockerfile()
        version = _get_dockerfile_arg(dockerfile, "CLAUDE_CODE_VERSION")
        sha_amd64 = _get_dockerfile_arg(dockerfile, "CLAUDE_CODE_SHA256_AMD64")
        sha_arm64 = _get_dockerfile_arg(dockerfile, "CLAUDE_CODE_SHA256_ARM64")

        assert _SEMVER_OR_TAG_PATTERN.match(version), (
            f"CLAUDE_CODE_VERSION '{version}' ist kein valides Semver"
        )
        assert "latest" not in version.lower()
        assert not any(char in version for char in ["^", "~", "*", "<", ">"])

        assert _HEX_64_PATTERN.match(sha_amd64), (
            f"CLAUDE_CODE_SHA256_AMD64 '{sha_amd64}' ist kein 64-Zeichen Hex-Hash"
        )
        assert _HEX_64_PATTERN.match(sha_arm64), (
            f"CLAUDE_CODE_SHA256_ARM64 '{sha_arm64}' ist kein 64-Zeichen Hex-Hash"
        )
        assert sha_amd64 != sha_arm64, "amd64- und arm64-Hashes dürfen nicht identisch sein"

    def test_disable_autoupdater_is_enforced_in_base_and_prod(self) -> None:
        dockerfile = _read_dockerfile()

        # base-Stage (von der dev erbt)
        base_match = re.search(r"FROM [^\n]+ AS base[\s\S]+?ENV DISABLE_AUTOUPDATER=1", dockerfile)
        assert base_match, "DISABLE_AUTOUPDATER=1 fehlt in der 'base'-Stage des Dockerfiles"

        # prod-Stage (die separat auf python:3.14-slim basiert)
        prod_match = re.search(r"FROM [^\n]+ AS prod[\s\S]+?DISABLE_AUTOUPDATER=1", dockerfile)
        assert prod_match, "DISABLE_AUTOUPDATER=1 fehlt in der 'prod'-Stage des Dockerfiles"


# ===========================================================================
# 2. Flag-Vertrag: Provider vs Dockerfile REQUIRED_FLAGS
# ===========================================================================


class TestCliProviderFlagContracts:
    """Verifiziert, dass Provider-Kommandos und Dockerfile-Verträge synchron sind."""

    def test_claude_provider_matches_dockerfile_required_flags(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.llm.providers import claude_cli

        monkeypatch.setattr(claude_cli, "is_claude_cli_available", lambda: True)

        cmd = claude_cli.build_claude_cli_command(
            model="claude-3-7-sonnet",
        )

        dockerfile = _read_dockerfile()
        required_flags_raw = _get_dockerfile_arg(dockerfile, "CLAUDE_CODE_REQUIRED_FLAGS")
        dockerfile_flags = set(required_flags_raw.split())

        cmd_flags = _get_command_flags(cmd)
        assert cmd_flags == dockerfile_flags, (
            f"Flag-Drift zwischen claude_cli.py ({cmd_flags}) und Dockerfile ({dockerfile_flags})"
        )

        # Sicherheits- und Parsing-Vertrag:
        # --permission-prompts none (nicht-interaktiver Batch-Betrieb)
        # --output-format json (strukturierte Rückgabe)
        # --tools "" (keine unerwünschten Tool-Hooks im Provider)
        assert "--permission-prompts" in cmd
        perm_idx = cmd.index("--permission-prompts")
        assert cmd[perm_idx + 1] == "none"

        assert "--output-format" in cmd
        format_idx = cmd.index("--output-format")
        assert cmd[format_idx + 1] == "json"

        assert "--tools" in cmd
        tools_idx = cmd.index("--tools")
        assert cmd[tools_idx + 1] == ""

    def test_codex_provider_matches_dockerfile_required_flags(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.llm.providers import codex_cli

        monkeypatch.setattr(codex_cli, "is_codex_cli_available", lambda: True)

        cmd = codex_cli.build_codex_cli_command(
            model="gpt-5-codex",
        )

        dockerfile = _read_dockerfile()
        required_flags_raw = _get_dockerfile_arg(dockerfile, "CODEX_REQUIRED_EXEC_FLAGS")
        dockerfile_flags = set(required_flags_raw.split())

        cmd_flags = _get_command_flags(cmd)
        assert cmd_flags == dockerfile_flags, (
            f"Flag-Drift zwischen codex_cli.py ({cmd_flags}) und Dockerfile ({dockerfile_flags})"
        )

        # Sicherheits- und Ausführungsvertrag:
        # Erster Subcommand ist 'exec'
        # --sandbox read-only (keine Schreibzugriffe des CLI-Tools)
        # --skip-git-repo-check (Ausführung auch ohne Git-Repo-Kontext im Container)
        # '-' am Ende für Stdin-Prompt
        assert cmd[0] == "codex"
        assert cmd[1] == "exec"
        assert "--sandbox" in cmd
        sb_idx = cmd.index("--sandbox")
        assert cmd[sb_idx + 1] == "read-only"
        assert "--skip-git-repo-check" in cmd
        assert cmd[-1] == "-"


# ===========================================================================
# 3. Gemini-Provider Architekturstatus (API vs CLI)
# ===========================================================================


class TestGeminiProviderArchitecture:
    """Dokumentiert und prüft den Provider-Status von Gemini.

    Gemini ist in Agora via Google AI Studio API angebunden (Issue #590),
    nicht als lokales CLI-Binary. Sollte künftig ein Gemini-CLI-Provider
    hinzukommen, muss dieser ebenfalls mit Version, SHA-256 und REQUIRED_FLAGS
    im Dockerfile gepinnt und hier abgesichert werden.
    """

    def test_gemini_is_api_adapter_and_not_binary(self) -> None:
        from app.llm.providers.gemini import GeminiAdapter
        from app.llm.providers.base import ProviderAdapter

        assert issubclass(GeminiAdapter, ProviderAdapter)
        adapter = GeminiAdapter()
        assert adapter.name == "google"
        assert not hasattr(adapter, "build_gemini_cli_command")


# ===========================================================================
# 4. Simulation des Dockerfile `--help` Prüfmusters
# ===========================================================================


class TestDockerfileHelpValidationRegex:
    """Prüft die im Dockerfile verwendete Regex-Logik gegen `--help`-Snippets."""

    _MOCK_CLAUDE_HELP = """
Usage: claude [options] [prompt]

Options:
  -p, --print                    Print response to stdout and exit
  --output-format <format>       Output format: text, json, stream (default: "text")
  --tools <tools>                Comma-separated tools to enable, or "" to disable
  --permission-prompts <mode>    Permission prompt mode (none, ask, strict)
  --model <model>                Model identifier
  -h, --help                     Display help for command
"""

    _MOCK_CODEX_EXEC_HELP = """
Usage: codex exec [OPTIONS] [PROMPT]

Options:
      --skip-git-repo-check      Allow execution outside a git repository
      --sandbox <MODE>           Sandbox execution mode [read-only, workspace-only, unrestricted]
      --model <MODEL>            Model identifier to use
  -h, --help                     Print help
"""

    def test_dockerfile_pattern_matches_claude_help(self) -> None:
        dockerfile = _read_dockerfile()
        flags = _get_dockerfile_arg(dockerfile, "CLAUDE_CODE_REQUIRED_FLAGS").split()

        for flag in flags:
            # Im Dockerfile: grep -Eq -- "${_flag}([^a-z-]|\$)"
            pattern = re.compile(rf"{re.escape(flag)}([^a-z-]|$)")
            assert pattern.search(self._MOCK_CLAUDE_HELP), (
                f"Flag '{flag}' wird vom Dockerfile-Muster in Claude --help nicht erkannt"
            )

    def test_dockerfile_pattern_matches_codex_exec_help(self) -> None:
        dockerfile = _read_dockerfile()
        flags = _get_dockerfile_arg(dockerfile, "CODEX_REQUIRED_EXEC_FLAGS").split()

        for flag in flags:
            pattern = re.compile(rf"{re.escape(flag)}([^a-z-]|$)")
            assert pattern.search(self._MOCK_CODEX_EXEC_HELP), (
                f"Flag '{flag}' wird vom Dockerfile-Muster in Codex exec --help nicht erkannt"
            )

    def test_dockerfile_pattern_rejects_missing_or_partial_flag(self) -> None:
        # Ein Flag, das nicht existiert, darf nicht matchen
        pattern = re.compile(r"--nonexistent-flag([^a-z-]|$)")
        assert not pattern.search(self._MOCK_CLAUDE_HELP)

        # Ein Prefix darf nicht matchen (z. B. --model-suffix wenn nur --model da ist)
        prefix_pattern = re.compile(r"--model-timeout([^a-z-]|$)")
        assert not prefix_pattern.search(self._MOCK_CLAUDE_HELP)


# ===========================================================================
# 5. Workflow-Gate Konfiguration in docker-image.yml
# ===========================================================================


class TestDockerImageWorkflowGate:
    """Verifiziert die Existenz und Konfiguration von Image-Build-Gate."""

    def test_image_build_gate_job_exists_and_is_configured(self) -> None:
        assert _WORKFLOW_PATH.is_file(), f"Workflow-Datei fehlt: {_WORKFLOW_PATH}"
        data = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))

        jobs = data.get("jobs", {})
        assert "image-build-gate" in jobs, "Job 'image-build-gate' fehlt in docker-image.yml"

        gate = jobs["image-build-gate"]
        assert gate.get("name") == "Image-Build-Gate", (
            f"Job-Name muss 'Image-Build-Gate' sein, ist '{gate.get('name')}'"
        )
        assert gate.get("if") == "always()", (
            f"Job-Condition muss 'always()' sein, ist '{gate.get('if')}'"
        )

        needs = gate.get("needs", [])
        assert "build-only" in needs, "'build-only' muss in needs von image-build-gate sein"
        assert "prod-proxy-smoke" in needs, (
            "'prod-proxy-smoke' muss in needs von image-build-gate sein"
        )
