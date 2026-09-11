from pathlib import Path

service_dir = Path("backend/app/services")
entities = service_dir / "prepare_entities.py"
facade = service_dir / "prepare_service.py"

text = entities.read_text(encoding="utf-8")
old = "from typing import TYPE_CHECKING, Any, Callable, List, Optional\n"
new = "from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional\n"
if text.count(old) != 1:
    raise SystemExit("prepare_entities typing import not found exactly once")
entities.write_text(text.replace(old, new, 1), encoding="utf-8")

text = facade.read_text(encoding="utf-8")
block = (
    "from . import prepare_llm as _prepare_llm\n"
    "from . import prepare_entities as _prepare_entities\n"
    "from . import prepare_quota as _prepare_quota\n"
)
if text.count(block) != 1:
    raise SystemExit("prepare helper import block not found exactly once")
text = text.replace(block, "", 1)
marker = 'logger = get_logger("agora.prepare")\n'
if marker not in text:
    raise SystemExit("prepare logger marker not found")
text = text.replace(marker, block + "\n" + marker, 1)
facade.write_text(text, encoding="utf-8")
