from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "backend" / "app" / "services"
GENERATOR = SERVICE_DIR / "oasis_profile_generator.py"

MODEL_IMPORT = """from .oasis_profile_models import (
    CollectivePersonaSchema,
    OasisAgentProfile,
    PersonaDemographicSlot,
    PersonaIneligible,
    PersonaProfileSchema,
)
"""

HELPER_IMPORT_NAMES = [
    "oasis_profile_core",
    "oasis_profile_demographics",
    "oasis_profile_context",
    "oasis_profile_llm",
    "oasis_profile_prompts",
    "oasis_profile_rule_based",
    "oasis_profile_batch_results",
    "oasis_profile_batch",
    "oasis_profile_persistence",
]


def _fix_generator_import_locations() -> None:
    text = GENERATOR.read_text(encoding="utf-8")
    if text.count(MODEL_IMPORT) != 1:
        raise SystemExit("expected exactly one model import block")
    text = text.replace(MODEL_IMPORT, "", 1)

    anchor = "from ..llm.json_mode import _try_repair_truncated_json\n"
    if anchor not in text:
        raise SystemExit("model import anchor not found")
    explicit_reexport = MODEL_IMPORT.replace(
        "    CollectivePersonaSchema,\n",
        "    CollectivePersonaSchema as CollectivePersonaSchema,\n",
    ).replace(
        "    OasisAgentProfile,\n",
        "    OasisAgentProfile as OasisAgentProfile,\n",
    ).replace(
        "    PersonaDemographicSlot,\n",
        "    PersonaDemographicSlot as PersonaDemographicSlot,\n",
    ).replace(
        "    PersonaIneligible,\n",
        "    PersonaIneligible as PersonaIneligible,\n",
    ).replace(
        "    PersonaProfileSchema,\n",
        "    PersonaProfileSchema as PersonaProfileSchema,\n",
    )
    text = text.replace(anchor, anchor + explicit_reexport, 1)

    marker = "# Intentional late imports: helper modules depend on legacy module globals.\n"
    first_helper = f"from . import {HELPER_IMPORT_NAMES[0]} as _{HELPER_IMPORT_NAMES[0]}\n"
    if first_helper not in text:
        raise SystemExit("late helper import block not found")
    text = text.replace(first_helper, marker + first_helper.rstrip() + "  # noqa: E402\n", 1)
    for name in HELPER_IMPORT_NAMES[1:]:
        line = f"from . import {name} as _{name}\n"
        if line not in text:
            raise SystemExit(f"helper import missing: {name}")
        text = text.replace(line, line.rstrip() + "  # noqa: E402\n", 1)

    GENERATOR.write_text(text, encoding="utf-8")


def _fix_helper_imports() -> None:
    for path in SERVICE_DIR.glob("oasis_profile_*.py"):
        if path.name in {"oasis_profile_generator.py", "oasis_profile_models.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        # `Any` is provided locally for the extracted self/cls annotations.
        text = text.replace("    Any,\n", "")
        path.write_text(text, encoding="utf-8")


def _add_forward_type_import(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if '"DegradationCollector"' not in text:
        raise SystemExit(f"expected DegradationCollector annotation in {path.name}")
    text = text.replace(
        "from typing import Any\n",
        "from typing import TYPE_CHECKING, Any\n",
        1,
    )
    legacy_anchor = "from . import oasis_profile_generator as _legacy\n"
    if legacy_anchor in text:
        text = text.replace(
            legacy_anchor,
            legacy_anchor + "\nif TYPE_CHECKING:\n    from .degradation_collector import DegradationCollector\n",
            1,
        )
    else:
        # Some helper groups do not use dynamic legacy globals and Ruff removes
        # the _legacy import. Insert the type-only dependency before other local imports.
        import_anchor = "from .oasis_profile_generator import (\n"
        if import_anchor not in text:
            raise SystemExit(f"no local import anchor in {path.name}")
        text = text.replace(
            import_anchor,
            "if TYPE_CHECKING:\n    from .degradation_collector import DegradationCollector\n\n" + import_anchor,
            1,
        )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    _fix_generator_import_locations()
    _fix_helper_imports()
    _add_forward_type_import(SERVICE_DIR / "oasis_profile_batch.py")
    _add_forward_type_import(SERVICE_DIR / "oasis_profile_rule_based.py")


if __name__ == "__main__":
    main()
