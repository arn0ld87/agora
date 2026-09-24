"""Regressionsschutz Issue #1284 (Codex-Finding P1): ``_detect_default_provider_id``
darf fuer einen erkannten Anthropic-Endpunkt kein rohes ``KeyError`` werfen.

``_HTTP_DETECTION_TO_PROVIDER_ID`` bildet die SSoT-Vokabel (``detect_provider``,
mode="http") auf dieses Moduls eigene Provider-IDs ab und hatte keinen
"anthropic"-Eintrag — seit ``detect_provider`` api.anthropic.com erkennt
(#1284), indizierte der Dict-Lookup direkt mit ``"anthropic"`` und crashte mit
``KeyError`` statt dem klaren Fail-Loud-Fehler.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.runtime_run_config import RuntimeRunConfig, _detect_default_provider_id


def test_detect_default_provider_id_rejects_anthropic_base_url():
    with pytest.raises(ValueError, match="Anthropic"):
        _detect_default_provider_id("https://api.anthropic.com", "claude-sonnet-5")


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
