"""Rollenangabe einer Persona: fehlend ist keine Angabe, kein Wert (Issue #1766).

Profile ohne ``profession`` (Organisations-, Orts- und Kollektiv-Personas)
trugen bisher den Platzhalter ``"Unknown"``. Der ist nicht leer und blockierte
deshalb den vorgesehenen Fallback beim Bilden von ``persona_stakeholder_group``;
im Bericht erschienen 31 verschiedene Akteure als eine Gruppe "Unknown".

Dieses Modul haelt die eine Definition von "fehlend" und die Fallback-Kette
fuer die Stakeholder-Gruppe. ADR-0002 Anker 4 (``cross_stakeholder_for_high``)
zaehlt ueber ``report_contract._role_family_key``: eine nicht-generische
Rollenfamilie hat Vorrang, sonst zaehlt der Gruppentitel. Die Kette hier darf
die Zahl unterscheidbarer Gruppen deshalb nie erhoehen:

* echte Rollenangabe -> unveraendert (zaehlt als ``title:<rolle>``),
* nicht-generische Rollenfamilie -> deren Label; der Validator zaehlt ohnehin
  ``family:<label>`` und ignoriert den Titel,
* sonst genau EIN konstanter Wert (``NO_ROLE_LABEL``). Bewusst nicht der
  Agentenname und nicht ein generischer Typ wie ``Organization``: beides wuerde
  rollenlose Personas im Validator in viele bzw. mehrere "Gruppen" zerlegen,
  waehrend sie heute zu einer kollabieren.
"""

from __future__ import annotations

from typing import Optional

from ..contracts.report_contract import _GENERIC_ENTITY_TYPES

#: Anzeige- und Gruppenwert, wenn weder Rolle noch Rollenfamilie bekannt sind.
NO_ROLE_LABEL = "ohne Rollenangabe"

#: Schreibweisen, die Altbestand und Provider fuer "keine Angabe" verwenden
#: (casefold-Vergleich).
_MISSING_ROLE_VALUES: frozenset[str] = frozenset({"unknown", "unbekannt"})


def _collapse(value: Optional[str]) -> str:
    return " ".join(str(value or "").split())


def normalize_role(value: Optional[str]) -> str:
    """Bereinigte Rollenangabe, ``""`` wenn keine vorliegt.

    Leer, nur Whitespace sowie ``Unknown``/``unbekannt`` (jede Schreibweise)
    gelten als fehlend.
    """
    collapsed = _collapse(value)
    if collapsed.casefold() in _MISSING_ROLE_VALUES:
        return ""
    return collapsed


def display_role(value: Optional[str]) -> str:
    """Rolle fuer Prompts und Berichtstext: nie leer, nie ``Unknown``."""
    return normalize_role(value) or NO_ROLE_LABEL


def resolve_stakeholder_group(
    agent_role: Optional[str], role_family: Optional[str]
) -> str:
    """``persona_stakeholder_group`` einer Persona (Fallback-Kette, siehe Modul)."""
    role = normalize_role(agent_role)
    if role:
        return role
    family = normalize_role(role_family)
    if family and family.casefold() not in _GENERIC_ENTITY_TYPES:
        return family
    return NO_ROLE_LABEL
