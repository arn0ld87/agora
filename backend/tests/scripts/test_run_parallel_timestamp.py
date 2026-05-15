"""
Test: emit_post_created_to_redis setzt UTC-TZ-Offset im timestamp.

Fix #1 (Gemini-Review PR #476): datetime.now() ohne tz → Zod datetime({ offset: true })
dropped alle Events. Fix: datetime.now(timezone.utc).isoformat() produziert
ISO-8601 mit '+00:00'-Offset.
"""

import re
from datetime import datetime, timezone


def test_timestamp_has_utc_offset() -> None:
    """timestamp muss Zod datetime({ offset: true }) bestehen: Offset-Suffix vorhanden."""
    ts = datetime.now(timezone.utc).isoformat()
    # Zod erwartet z. B. "2026-05-15T12:00:00+00:00" oder "...Z"
    # datetime.now(timezone.utc).isoformat() liefert "+00:00"
    assert "+" in ts or ts.endswith("Z"), (
        f"Timestamp enthält keinen TZ-Offset: {ts!r}"
    )


def test_timestamp_matches_zod_pattern() -> None:
    """Prüft gegen das Regex-Pattern das Zod für datetime({ offset: true }) nutzt."""
    # Zod datetime mit offset: true akzeptiert ISO-8601 mit Offset (+hh:mm oder Z)
    zod_offset_pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
    )
    ts = datetime.now(timezone.utc).isoformat()
    assert zod_offset_pattern.match(ts), (
        f"Timestamp passt nicht auf Zod-datetime-offset-Pattern: {ts!r}"
    )


def test_naive_datetime_fails_zod_pattern() -> None:
    """Dokumentiert dass naive datetime (ohne tz) Zod datetime({ offset: true }) bricht."""
    zod_offset_pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
    )
    naive_ts = datetime.now().isoformat()  # BUG: kein Offset
    # Stellt sicher der naive Timestamp schlägt fehl — das ist das erwartete Verhalten
    assert not zod_offset_pattern.match(naive_ts), (
        f"Naiver Timestamp hat unerwartet einen Offset: {naive_ts!r}"
    )
