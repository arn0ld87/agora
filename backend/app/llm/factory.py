"""
P5.3: Profile-basierte Client-Factory.

Extracted verbatim from ``app/utils/llm_client.py`` as part of issue #582
(mechanical split — no behavior change).
"""

from typing import TYPE_CHECKING, Optional

from .client import LLMClient

if TYPE_CHECKING:
    from ..contracts.llm_profile_contract import LlmProfile


def build_client_from_profile(
    profile: "LlmProfile",
    *,
    run_id: Optional[str] = None,
    timeout: float = 300.0,
) -> LLMClient:
    """P5.3: LLMClient aus persistiertem LLM-Profil bauen (überschreibt Config).

    Ollama-Provider (localhost oder 'ollama' in base_url) dürfen api_key leer
    lassen — der Dummy-Wert 'ollama' wird gesetzt. Cloud-Provider ohne Key
    scheitern sofort mit einem ValueError, bevor ein HTTP-Request entsteht.
    """
    base_url_lower = profile.base_url.lower()
    is_local = any(
        h in base_url_lower
        for h in ("localhost", "127.0.0.1", "host.docker.internal", "ollama")
    )
    if not profile.api_key and not is_local:
        raise ValueError(
            f"LLM-Profil {profile.id!r}: api_key fehlt für Provider {profile.provider!r}"
        )
    return LLMClient(
        api_key=profile.api_key or "ollama",
        base_url=profile.base_url,
        model=profile.model_name,
        timeout=timeout,
        run_id=run_id,
    )
