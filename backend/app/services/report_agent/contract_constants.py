"""Output-Contract-Konstanten für den Report-Agent (M11.8 Output-Vertrag-Hardening).

Quelle: docs/2026-05-09-output-vertrag-bewertung-evidence-quality.md
- §3 Hauptbefund: 11 Pflichtabschnitte
- §6.1 Fehlende vollständige Persona-Tabelle: Zeilen-Mindestgerüst (früher 50)
"""

from __future__ import annotations

# Mindest-Mengengerüst für die Persona-Tabelle eines DACH-Reports.
# Ursprünglich 50 Zeilen aus docs/2026-05-09-output-vertrag-bewertung-evidence-quality.md §6.1.
# Senkung auf 20 (Sub-Slice persona-floor-20, 2026-08-12): praktische Läufe mit
# kleineren DACH-Seed-Dokumenten erreichen nach Eligibility/Dedup häufig nur
# ~40 elige Personas, scheiterten damit am harten 50er-Gate, ohne dass der
# Report inhaltlich nicht erstellbar wäre. 20 hält eine statistisch noch
# belastbare Untergrenze, lässt aber dokumenttreue Runs durch. Ein kleineres
# ``max_agents`` kann den Floor weiter senken (Nutzer-Wunsch schlägt Contract,
# siehe prepare_service.py); ``min(floor, MIN_PERSONA_TABLE_ROWS)`` bleibt die
# harte Obergrenze.
MIN_PERSONA_TABLE_ROWS: int = 20

# Untergrenze für die Simulation-Pool-Größe (OASIS-Agenten). Smaller pools
# erlauben Schnell-Tests mit Mini-Seeds (Smoke-Befund #6 2026-05-15); der
# Report-Pfad skaliert den Persona-Pool danach via Round-Robin auf
# ``MIN_PERSONA_TABLE_ROWS`` hoch (siehe ``_apply_persona_floor_to_entities``).
MIN_SIMULATION_AGENTS: int = 10

__all__ = [
    "MIN_PERSONA_TABLE_ROWS",
    "MIN_SIMULATION_AGENTS",
]
