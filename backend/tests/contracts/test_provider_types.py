import re
from pathlib import Path

from app.contracts.provider_types import ALL_PROVIDER_TYPES


def test_provider_types_include_minimax_and_opencode_go() -> None:
    assert "minimax" in ALL_PROVIDER_TYPES
    assert "opencode_go" in ALL_PROVIDER_TYPES


def test_provider_types_include_bedrock() -> None:
    assert "bedrock" in ALL_PROVIDER_TYPES

def test_no_gemini_literals_in_code():
    """
    Regression gate: Ensure 'gemini' literal is not used for provider identification
    outside of comments, docstrings, and the provider_types.py mapping.
    """
    app_root = Path(__file__).parents[3] / "backend" / "app"

    # Regex to find "gemini" (with quotes)
    gemini_re = re.compile(r'"gemini"')

    forbidden_lines = []

    # Files/directories to skip completely
    skip_files = {"provider_types.py"}

    # Legitimate substrings to allow on a line containing "gemini"
    legitimate_substrings = [
        "fallback_models",
        "gemini-1.5",
        "gemini-3",
        "VISION_MODEL_NAME",
        "normalized_model",
        "LEGACY_GEMINI"
    ]

    for path in app_root.rglob("*.py"):
        if path.name in skip_files:
            continue

        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for i, line in enumerate(lines, 1):
            if gemini_re.search(line):
                # Check for comments: if # appears before "gemini"
                comment_idx = line.find("#")
                gemini_idx = line.find('"gemini"')
                if comment_idx != -1 and comment_idx < gemini_idx:
                    continue

                # Rough docstring check
                if '"""' in line or "'''" in line:
                    continue

                # Check for legitimate usage
                if any(sub in line for sub in legitimate_substrings):
                    continue

                forbidden_lines.append(f"{path.relative_to(app_root.parent)}:{i}: {line.strip()}")

    if forbidden_lines:
        print("\nFound forbidden 'gemini' literals:")
        for fl in forbidden_lines:
            print(fl)
        assert not forbidden_lines, f"Found {len(forbidden_lines)} forbidden 'gemini' literals."
