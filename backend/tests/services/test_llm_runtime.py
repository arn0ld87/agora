from app.services.llm_runtime import parse_runtime_llm_config


def test_google_runtime_uses_openai_compatible_base_url():
    cfg = parse_runtime_llm_config(
        {"llm_provider": {"provider": "google", "api_key": "gemini-key"}}
    )

    assert cfg.enabled
    assert cfg.provider == "google"
    assert cfg.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert cfg.subprocess_env(model="gemini-2.5-flash") == {
        "LLM_API_KEY": "gemini-key",
        "OPENAI_API_KEY": "gemini-key",
        "LLM_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "OPENAI_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "OPENAI_API_BASE": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "OPENAI_API_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "LLM_MODEL_NAME": "gemini-2.5-flash",
    }


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
        "provider": "openai_compatible",
        "base_url": "https://example.test/v1",
        "api_key_set": True,
    }
    assert "secret-value" not in str(cfg.redacted_metadata())


def test_non_default_provider_requires_api_key():
    try:
        parse_runtime_llm_config({"llm_provider": {"provider": "google"}})
    except ValueError as exc:
        assert "api_key" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing api_key")
