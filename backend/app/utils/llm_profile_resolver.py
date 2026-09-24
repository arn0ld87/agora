"""Expand UI-side `model: "profile:<id>"` tokens into real model + provider creds.

Frontend `HeroNewRun.vue` ships persisted LLM-Profiles as pseudo-models of the
form `profile:<uuid>` in the `llm_model` request field. Only the ontology-
generate endpoint had a dedicated profile resolver — graph build, persona
prepare, report generation and run resume passed the pseudo-token straight to
the LLM client, which sent it as the model name to Ollama and got a 404.

`expand_profile_in_data` makes the resolution transparent: it mutates the
request `data` dict in place so all downstream code sees a real `model_name`
and a fully populated `llm_provider` block (provider/api_key/base_url from the
stored profile).
"""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import ANTHROPIC_CHAT_TRANSPORT_UNSUPPORTED, LEGACY_GEMINI, PROVIDER_GOOGLE
from ..llm.providers.registry import detect_provider
from ..repositories.llm_profile_repository import get_llm_profile_repository

_PROFILE_PREFIX = "profile:"

_PROFILE_PROVIDER_TO_RUNTIME = {
    "openai": "openai",
    LEGACY_GEMINI: PROVIDER_GOOGLE,
    "ollama": "custom_openai",
    "custom": "custom_openai",
}


def expand_profile_in_data(data: Any) -> None:
    """Mutate *data* (a request payload dict) in place.

    No-op if `data` is not a dict, if `llm_model` doesn't start with
    `profile:`, or if the referenced profile cannot be resolved. Existing
    explicit `llm_provider` fields from the request override the profile
    values — request still wins over profile, profile fills the gaps.

    Raises:
        ValueError: If the *effective* route — profile values merged with
            any explicit request override — still resolves to Anthropic's
            native API (Issue #1284). There is no native Anthropic chat
            transport: the old mapping silently rerouted it through
            ``custom_openai`` onto a base URL (``https://api.anthropic.com``)
            the OpenAI-compatible client can't actually speak to, producing a
            403/404 at request time instead of a clear error here. The check
            runs *after* the merge, not on the bare profile provider, so an
            explicit request override (e.g. onto Bedrock) that wins against
            the profile per the precedence documented above is not blocked
            by a profile-only gate that ignores it. Callers propagate this
            as HTTP 400 (see e.g. ``@handle_api_errors``).
    """
    if not isinstance(data, Mapping):
        return
    raw_model = (data.get("llm_model") or "")
    if not isinstance(raw_model, str) or not raw_model.startswith(_PROFILE_PREFIX):
        return
    profile_id = raw_model[len(_PROFILE_PREFIX) :].strip()
    if not profile_id:
        return
    try:
        profile = get_llm_profile_repository().get(profile_id, include_api_key=True)
    except Exception:  # noqa: BLE001 — defensive: store failure must not break the request earlier
        return
    if profile is None:
        return

    runtime_provider = _PROFILE_PROVIDER_TO_RUNTIME.get(
        (profile.provider or "").lower(), "custom_openai"
    )
    existing = data.get("llm_provider")
    merged: dict[str, Any] = {
        "provider": runtime_provider,
        "base_url": profile.base_url,
        "api_key": profile.api_key or "",
    }
    if isinstance(existing, Mapping):
        # Request-supplied values win — only fill empty slots from the profile.
        for k, v in existing.items():
            if v not in (None, "", {}):
                merged[k] = v

    # Issue #1284: decide on the merged base URL, not the bare profile
    # provider — an explicit request override already won above, so this
    # sees exactly what would actually be dialed. Central detect_provider
    # (registry.py) — no second heuristic. Nothing in `data` is mutated
    # before this check, so a rejected request leaves the payload untouched.
    if detect_provider(merged.get("base_url"), profile.model_name, mode="http") == "anthropic":
        raise ValueError(ANTHROPIC_CHAT_TRANSPORT_UNSUPPORTED)

    data["llm_model"] = profile.model_name
    data["llm_provider"] = merged
