"""Evidence-Map-Migration v1 -> v2.

Sub-Slice 02a — Refs #107.

Hebt persistierte Evidence-Maps beim Laden auf das aktuelle Schema, ohne
sie semantisch umzuformen. Mehr (Pydantic-Boundary-Validation) folgt in
Sub-Slice 02b/02c.
"""

from __future__ import annotations

from typing import Optional

CURRENT_SCHEMA_VERSION = 2


def migrate_v1_to_v2(raw: Optional[dict]) -> Optional[dict]:
    """Hebt eine persistierte Evidence-Map auf schema_version=2.

    - ``None`` und bereits auf v2 stehende Maps werden unverändert zurückgegeben.
    - Mutiert das übergebene Dict in-place (entspricht dem Plan-Snippet aus
      PLAN.md Teil D.2) und reicht es zurück, damit Caller wahlweise
      Rückgabewert oder Original verwenden können.
    - Section-Einträge erben ``schema_version`` auf v2.
    """
    if raw is None:
        return None
    if raw.get("schema_version") == CURRENT_SCHEMA_VERSION:
        return raw

    raw["schema_version"] = CURRENT_SCHEMA_VERSION
    sections = raw.get("sections") or []
    for section in sections:
        if isinstance(section, dict):
            section["schema_version"] = CURRENT_SCHEMA_VERSION
    return raw
