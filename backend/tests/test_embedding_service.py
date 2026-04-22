from unittest.mock import patch

import pytest

from app.config import infer_vector_dim_for_model
from app.storage.embedding_service import EmbeddingError, validate_embedding_configuration


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
