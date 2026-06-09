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

from ..contracts import LEGACY_GEMINI, PROVIDER_GOOGLE
from ..services.llm_profiles_store import get_llm_profiles_store

_PROFILE_PREFIX = "profile:"

_PROFILE_PROVIDER_TO_RUNTIME = {
    "openai": "openai",
    LEGACY_GEMINI: PROVIDER_GOOGLE,
    "ollama": "custom_openai",
    "anthropic": "custom_openai",
    "custom": "custom_openai",
}


def expand_profile_in_data(data: Any) -> None:
    """Mutate *data* (a request payload dict) in place.

    No-op if `data` is not a dict, if `llm_model` doesn't start with
    `profile:`, or if the referenced profile cannot be resolved. Existing
    explicit `llm_provider` fields from the request override the profile
    values — request still wins over profile, profile fills the gaps.
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
        profile = get_llm_profiles_store().get(profile_id, include_api_key=True)
    except Exception:  # noqa: BLE001 — defensive: store failure must not break the request earlier
        return
    if profile is None:
        return

    data["llm_model"] = profile.model_name

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
    data["llm_provider"] = merged
