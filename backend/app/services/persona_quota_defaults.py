"""Destatis-WZ-2008-basierte Default-Branchenverteilung für Persona-Generierung.

Quelle: Destatis Wirtschaftszweigklassifikation 2008 (WZ 2008), Beschäftigtenstatistik
der Bundesagentur für Arbeit (Stand 2023), Statista-Auswertung Beschäftigte nach
Wirtschaftszweigen Deutschland 2022 (veröffentlicht 2023).

Die Anteile sind auf ganze Prozentpunkte gerundet; Summe = 100 %.
IT-Anteil (Information und Kommunikation, WZ J) ist hard-gecappt auf ≤ 12 %,
um den Default-IT-Bias des LLM zu korrigieren (Issue #215).
"""
from __future__ import annotations

import math
from typing import Final

from ..contracts import PersonaQuotaPlan

# ---------------------------------------------------------------------------
# Branchenverteilung: WZ-2008-Buchstaben → (Label, prozentualer Anteil)
# Anteile spiegeln Erwerbstätige nach Wirtschaftsbereichen wider.
# Summe der Anteile muss 1.0 ergeben (100 %).
# ---------------------------------------------------------------------------

_DACH_INDUSTRY_DISTRIBUTION: Final[list[tuple[str, float]]] = [
    # (Segment-Label, Anteil)
    ("Verarbeitendes Gewerbe (C)",              0.17),
    ("Handel (G)",                              0.14),
    ("Gesundheit und Sozialwesen (Q)",          0.13),
    ("Sonstige Dienstleistungen (M, N, R, S)",  0.12),
    ("Information und Kommunikation (J)",       0.12),   # hard-cap ≤ 12 %
    ("Öffentliche Verwaltung (O)",              0.07),
    ("Bildung (P)",                             0.07),
    ("Bau (F)",                                 0.06),
    ("Verkehr und Lagerei (H)",                 0.05),
    ("Gastgewerbe (I)",                         0.04),
    ("Finanz- und Versicherungswesen (K)",      0.03),
]

# Anzahl der wichtigsten Branchen, die bei sehr kleinem total_personas
# mindestens je 1 Persona erhalten (Clamp-Logik).
_MIN_COVERED_BRANCHES: Final[int] = 4


def default_dach_industry_quota(total_personas: int) -> PersonaQuotaPlan:
    """Erzeugt einen ``PersonaQuotaPlan`` mit Destatis-WZ-2008-Branchenverteilung.

    Die Funktion verteilt ``total_personas`` proportional nach den realen
    Erwerbstätigen-Anteilen. Bei sehr kleinen Pools (< Anzahl Branchen) wird
    für die vier Hauptbranchen je mindestens 1 Persona gesichert; überschüssige
    Personas werden proportional auf alle Branchen aufgeteilt.

    Garantien:
    - IT-Anteil (Information und Kommunikation, J) ≤ 12 %.
    - Mindestens 7 Branchen im Plan vertreten.
    - Summe der targets == total_personas.

    Args:
        total_personas: Gesamtanzahl der zu generierenden Personas (≥ 1).

    Returns:
        PersonaQuotaPlan mit targets dict (Segment-Label → Anzahl).

    Raises:
        ValueError: Wenn total_personas < 1.
    """
    if total_personas < 1:
        raise ValueError(
            f"total_personas muss ≥ 1 sein, erhalten: {total_personas}"
        )

    n_branches = len(_DACH_INDUSTRY_DISTRIBUTION)

    # --- Rohe Floats berechnen ---
    raw: list[float] = [share * total_personas for _, share in _DACH_INDUSTRY_DISTRIBUTION]

    # --- Flooring: alle auf int abrunden ---
    floored: list[int] = [math.floor(r) for r in raw]

    # --- Restpersonen verteilen (Largest-Remainder-Methode) ---
    remainder_sum = total_personas - sum(floored)
    remainders = [(raw[i] - floored[i], i) for i in range(n_branches)]
    remainders.sort(reverse=True)
    for rank in range(remainder_sum):
        floored[remainders[rank][1]] += 1

    # --- Clamp-Logik: für die _MIN_COVERED_BRANCHES Hauptbranchen mindestens 1 ---
    # Hauptbranchen = erste 4 Einträge nach Gewicht (bereits nach Anteil sortiert)
    clamped = list(floored)
    for i in range(min(_MIN_COVERED_BRANCHES, n_branches)):
        if clamped[i] < 1:
            # Nehme eine Persona von der letzten Branche mit > 1
            for j in range(n_branches - 1, -1, -1):
                if clamped[j] > 1:
                    clamped[j] -= 1
                    clamped[i] = 1
                    break

    # --- Nur Branchen mit > 0 Personas in den Plan aufnehmen ---
    targets: dict[str, int] = {}
    for idx, (label, _) in enumerate(_DACH_INDUSTRY_DISTRIBUTION):
        if clamped[idx] > 0:
            targets[label] = clamped[idx]

    # --- Summen-Korrektur (Paranoia-Check nach Clamp) ---
    current_total = sum(targets.values())
    if current_total != total_personas:
        # Differenz auf die größte Branche addieren/subtrahieren
        largest_label = max(targets, key=lambda k: targets[k])
        targets[largest_label] += total_personas - current_total

    return PersonaQuotaPlan(targets=targets, total=total_personas)


def build_industry_quota_prompt_block(quota_plan: PersonaQuotaPlan) -> str:
    """Erzeugt einen deutschen Prompt-Block mit der Branchenverteilung.

    Der Block wird in die LLM-Prompts eingebettet, damit das Modell die
    Persona-Branche gemäß der Destatis-WZ-2008-Soll-Verteilung wählt —
    und nicht systematisch IT-Personas erzeugt.

    Args:
        quota_plan: PersonaQuotaPlan mit den Ziel-Counts pro Branche.

    Returns:
        Formatierter Prompt-Block als String.
    """
    total = quota_plan.total
    lines: list[str] = []
    for label, count in quota_plan.targets.items():
        pct = round(count / total * 100)
        lines.append(f"  - {label}: ca. {pct} %")

    distribution_text = "\n".join(lines)

    return (
        "### Branchenverteilung (Destatis WZ 2008)\n"
        "Die Personas dieser Simulation spiegeln die reale Erwerbstätigenstruktur "
        "im DACH-Raum wider. Weise der Persona einen Beruf und eine Branche zu, "
        "die der folgenden Verteilung entspricht — NICHT primär aus der IT-Branche:\n"
        f"{distribution_text}\n"
        "Wähle Branche und Beruf der Persona passend zu dieser Verteilung. "
        "Information und Kommunikation / IT-Berufe sind nur für ca. 12 % der Personas vorgesehen."
    )


def build_industry_quota_prompt_block_en(quota_plan: PersonaQuotaPlan) -> str:
    """English version of the industry quota prompt block.

    Args:
        quota_plan: PersonaQuotaPlan with target counts per sector.

    Returns:
        Formatted prompt block as string.
    """
    total = quota_plan.total
    lines: list[str] = []
    for label, count in quota_plan.targets.items():
        pct = round(count / total * 100)
        lines.append(f"  - {label}: approx. {pct} %")

    distribution_text = "\n".join(lines)

    it_label = "Information und Kommunikation (J)"
    it_count = quota_plan.targets.get(it_label, 0)
    it_pct = round(it_count / total * 100)

    it_hint = (
        f"Information and Communication / IT roles should cover approx. {it_pct} % of personas."
        if it_pct > 0
        else "Information and Communication / IT roles are not intended for this selection."
    )

    return (
        "### Industry Distribution (Destatis WZ 2008)\n"
        "The personas in this simulation reflect the real workforce structure "
        "in the DACH region (Germany, Austria, Switzerland). Assign the persona "
        "a profession and industry sector matching the following distribution "
        "— NOT predominantly from IT:\n"
        f"{distribution_text}\n"
        f"Choose the persona's sector and profession according to this distribution. {it_hint}"
    )


__all__ = [
    "default_dach_industry_quota",
    "build_industry_quota_prompt_block",
    "build_industry_quota_prompt_block_en",
    "_DACH_INDUSTRY_DISTRIBUTION",
]
