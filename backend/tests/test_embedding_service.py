from unittest.mock import patch

import pytest

from app.config import Config, infer_vector_dim_for_model
from app.llm.providers.registry import detect_embedding_provider
from app.storage.embedding_service import EmbeddingError, EmbeddingService, validate_embedding_configuration


@pytest.mark.parametrize(
    ("base_url", "model"),
    [
        ("http://localhost:11434/v1", "nomic-embed-text"),
        ("http://localhost:11434", "nomic-embed-text"),
        ("https://api.openai.com", "text-embedding-3-small"),
        ("http://localhost:11434", "text-embedding-3-small"),
    ],
)
def test_detect_provider_delegates_to_registry_ssot(base_url, model):
    """Issue #671 — EmbeddingService._detect_provider MUSS byte-genau das
    liefern, was detect_embedding_provider() (SSoT-Registry) liefert. Kein
    lokal divergentes Verhalten mehr."""
    service = EmbeddingService(model=model, base_url=base_url, api_key='dummy-key')
    assert service._detect_provider() == detect_embedding_provider(base_url, model)


def test_infer_vector_dim_for_known_models():
    assert infer_vector_dim_for_model('nomic-embed-text') == 768
    assert infer_vector_dim_for_model('nomic-embed-text:latest') == 768
    assert infer_vector_dim_for_model('qwen3-embedding:4b') == 2560
    assert infer_vector_dim_for_model('qwen3-embedding:8b') == 4096


def test_validate_embedding_configuration_rejects_known_dim_mismatch():
    with pytest.raises(EmbeddingError, match='VECTOR_DIM=768 does not match known dimension 2560'):
        validate_embedding_configuration(
            model='qwen3-embedding:4b',
            vector_dim=768,
            base_url='http://localhost:11434',
        )


def test_validate_embedding_configuration_rejects_runtime_dim_mismatch():
    with patch('app.storage.embedding_service.EmbeddingService.embed', return_value=[0.0] * 2560):
        with pytest.raises(EmbeddingError, match='returned dimension 2560, but VECTOR_DIM is configured as 768'):
            validate_embedding_configuration(
                model='custom-embed-model',
                vector_dim=768,
                base_url='http://localhost:11434',
            )


def test_validate_embedding_configuration_returns_actual_dimension_on_success():
    with patch('app.storage.embedding_service.EmbeddingService.embed', return_value=[0.0] * 2560):
        actual_dim = validate_embedding_configuration(
            model='qwen3-embedding:4b',
            vector_dim=2560,
            base_url='http://localhost:11434',
        )

    assert actual_dim == 2560


def test_validate_embedding_configuration_skip_probe_returns_none():
    """When skip_probe=True, no network call is made and None is returned."""
    with patch('app.storage.embedding_service.EmbeddingService.embed') as mock_embed:
        result = validate_embedding_configuration(
            model='qwen3-embedding:4b',
            vector_dim=2560,
            base_url='http://nonexistent:11434',
            skip_probe=True,
        )
    assert result is None
    mock_embed.assert_not_called()


def test_validate_embedding_configuration_skip_probe_still_rejects_known_dim_mismatch():
    """skip_probe must not bypass the static KNOWN_EMBEDDING_DIMS check."""
    with pytest.raises(EmbeddingError, match='VECTOR_DIM=768 does not match known dimension 2560'):
        validate_embedding_configuration(
            model='qwen3-embedding:4b',
            vector_dim=768,
            base_url='http://nonexistent:11434',
            skip_probe=True,
        )


def test_validate_embedding_configuration_default_still_probes():
    """Default behavior (skip_probe omitted/False) preserves the network probe."""
    with patch('app.storage.embedding_service.EmbeddingService.embed', return_value=[0.0] * 768) as mock_embed:
        result = validate_embedding_configuration(
            model='nomic-embed-text',
            vector_dim=768,
            base_url='http://localhost:11434',
        )
    assert result == 768
    mock_embed.assert_called_once()


# ---------------------------------------------------------------------------
# Stub-Modus Tests (AGORA_E2E_LLM_MODE=stub)
# ---------------------------------------------------------------------------

class TestEmbeddingServiceStubMode:
    """EmbeddingService im Stub-Modus liefert deterministischen Vector ohne Netzwerk."""

    def test_stub_embed_returns_correct_dimension(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """embed() im Stub-Modus liefert Vector mit len == Config.VECTOR_DIM."""
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        EmbeddingService._stub_mode_logged = False  # Zustand zurücksetzen

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")
        vec = svc.embed("hallo welt")

        assert len(vec) == Config.VECTOR_DIM, (
            f"Stub-Vector muss dim={Config.VECTOR_DIM} haben, war {len(vec)}"
        )

    def test_stub_embed_is_deterministic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """embed() im Stub-Modus ist bytewise deterministisch (gleicher Text → gleicher Vector)."""
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        EmbeddingService._stub_mode_logged = False

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")
        v1 = svc.embed("deterministic text")
        v2 = svc.embed("deterministic text")

        assert v1 == v2, "Gleicher Text muss gleichen Stub-Vector liefern"

    def test_stub_embed_different_texts_produce_different_vectors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """embed() im Stub-Modus liefert verschiedene Vektoren für verschiedene Texte.

        Verhindert, dass Cosine-Similarity konstant 1.0 ist und Section-Dedup-Fehler
        verschleiert werden.
        """
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        EmbeddingService._stub_mode_logged = False

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")
        v1 = svc.embed("text alpha")
        v2 = svc.embed("text beta")

        assert v1 != v2, "Verschiedene Texte müssen verschiedene Stub-Vektoren liefern"

    def test_stub_embed_batch_returns_correct_count_and_dimension(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """embed_batch() im Stub-Modus liefert Liste mit korrekter Länge und Dimension."""
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        EmbeddingService._stub_mode_logged = False

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")
        batch = svc.embed_batch(["a", "b", "c"])

        assert len(batch) == 3
        for vec in batch:
            assert len(vec) == Config.VECTOR_DIM, (
                f"Stub-Batch-Vector muss dim={Config.VECTOR_DIM} haben, war {len(vec)}"
            )

    def test_stub_health_check_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """health_check() im Stub-Modus gibt True ohne Netzwerkaufruf."""
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")
        assert svc.health_check() is True

    def test_stub_no_network_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Im Stub-Modus wird _request_embeddings() niemals aufgerufen."""
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        EmbeddingService._stub_mode_logged = False

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")

        with patch.object(svc, "_request_embeddings") as mock_req:
            svc.embed("kein netzwerk bitte")
            svc.embed_batch(["a", "b"])
            mock_req.assert_not_called()

    def test_stub_vector_is_l2_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Stub-Vector ist L2-normiert (|v|₂ ≈ 1.0)."""
        import math
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        EmbeddingService._stub_mode_logged = False

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")
        vec = svc.embed("normalization test")

        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 1e-9, f"Stub-Vector ist nicht L2-normiert: |v|₂={norm}"
