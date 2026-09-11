from pathlib import Path

patterns = (
    "backend/app/services/oasis_profile_*.py",
    "backend/app/services/simulation_config_*.py",
)

for pattern in patterns:
    for path in Path(".").glob(pattern):
        text = path.read_text(encoding="utf-8")
        cleaned = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
        path.write_text(cleaned, encoding="utf-8")
