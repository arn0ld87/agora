import subprocess
from pathlib import Path

def test_no_gemini_literals_in_code():
    """
    Regression gate: Ensure 'gemini' literal is not used for provider identification
    outside of comments, docstrings, and the provider_types.py mapping.
    """
    app_root = Path(__file__).parents[3] / "backend" / "app"

    # Grep for "gemini" in non-comment/non-docstring lines.
    # We exclude provider_types.py because it defines the legacy mapping.
    # We also exclude some specific files that have legitimate model name references or strings.

    cmd = [
        "grep", "-r", "\"gemini\"", str(app_root)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        lines = result.stdout.splitlines()
        forbidden_lines = []
        for line in lines:
            # Exclude comments
            if "#" in line and line.find("#") < line.find("\"gemini\""):
                continue
            # Exclude provider_types.py
            if "provider_types.py" in line:
                continue
            # Exclude docstrings (rough check)
            if "\"\"\"" in line or "'''" in line:
                continue

            # Legitimate uses: model names in lists or env defaults
            if any(x in line for x in [
                "fallback_models",
                "gemini-1.5",
                "gemini-3",
                "VISION_MODEL_NAME",
                "normalized_model",
                "LEGACY_GEMINI"
            ]):
                continue

            forbidden_lines.append(line)

        if forbidden_lines:
            print("\nFound forbidden 'gemini' literals:")
            for fl in forbidden_lines:
                print(fl)
            assert not forbidden_lines, f"Found {len(forbidden_lines)} forbidden 'gemini' literals."
