import pytest
from app.llm.context import heuristic_num_ctx_for_model

def test_heuristic_empty_model():
    """Test that an empty model name returns None."""
    assert heuristic_num_ctx_for_model("") is None
    assert heuristic_num_ctx_for_model(None) is None

def test_heuristic_unknown_model():
    """Test that an unknown model returns None."""
    assert heuristic_num_ctx_for_model("unknown-model-xyz") is None
    assert heuristic_num_ctx_for_model("random-123") is None

def test_heuristic_exact_match():
    """Test exact matches from the heuristic table."""
    assert heuristic_num_ctx_for_model("gemini-3") == 1_048_576
    assert heuristic_num_ctx_for_model("deepseek-v3") == 131_072
    assert heuristic_num_ctx_for_model("nemotron") == 131_072

def test_heuristic_substring_match_and_case_insensitive():
    """Test substring matches and case insensitivity."""
    # Substring matches
    assert heuristic_num_ctx_for_model("my-gemini-3-pro") == 1_048_576
    assert heuristic_num_ctx_for_model("qwen3-coder:latest") == 262_144

    # Case insensitivity
    assert heuristic_num_ctx_for_model("GEMINI-3") == 1_048_576
    assert heuristic_num_ctx_for_model("DeepSeek-R1:32b") == 131_072
    assert heuristic_num_ctx_for_model("LLAMA-3.3-70B") == 131_072
