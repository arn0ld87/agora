"""Tests für die Pricing Registry (Issue #764)."""
from __future__ import annotations

import json
from pathlib import Path

from app.services.pricing_registry import PricingRegistry

_DATA = {
    "pricing_version": "2099-01",
    "pricing_source": "test-fixture",
    "providers": {
        "openai": [
            {"match": "gpt-4o-mini", "input": 150000, "output": 600000},
            {"match": "gpt-4o", "input": 2500000, "output": 10000000},
        ],
        "google": [
            {"match": "gemini-2.5-flash", "input": 300000, "output": 2500000},
        ],
    },
}


def _registry(tmp_path: Path) -> PricingRegistry:
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(_DATA), encoding="utf-8")
    return PricingRegistry(data_path=path)


class TestPricedResolution:
    def test_exact_prefix_match(self, tmp_path):
        reg = _registry(tmp_path)
        quote = reg.resolve("openai", "gpt-4o-mini")
        assert quote.status == "priced"
        assert quote.input_per_mtok_micros == 150000
        assert quote.pricing_version == "2099-01"

    def test_dated_model_suffix_matches_prefix(self, tmp_path):
        reg = _registry(tmp_path)
        quote = reg.resolve("openai", "gpt-4o-2024-08-06")
        assert quote.status == "priced"
        assert quote.input_per_mtok_micros == 2500000

    def test_longest_prefix_wins(self, tmp_path):
        reg = _registry(tmp_path)
        # "gpt-4o-mini-2024-07-18" darf nicht als "gpt-4o" bepreist werden
        quote = reg.resolve("openai", "gpt-4o-mini-2024-07-18")
        assert quote.input_per_mtok_micros == 150000

    def test_provider_case_insensitive(self, tmp_path):
        reg = _registry(tmp_path)
        assert reg.resolve("OpenAI", "GPT-4o").status == "priced"

    def test_cost_micros_integer_math(self, tmp_path):
        reg = _registry(tmp_path)
        quote = reg.resolve("openai", "gpt-4o-mini")
        # 2 Mio Input * 0.15 USD + 1 Mio Output * 0.60 USD = 0.90 USD = 900_000 micros
        assert quote.cost_micros(2_000_000, 1_000_000) == 900_000


class TestFreeAndUnknown:
    def test_local_ollama_is_free(self, tmp_path):
        reg = _registry(tmp_path)
        quote = reg.resolve("ollama", "qwen3:8b", "http://localhost:11434")
        assert quote.status == "free"
        assert quote.cost_micros(10**9, 10**9) == 0

    def test_local_loopback_without_provider_is_free(self, tmp_path):
        reg = _registry(tmp_path)
        quote = reg.resolve(None, "anything", "http://127.0.0.1:8080")
        assert quote.status == "free"

    def test_cloud_model_without_table_is_unknown_not_zero(self, tmp_path):
        reg = _registry(tmp_path)
        quote = reg.resolve("openai", "gpt-99-turbo")
        assert quote.status == "unknown"
        assert quote.cost_micros(1000, 1000) is None

    def test_remote_ollama_cloud_is_not_free(self, tmp_path):
        reg = _registry(tmp_path)
        quote = reg.resolve("ollama", "qwen3:cloud", "https://ollama.com")
        assert quote.status == "unknown"

    def test_missing_pricing_file_yields_unknown(self, tmp_path):
        reg = PricingRegistry(data_path=tmp_path / "does-not-exist.json")
        quote = reg.resolve("openai", "gpt-4o")
        assert quote.status == "unknown"
        assert quote.pricing_version == "unknown"


class TestBundledPricingData:
    def test_bundled_file_loads_and_covers_common_providers(self):
        reg = PricingRegistry()
        assert reg.pricing_version != "unknown"
        assert reg.resolve("openai", "gpt-4o").status == "priced"
        assert reg.resolve("google", "gemini-2.5-flash").status == "priced"
        assert reg.resolve("ollama", "qwen3:8b", "http://localhost:11434").status == "free"
