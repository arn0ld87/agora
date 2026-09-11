from pathlib import Path
import subprocess

BASE = "4496d7ad425593ec12084e508d3f148be9a4166e"
changed = subprocess.check_output(
    ["git", "diff", "--name-only", BASE, "--", "*.py"],
    text=True,
).splitlines()

for name in changed:
    path = Path(name)
    if not path.exists() or path.suffix != ".py":
        continue
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    cleaned = "\n".join(line.rstrip() for line in lines)
    if text.endswith("\n") or lines:
        cleaned += "\n"
    path.write_text(cleaned, encoding="utf-8")
