"""
Secret Resolver.
Resolves API keys from session, persistent store, or environment without
exposing them in serializable objects.

Resolution order:
  1. Session-only override (höchste Priorität, für ad-hoc Tests)
  2. Persistenter Fernet-encrypted Store (vom Frontend befüllt)
  3. Provider-spezifische Environment-Variablen (mit Format-Sanity-Check)
  4. Globaler Fallback (Config.LLM_API_KEY) — nur für Provider ohne striktes
     Format oder wenn der Wert das erwartete Format trifft

Format-Sanity-Check (Track 1 Hardening, siehe ``backend/CLAUDE.md`` /
``docs/runbooks/architecture-layers.md``): ENV- und Config-Fallback-Werte
werden für provider_type ``openai`` / ``google`` gegen das jeweilige
Key-Format geprüft. Bekannt-toxische Marker (``ollama``, ``none``, …) werden
universell abgelehnt. So kann ein versehentlicher ``OPENAI_API_KEY=ollama``
in einem Container-Env nicht mehr zum 401-Loop führen.

Provider-spezifische ENV-Mapping:
  * ``openai``            → ``OPENAI_API_KEY``         (Format ``sk-…``)
  * ``google``            → ``GOOGLE_API_KEY`` / ``GEMINI_API_KEY`` (``AIzaSy…``)
  * ``ollama_cloud``      → ``OLLAMA_API_KEY``         (Bearer, kein striktes Format)
  * ``openai_compatible`` → ``LLM_API_KEY``            (kein striktes Format)
  * ``github_copilot``    → eigene Auflösung über ``llm_providers.github_copilot``

Ollama-Cloud-Auth-Doku: ``~/.agents/skills/ollama-cloud-models/SKILL.md`` (v2).
Zwei Modi: **Direct API** (``https://ollama.com`` nativ oder ``/v1``
OpenAI-kompatibel, ``Authorization: Bearer $OLLAMA_API_KEY``) und
**Local Proxy** (``http://localhost:11434``, kein Key). Dieser Resolver
adressiert ausschließlich Direct API — Local Proxy umgeht ihn, weil dort
kein Auth-Material gebraucht wird.
"""

import logging
import os
import re
from typing import Optional, Dict

from ..config import Config
from ..contracts import (
    PROVIDER_GOOGLE,
    PROVIDER_OLLAMA_CLOUD,
    PROVIDER_OPENAI,
    PROVIDER_OPENAI_COMPATIBLE,
    PROVIDER_GITHUB_COPILOT,
)
from .llm_provider_secrets_store import get_llm_provider_secrets_store

logger = logging.getLogger("agora.secret_resolver")

# Provider-spezifische Key-Formate. Bewusst eng gehalten, damit
# Tippfehler und Müll-Defaults (``ollama``, ``your-key-here``) verlässlich
# rausfallen. Echte Keys sind länger und matchen das Prefix.
_OPENAI_KEY_RE = re.compile(r"^sk-[A-Za-z0-9_\-]{20,}$")
_GOOGLE_KEY_RE = re.compile(r"^AIza[A-Za-z0-9_\-]{20,}$")

# Werte, die nie als Key durchgehen dürfen — historische Default-Empfehlungen
# (siehe app/config.py:305 "set to any non-empty value, e.g. 'ollama'").
_TOXIC_KEY_LITERALS = frozenset(
    {
        "ollama",
        "none",
        "null",
        "true",
        "false",
        "changeme",
        "your-key-here",
        "your-api-key",
        "sk-",
        "aiza",
    }
)


def _format_valid(value: Optional[str], provider_type: str) -> bool:
    """Provider-aware Format-Check für ENV- / Config-Fallback-Werte.

    Sicher = Wert hat das erwartete Prefix und ist lang genug. Bei nicht
    explizit gehärteten Provider-Types (``ollama_cloud``, ``openai_compatible``,
    ``github_copilot``) bleibt nur der Toxic-Literal-Filter, weil deren
    Key-Format vom Backend bestimmt wird (z. B. Ollama-Cloud-Hex).
    """
    if not value or not isinstance(value, str):
        return False
    v = value.strip()
    if not v:
        return False
    if v.lower() in _TOXIC_KEY_LITERALS:
        return False
    if provider_type == PROVIDER_OPENAI:
        return bool(_OPENAI_KEY_RE.match(v))
    if provider_type == PROVIDER_GOOGLE:
        return bool(_GOOGLE_KEY_RE.match(v))
    return True


def _mask_for_log(value: Optional[str]) -> str:
    """Erster Block für Logs. Niemals den ganzen Wert ausgeben."""
    if not value:
        return "<empty>"
    v = value.strip()
    if not v:
        return "<empty>"
    if len(v) <= 4:
        return "<short>"
    return f"{v[:4]}..."


class SecretResolver:
    """Resolves secrets for LLM providers.

    Side-Channel: nach jedem :meth:`get_api_key`-Aufruf hält
    :attr:`last_source` die Herkunft des zurückgegebenen Keys
    (``session`` / ``store`` / ``env:NAME`` / ``config_fallback`` /
    ``github_copilot`` / ``None``). Für Audit-Logging im LLMClient-Init
    und für den Diagnostic-Endpoint in Track 2.
    """

    def __init__(self, session_api_keys: Optional[Dict[str, str]] = None):
        self._session_keys = session_api_keys or {}
        self.last_source: Optional[str] = None

    def get_api_key(self, provider_id: str, provider_type: str) -> Optional[str]:
        """Resolve API key for a provider. Setzt :attr:`last_source` als Seiteneffekt."""
        self.last_source = None

        # 1. Session-only override
        if provider_id in self._session_keys:
            self.last_source = "session"
            return self._session_keys[provider_id]

        # 2. Persistenter Store (Fernet-encrypted, vom Frontend befüllt)
        try:
            stored = get_llm_provider_secrets_store().get_plaintext(provider_id)
            if stored:
                self.last_source = "store"
                return stored
        except RuntimeError as exc:
            # AGORA_SECRET_KEY fehlt o. ä. — auf env-Fallback weiterleiten.
            # Hier explizit ohne Key-Werte loggen.
            logger.warning("Secret-Store-Zugriff fehlgeschlagen, fallback auf env: %s", exc)

        # 3. Provider-spezifische Environment-Variablen (mit Format-Sanity-Check)
        env_candidates: list[tuple[str, Optional[str]]] = []
        if provider_type == PROVIDER_OPENAI:
            env_candidates.append(("env:OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY")))
        elif provider_type == PROVIDER_GOOGLE:
            env_candidates.append(("env:GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY")))
            env_candidates.append(("env:GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY")))
        elif provider_type == PROVIDER_OLLAMA_CLOUD:
            env_candidates.append(("env:OLLAMA_API_KEY", os.environ.get("OLLAMA_API_KEY")))
        elif provider_type == PROVIDER_OPENAI_COMPATIBLE:
            env_candidates.append(("env:LLM_API_KEY", os.environ.get("LLM_API_KEY")))
        elif provider_type == PROVIDER_GITHUB_COPILOT:
            # GitHub Copilot: Token-Auflösung über separates Modul (Slice B).
            try:
                from .llm_providers.github_copilot import resolve_copilot_token
            except ImportError:
                return None
            token = resolve_copilot_token()
            if token:
                self.last_source = "github_copilot"
            return token

        for source_label, candidate in env_candidates:
            if candidate is None:
                continue
            if _format_valid(candidate, provider_type):
                self.last_source = source_label
                return candidate
            env_name = source_label.split(":", 1)[-1]
            logger.warning(
                "ENV-Variable %s enthält für provider_type=%s keinen Key im erwarteten Format "
                "(Prefix: %s) — wird übersprungen.",
                env_name,
                provider_type,
                _mask_for_log(candidate),
            )

        # 4. Globaler Fallback Config.LLM_API_KEY
        fallback = Config.LLM_API_KEY
        if fallback:
            if provider_type in (PROVIDER_OPENAI, PROVIDER_GOOGLE):
                if _format_valid(fallback, provider_type):
                    self.last_source = "config_fallback"
                    return fallback
                logger.warning(
                    "Config.LLM_API_KEY hat falsches Format für provider_type=%s "
                    "(Prefix: %s) — wird NICHT als Fallback genutzt. Setze den Key "
                    "im UI (Settings → LLM-Provider) oder via ENV %s.",
                    provider_type,
                    _mask_for_log(fallback),
                    "OPENAI_API_KEY" if provider_type == PROVIDER_OPENAI else "GOOGLE_API_KEY",
                )
                return None
            # Provider-Type ohne striktes Format (ollama_cloud, openai_compatible, …):
            # Globalen Fallback durchlassen, aber Toxic-Literal-Filter anwenden.
            if not _format_valid(fallback, provider_type):
                logger.warning(
                    "Config.LLM_API_KEY ist ein Toxic-Literal (Prefix: %s) — wird nicht "
                    "als Fallback für provider_type=%s genutzt.",
                    _mask_for_log(fallback),
                    provider_type,
                )
                return None
            self.last_source = "config_fallback"
            return fallback

        return None

    def sanitize_url(self, url: Optional[str]) -> Optional[str]:
        """Remove secrets from URL (no userinfo, no query string)."""
        if not url:
            return url
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        # Remove user:pass and query/fragment
        sanitized = parsed._replace(netloc=parsed.hostname + (f":{parsed.port}" if parsed.port else ""), query="", fragment="")
        return urlunparse(sanitized)
