"""Regressionsschutz Issue #1284 (Codex-Finding P1) und #1567:
``_detect_default_provider_id`` darf fuer keinen von ``detect_provider``
(mode="http") erkannten Wert ein rohes ``KeyError`` werfen.

``_HTTP_DETECTION_TO_PROVIDER_ID`` bildet die SSoT-Vokabel (``detect_provider``,
mode="http") auf dieses Moduls eigene Provider-IDs ab. Fuer "anthropic" hatte
sie (#1284) keinen Eintrag — seit ``detect_provider`` api.anthropic.com
erkennt, indizierte der Dict-Lookup direkt mit ``"anthropic"`` und crashte mit
``KeyError`` statt dem klaren Fail-Loud-Fehler. Fuer "bedrock" (#1567) fehlte
derselbe Eintrag: eine Legacy-Server-Config mit Bedrock-``LLM_BASE_URL``
(kein persistiertes ``runtime_llm_routing.json``) crashte ebenfalls mit
``KeyError('bedrock')``.
"""
from __future__ import annotations

import typing
from unittest.mock import patch

import pytest

from app.contracts import PROVIDER_BEDROCK
from app.llm.providers.registry import HttpDetectedProvider, detect_provider
from app.services.runtime_run_config import RuntimeRunConfig, _detect_default_provider_id


def test_detect_default_provider_id_rejects_anthropic_base_url():
    with pytest.raises(ValueError, match="Anthropic"):
        _detect_default_provider_id("https://api.anthropic.com", "claude-sonnet-5")


def test_detect_default_provider_id_maps_bedrock_base_url():
    """Issue #1567: Legacy-Config mit Bedrock-mantle-Base-URL ⇒ Bedrock-Provider-ID
    statt KeyError."""
    provider_id = _detect_default_provider_id(
        "https://bedrock-mantle.us-east-1.api.aws", "anthropic.claude-sonnet-5"
    )
    assert provider_id == PROVIDER_BEDROCK


def test_detect_default_provider_id_covers_every_http_detection_value():
    """Jeder Rueckgabewert von ``detect_provider(mode="http")`` muss in
    ``_detect_default_provider_id`` entweder gemappt oder explizit
    abgelehnt sein — kein Wert darf ein rohes ``KeyError`` ausloesen."""
    for detected in typing.get_args(HttpDetectedProvider):
        with patch(
            "app.services.runtime_run_config.detect_provider", return_value=detected
        ):
            try:
                _detect_default_provider_id("https://example.invalid", "some-model")
            except ValueError:
                # "anthropic" (fail-loud, #1284) ist die einzige erwartete
                # explizite Ablehnung; alles andere muss gemappt sein.
                assert detected == "anthropic", (
                    f"detect_provider(mode='http') result {detected!r} ist weder "
                    "gemappt noch explizit abgelehnt."
                )
            except KeyError:
                pytest.fail(
                    f"_detect_default_provider_id wirft KeyError fuer "
                    f"detect_provider-Ergebnis {detected!r} statt es zu mappen "
                    "oder abzulehnen."
                )

    # Smoke-Test: die SSoT-Literale und die hier iterierten Werte duerfen
    # nicht auseinanderlaufen.
    assert detect_provider(None, None, mode="http") == "unknown"


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_load_config_legacy_fallback_rejects_anthropic_base_url(mock_run_dir, tmp_path):
    """Kein persistiertes runtime_llm_routing.json → load_config() synthetisiert
    aus Config.LLM_BASE_URL. Ein Anthropic-Endpunkt darf dabei nicht auf den
    generischen openai_compatible-Fallback kippen (KeyError vorher)."""
    run_id = "run_legacy_anthropic"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    with patch("app.config.Config.LLM_BASE_URL", "https://api.anthropic.com"), patch(
        "app.config.Config.LLM_MODEL_NAME", "claude-sonnet-5"
    ):
        with pytest.raises(ValueError, match="Anthropic"):
            RuntimeRunConfig(run_id).load_config()


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_load_config_legacy_fallback_maps_bedrock_base_url(mock_run_dir, tmp_path):
    """Issue #1567: Legacy-Config mit Bedrock-Base-URL ⇒ Bedrock-Provider-ID
    statt KeyError('bedrock')."""
    run_id = "run_legacy_bedrock"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    with patch(
        "app.config.Config.LLM_BASE_URL", "https://bedrock-mantle.us-east-1.api.aws"
    ), patch("app.config.Config.LLM_MODEL_NAME", "anthropic.claude-sonnet-5"):
        config = RuntimeRunConfig(run_id).load_config()

    assert config.global_default.provider_id == PROVIDER_BEDROCK
