"""Output-Contract-Konstanten für den Report-Agent (M11.8 Output-Vertrag-Hardening).

Quelle: docu/2026-05-09-output-vertrag-bewertung-evidence-quality.md
- §3 Hauptbefund: 11 Pflichtabschnitte
- §6.1 Fehlende vollständige Persona-Tabelle: 50 Zeilen Pflicht
"""

from __future__ import annotations

# Mindest-Mengengerüst für die Persona-Tabelle eines DACH-Reports.
# Quelle: docu/2026-05-09-output-vertrag-bewertung-evidence-quality.md §6.1
# ("Der Prompt fordert explizit 50 Persona-Zeilen.").
MIN_PERSONA_TABLE_ROWS: int = 50

# Untergrenze für die Simulation-Pool-Größe (OASIS-Agenten). Smaller pools
# erlauben Schnell-Tests mit Mini-Seeds (Smoke-Befund #6 2026-05-15); der
# Report-Pfad skaliert den Persona-Pool danach via Round-Robin auf
# ``MIN_PERSONA_TABLE_ROWS`` hoch (siehe ``_apply_persona_floor_to_entities``).
MIN_SIMULATION_AGENTS: int = 10

__all__ = [
    "MIN_PERSONA_TABLE_ROWS",
    "MIN_SIMULATION_AGENTS",
]
