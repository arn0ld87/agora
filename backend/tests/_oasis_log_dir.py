"""Race-freies Anlegen von ``./log`` für den OASIS-Import unter xdist (#1898).

``oasis/social_platform/platform.py`` legt beim Import ``./log`` per
``if not os.path.exists(...): os.makedirs(...)`` an, ohne ``exist_ok``. Unter
``pytest-xdist`` importieren mehrere Worker OASIS gleichzeitig während der
Collection (#1897: ``tests/unit/test_platform_runner_parity.py``), und der
langsamere Worker scheitert mit ``FileExistsError: './log'``. Der Controller
lädt ``tests/conftest.py`` vor dem Start der Worker und legt das Verzeichnis
dort über :func:`ensure_oasis_log_dir` einmal an.
"""

from __future__ import annotations

import os
from pathlib import Path

OASIS_LOG_DIR_NAME = "log"


def ensure_oasis_log_dir(base: str | os.PathLike[str] = ".") -> Path:
    """Legt ``<base>/log`` an; ein bereits vorhandenes Verzeichnis ist kein Fehler."""
    log_dir = Path(base) / OASIS_LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir
