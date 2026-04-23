"""Small helpers for atomic JSON writes and defensive reads."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any


def write_json_atomic(path: str, payload: Any) -> None:
    """Write JSON atomically so readers never see half-written files."""
    directory = os.path.dirname(path) or '.'
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix='.tmp-json-', suffix='.json', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def read_json_file(path: str, default: Any = None, logger=None, description: str | None = None) -> Any:
    """Read JSON defensively and return ``default`` if the file is missing or unreadable."""
    if not os.path.exists(path):
        return default

    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        if logger:
            target = description or path
            logger.warning(f"Skipping unreadable JSON file {target}: {exc}")
        return default
