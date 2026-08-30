"""Codex-CLI-Bridge (Issue #1405): ChatGPT-Abo statt Pay-per-Token-API.

Spricht den lokal installierten, per ``codex login`` bereits authentifizierten
``codex``-Subprozess an, statt einen ``OPENAI_API_KEY`` zu verlangen. Bewusst
KEIN eigener ``ProviderAdapter`` (``llm/providers/base.py``) — dieser
Adapter-Hierarchie folgt der aktuelle ``LLMClient.chat``/``chat_json``-Pfad
nicht (verifiziert: ``get_adapter()`` hat ausserhalb der eigenen Definition
keine Aufrufer). Der tatsaechliche Einstiegspunkt ist
``LLMClient._provider_attempt``, der ausschliesslich
``self.client.chat.completions.create(**kwargs)`` ruft. ``CodexCliClient``
imitiert deshalb nur genau diese Teiloberflaeche des OpenAI-SDK-Clients.

Sicherheit: ``codex exec`` ist ein agentisches Coding-Tool und darf NICHT im
CWD des Agora-Backend-Prozesses (= dieses Repo!) mit Schreibrechten laufen.
Jeder Aufruf bekommt ein isoliertes, leeres ``cwd`` und ``--sandbox
read-only``.

Kein Streaming, kein natives ``response_format`` — ``chat_json`` faellt fuer
diesen Provider auf die bestehende Legacy-JSON-Extraktion/-Repair-Pipeline
zurueck (wie bei jedem anderen Provider ohne strict-Schema-Support).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..errors import LlmProviderError
from ...contracts.llm_request import NormalizedLlmError

CODEX_CLI_BINARY_ENV = "AGORA_CODEX_CLI_BIN"
CODEX_CLI_TIMEOUT_ENV = "AGORA_CODEX_CLI_TIMEOUT_SECONDS"
DEFAULT_CODEX_CLI_BINARY = "codex"
DEFAULT_CODEX_CLI_TIMEOUT_SECONDS = 180


def codex_cli_binary() -> str:
    return os.environ.get(CODEX_CLI_BINARY_ENV, DEFAULT_CODEX_CLI_BINARY)


def codex_cli_timeout_seconds() -> float:
    raw = os.environ.get(CODEX_CLI_TIMEOUT_ENV)
    if not raw:
        return float(DEFAULT_CODEX_CLI_TIMEOUT_SECONDS)
    try:
        return float(raw)
    except ValueError:
        return float(DEFAULT_CODEX_CLI_TIMEOUT_SECONDS)


def is_codex_cli_available() -> bool:
    """True wenn das ``codex``-Binary im PATH auffindbar ist.

    Prueft NUR Installation, nicht Login-Status — ein fehlender Login zeigt
    sich erst als Subprozess-Fehler beim ersten echten Aufruf.
    """
    return shutil.which(codex_cli_binary()) is not None


class CodexCliUnavailableError(RuntimeError):
    """Codex-CLI fehlt, ist nicht eingeloggt, oder der Aufruf ist fehlgeschlagen."""


def _flatten_messages(messages: List[Dict[str, Any]]) -> str:
    """OpenAI-Chat-Messages -> ein Prompt-String fuer ``codex exec``.

    Die CLI kennt keine Chat-Turn-Struktur — nur ein Freitext-Prompt. Rollen
    bleiben als Marker erhalten, damit System-/Few-Shot-Anteile im Prompt
    erkennbar bleiben statt stillschweigend zu verschmelzen.
    """
    parts: List[str] = []
    for message in messages:
        role = str(message.get("role", "user")).upper()
        content = message.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)


def _run_codex_cli(prompt: str, *, model: Optional[str]) -> str:
    if not is_codex_cli_available():
        raise CodexCliUnavailableError(
            f"codex-CLI nicht gefunden (PATH, Binary={codex_cli_binary()!r}). "
            "Installation + `codex login` pruefen."
        )
    cmd = [codex_cli_binary(), "exec", "--skip-git-repo-check", "--sandbox", "read-only"]
    if model:
        cmd += ["--model", model]
    cmd.append(prompt)
    timeout = codex_cli_timeout_seconds()
    # Isoliertes CWD: `codex exec` liest/interpretiert Repo-Kontext aus dem
    # Arbeitsverzeichnis. Das Backend-Prozess-CWD ist das Agora-Repo selbst —
    # ein Sandbox-Fehlgriff darf dort nichts anfassen koennen.
    with tempfile.TemporaryDirectory(prefix="agora-codex-cli-") as scratch_dir:
        try:
            result = subprocess.run(  # noqa: S603 — Binary kommt aus Config, Argumente sind kein Shell-String
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=scratch_dir,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CodexCliUnavailableError(
                f"codex exec Timeout nach {timeout:.0f}s"
            ) from exc
        except OSError as exc:
            raise CodexCliUnavailableError(f"codex exec konnte nicht gestartet werden: {exc}") from exc
    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-500:]
        raise CodexCliUnavailableError(
            f"codex exec fehlgeschlagen (exit={result.returncode}): {stderr_tail}"
        )
    text = (result.stdout or "").strip()
    if not text:
        raise CodexCliUnavailableError("codex exec lieferte leere Ausgabe")
    return text


# ---------------------------------------------------------------------------
# Minimaler Duck-Type-Shim der OpenAI-SDK-Oberflaeche
# (``client.chat.completions.create(**kwargs) -> .choices[0].message.content``)
# ---------------------------------------------------------------------------


@dataclass
class _ShimMessage:
    content: str
    role: str = "assistant"


@dataclass
class _ShimChoice:
    message: _ShimMessage
    finish_reason: str = "stop"
    index: int = 0


@dataclass
class _ShimUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class _ShimChatCompletion:
    choices: List[_ShimChoice] = field(default_factory=list)
    usage: _ShimUsage = field(default_factory=_ShimUsage)


class _CodexCliCompletions:
    def create(self, *, model: Optional[str] = None, messages: Optional[List[Dict[str, Any]]] = None, **_ignored: Any) -> _ShimChatCompletion:
        """Wire-kompatibel zu ``openai.Client.chat.completions.create``.

        ``**_ignored`` faengt ``temperature``/``max_tokens``/``response_format``/
        ``tools``/``extra_body``/``stream`` ab — die Codex-CLI kennt keinen
        dieser Parameter. ``stream=True`` wird bewusst NICHT unterstuetzt
        (kein Token-Streaming in diesem Slice); der Aufrufer bekommt hier
        immer die vollstaendige Antwort in einem Zug, ``LLMClient`` erzwingt
        ueber ``_codex_cli_active`` einen nicht-streamenden Call-Pfad.
        """
        prompt = _flatten_messages(messages or [])
        try:
            text = _run_codex_cli(prompt, model=model)
        except CodexCliUnavailableError as exc:
            raise LlmProviderError(
                NormalizedLlmError(
                    provider="codex_cli",
                    code="provider_unavailable",
                    message=str(exc),
                    retryable=False,
                )
            ) from exc
        return _ShimChatCompletion(choices=[_ShimChoice(message=_ShimMessage(content=text))])


class _CodexCliChatNamespace:
    def __init__(self) -> None:
        self.completions = _CodexCliCompletions()


class CodexCliClient:
    """Duck-Type-Ersatz fuer ``openai.OpenAI`` — nur die genutzte Teiloberflaeche."""

    def __init__(self) -> None:
        self.chat = _CodexCliChatNamespace()
