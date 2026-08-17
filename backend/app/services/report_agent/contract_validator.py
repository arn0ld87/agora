"""Output-Contract-Validator fuer den Report-Agent (Sub-Slice P1.1).

Quelle: PLAN.md §2.1 — Pflichtabschnitt-Validator.
"""
from __future__ import annotations


def validate_required_sections(
    outline_titles: list[str],
    required: list[str],
) -> list[str]:
    """Liefert fehlende Section-Titel, case-insensitive und whitespace-tolerant."""
    have = {t.strip().casefold() for t in outline_titles if t and t.strip()}
    return [t for t in required if t.strip().casefold() not in have]


def matches_known_preset(outline_titles: list[str]) -> bool:
    """True, wenn die Outline einem bekannten Intent-Preset entspricht.

    Ein Opinion- oder Risk-Report hat bewusst nicht die elf Pflichtabschnitte
    des Full-Reports. Ohne diese Prüfung scheitert jede Outline eines
    kompakten Presets am Pflichtabschnitt-Validator, und der Report wird leer.

    Die Prüfung ist absichtlich streng: die Outline muss *alle* Titel genau
    eines Presets enthalten. Eine beliebige Kurz-Outline besteht sie nicht —
    der Full-Report bleibt damit gegen versehentliche Verkürzung geschützt.

    Einzige Lockerung ist die abschließende Handlungsempfehlung (#1322): sie
    kam nachträglich in die Presets, und Outlines, die davor geplant und
    persistiert wurden, tragen sie nicht. Ohne diese Ausnahme scheitert so ein
    Bestandsreport beim Resume am Full-Report-Pflichtsatz und endet als
    ``incomplete``, obwohl seine Outline zum Planungszeitpunkt korrekt war.
    """
    from ..report_intent import INTENT_SECTION_PRESETS  # noqa: PLC0415 — zyklischer Import
    from ..report_prompts import RECOMMENDATION_SECTION_TITLE  # noqa: PLC0415 — s. o.

    for preset in INTENT_SECTION_PRESETS.values():
        preset_titles = [title for title, _description in preset]
        if not validate_required_sections(outline_titles, preset_titles):
            return True
        legacy_titles = [
            title for title in preset_titles if title != RECOMMENDATION_SECTION_TITLE
        ]
        if len(legacy_titles) == len(preset_titles):
            continue  # Preset ohne Empfehlung — nichts zu lockern
        if not validate_required_sections(outline_titles, legacy_titles):
            return True
    return False


__all__ = ["matches_known_preset", "validate_required_sections"]
