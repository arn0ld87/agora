"""Belegt, dass die Upstream-Warnfilter aus ``pyproject.toml`` eng bleiben.

Issue #1090 (E8 aus #979): Die ``filterwarnings``-Einträge dürfen nur die
nachweislich aus Fremdcode stammenden Warnungen dämpfen — Nachricht UND
Modul, nie eine ganze Kategorie. Diese Tests nageln beide Richtungen fest:
projekteigene Verwerfungswarnungen bleiben sichtbar und gate-fähig, und
selbst die gefilterte Nachricht bleibt sichtbar, wenn sie aus einem anderen
Modul kommt.
"""

from __future__ import annotations

import warnings

import pytest


def test_project_deprecation_warnings_stay_visible_and_gateable():
    """Eine projekteigene DeprecationWarning wird weiterhin gefangen.

    Wäre ein Filter versehentlich auf die ganze Kategorie geraten, liefe
    ``pytest.warns`` hier ins Leere und der Test schlüge fehl — genau der
    Schaden, den Issue #1090 verhindern soll.
    """
    with pytest.warns(DeprecationWarning, match="agora-eigene Verwerfung"):
        warnings.warn("agora-eigene Verwerfung: bitte X statt Y", DeprecationWarning, stacklevel=1)


def test_filtered_message_from_other_module_stays_visible(recwarn):
    """Die gefilterte Nachricht bleibt sichtbar, wenn sie NICHT aus dem
    gefilterten Upstream-Modul stammt.

    Der Filter für ``'asyncio.iscoroutinefunction' is deprecated`` ist auf
    ``pytest_asyncio.plugin`` bzw. ``neo4j._meta`` eingegrenzt. Dieselbe
    Nachricht aus diesem Testmodul darf er nicht schlucken — sonst wäre er
    faktisch ein Nachrichts-Globalfilter.
    """
    warnings.warn(
        "'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16",
        DeprecationWarning,
        stacklevel=1,
    )
    assert len(recwarn) == 1
    assert recwarn[0].category is DeprecationWarning
