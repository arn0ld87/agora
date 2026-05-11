"""Output-Contract-Konstanten für den Report-Agent (M11.8 Output-Vertrag-Hardening).

Quelle: docs/archive/reviews/2026-05-09-output-vertrag-bewertung-evidence-quality.md
- §3 Hauptbefund: 11 Pflichtabschnitte
- §6.1 Fehlende vollständige Persona-Tabelle: 50 Zeilen Pflicht
"""

from __future__ import annotations

# Mindest-Mengengerüst für die Persona-Tabelle eines DACH-Reports.
# Quelle: docs/archive/reviews/2026-05-09-output-vertrag-bewertung-evidence-quality.md §6.1
# ("Der Prompt fordert explizit 50 Persona-Zeilen.").
MIN_PERSONA_TABLE_ROWS: int = 50

__all__ = [
    "MIN_PERSONA_TABLE_ROWS",
]
