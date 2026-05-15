from app.services.llm_runtime import parse_runtime_llm_config


def test_google_runtime_uses_openai_compatible_base_url():
    # Dummy-Key muss das ``AIzaSy``-Format-Präfix erfüllen, sonst lehnt
    # ``_validate_key_format`` als Cross-Provider-Mismatch ab (Smoke-Live-Fix
    # 2026-05-15, Followup zu PR #466).
    cfg = parse_runtime_llm_config(
        {"llm_provider": {"provider": "google", "api_key": "AIzaSy-dummy-test-key"}}
    )

    assert cfg.enabled
    assert cfg.provider == "google"
    assert cfg.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert cfg.subprocess_env(model="gemini-2.5-flash") == {
        "LLM_API_KEY": "AIzaSy-dummy-test-key",
        "OPENAI_API_KEY": "AIzaSy-dummy-test-key",
        "LLM_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "OPENAI_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "OPENAI_API_BASE": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "OPENAI_API_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "LLM_MODEL_NAME": "gemini-2.5-flash",
    }


def test_validate_key_format_rejects_cross_provider_keys():
    """Followup zu PR #466 (Live-Smoke 2026-05-15): ein Gemini-``AIzaSy``-Key
    an einen ``openai``-Provider muss mit ``ValueError`` abgelehnt werden,
    damit der NER-Loop nicht 100× 401 von OpenAI bekommt.
    """
    import pytest as _pytest

    with _pytest.raises(ValueError, match="api_key format does not match provider 'openai'"):
        parse_runtime_llm_config(
            {"llm_provider": {"provider": "openai", "api_key": "AIzaSyD9_wrong_provider"}}
        )

    with _pytest.raises(ValueError, match="api_key format does not match provider 'google'"):
        parse_runtime_llm_config(
            {"llm_provider": {"provider": "google", "api_key": "sk-wrong-provider-for-google"}}
        )

    # custom_openai bleibt ungeprüft (beliebige Key-Formate erlaubt).
    cfg = parse_runtime_llm_config(
        {
            "llm_provider": {
                "provider": "custom_openai",
                "api_key": "anything-goes",
                "base_url": "https://example.com/v1",
            }
        }
    )
    assert cfg.api_key == "anything-goes"


def test_runtime_metadata_redacts_api_key():
    cfg = parse_runtime_llm_config(
        {
            "llm_provider": {
                "provider": "custom_openai",
                "api_key": "secret-value",
                "base_url": "https://example.test/v1",
            }
        }
    )

    assert cfg.redacted_metadata() == {
        "provider": "custom_openai",
        "base_url": "https://example.test/v1",
        "api_key_set": True,
    }
    assert "secret-value" not in str(cfg.redacted_metadata())


def test_non_default_provider_without_api_key_is_accepted():
    """Seit Smoke-Fix Slice 04: leerer api_key im Payload wirft keinen Fehler mehr.

    Der Fallback auf den Settings-DB-Key erfolgt in resolve_route_api_key().
    parse_runtime_llm_config() setzt api_key=None und gibt enabled=True zurück.
    """
    cfg = parse_runtime_llm_config({"llm_provider": {"provider": "google"}})
    assert cfg.enabled
    assert cfg.provider == "google"
    assert cfg.api_key is None


def test_runtime_metadata_shows_api_key_set_false_when_key_absent():
    """redacted_metadata() zeigt api_key_set=False wenn api_key=None."""
    cfg = parse_runtime_llm_config({"llm_provider": {"provider": "google"}})
    meta = cfg.redacted_metadata()
    assert meta["api_key_set"] is False
