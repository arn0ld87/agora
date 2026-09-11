from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "backend" / "app" / "services"
FACADE = SERVICE_DIR / "simulation_config_generator.py"

MODEL_IMPORT = '''from .simulation_config_models import (
    AgentActivityConfig as AgentActivityConfig,
    EventConfig as EventConfig,
    PlatformConfig as PlatformConfig,
    SimulationParameters as SimulationParameters,
    TimeSimulationConfig as TimeSimulationConfig,
)
'''

HELPER_IMPORTS = '''from . import simulation_config_context as _simulation_config_context
from . import simulation_config_llm as _simulation_config_llm
from . import simulation_config_time as _simulation_config_time
from . import simulation_config_events as _simulation_config_events
from . import simulation_config_agents as _simulation_config_agents
'''


def move_facade_imports() -> None:
    text = FACADE.read_text(encoding="utf-8")
    for block, label in ((MODEL_IMPORT, "model import"), (HELPER_IMPORTS, "helper imports")):
        if text.count(block) != 1:
            raise SystemExit(f"expected exactly one {label} block")
        text = text.replace(block, "", 1)

    marker = 'logger = get_logger("agora.simulation_config")\n'
    if marker not in text:
        raise SystemExit("logger marker not found in generated facade")

    imports = MODEL_IMPORT + HELPER_IMPORTS + "\n"
    text = text.replace(marker, imports + marker, 1)
    FACADE.write_text(text, encoding="utf-8")


def restore_intentional_broad_catch_noqa() -> None:
    replacements = {
        "simulation_config_agents.py": (
            "except Exception as e:\n",
            "except Exception as e:  # noqa: BLE001 — logged and intentionally converted to rule-based fallback\n",
        ),
        "simulation_config_events.py": (
            "except Exception as e:\n",
            "except Exception as e:  # noqa: BLE001 — logged and intentionally converted to default config\n",
        ),
        "simulation_config_time.py": (
            "except Exception as e:\n",
            "except Exception as e:  # noqa: BLE001 — logged and intentionally converted to default config\n",
        ),
        "simulation_config_llm.py": (
            "except Exception as fallback_err:\n",
            "except Exception as fallback_err:  # noqa: BLE001 — transport errors are already internally retried\n",
        ),
    }

    for filename, (old, new) in replacements.items():
        path = SERVICE_DIR / filename
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise SystemExit(f"expected exactly one broad catch in {filename}, found {text.count(old)}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    move_facade_imports()
    restore_intentional_broad_catch_noqa()
    for path in [FACADE, *SERVICE_DIR.glob("simulation_config_*.py")]:
        ast.parse(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
