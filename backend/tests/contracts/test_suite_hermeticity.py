"""Hermetik-Verträge der Test-Suite selbst.

Hintergrund: ``app/config.py`` ruft beim Import ``load_dotenv()`` auf und zieht
damit den echten ``AGORA_AUTH_TOKEN`` aus der lokalen ``.env`` prozessweit in
``os.environ``. Zusammen mit den Blueprint-Singletons — ``install_blueprint_guard``
markiert ein Blueprint über ``_agora_guard_installed`` dauerhaft und hängt seinen
``before_request``-Hook an das *Objekt*, nicht an die App — führte das zu 133
reihenfolgenabhängigen Fehlschlägen in ``tests/api``: sobald irgendein Test
``create_app()`` rief, war der Guard permanent auf ``simulation_bp`` & Co. und
jede spätere nackte ``Flask()``-Testapp bekam ``401 auth_required``.

In CI fiel das nie auf, weil dort keine ``.env`` existiert — es traf nur lokale
Läufe und damit genau die Schleife, in der Entwickler arbeiten. Ein Test, der nur
den Ist-Zustand von ``os.environ`` prüft, wäre in CI deshalb grün, auch wenn das
Fixture gelöscht würde. Darum steht hier zusätzlich die strukturelle Prüfung.

Secret-Hygiene: die Assertions vergleichen bewusst über ``bool``/Länge statt über
den Wert — ein nacktes ``assert os.environ[var] == ""`` würde den echten Token
in den pytest-Report schreiben.
"""

from __future__ import annotations

import os

import pytest

import tests.conftest as root_conftest

# Env-Variablen, die aus einer lokalen `.env` in die Suite lecken können und
# deshalb im Root-Conftest pro Test entfernt werden müssen.
SCRUBBED_ENV_VARS = (
    "AGORA_AUTH_TOKEN",
    "LLM_DISABLE_JSON_MODE",
    "LLM_DISABLE_JSON_OBJECT_MODE",
)

# autouse-Fixtures im Root-Conftest, die diese Hermetik herstellen.
HERMETICITY_FIXTURES = (
    "_clean_auth_token_env",
    "_clean_llm_json_mode_env",
)


@pytest.mark.parametrize("var", SCRUBBED_ENV_VARS)
def test_leaky_env_var_is_unset_during_tests(var: str) -> None:
    """Verhaltensaussage: die Variable ist in jedem Test leer.

    Lokal (mit ``.env``) ist das die scharfe Prüfung; in CI ohne ``.env`` ist sie
    trivial erfüllt — dafür greift ``test_hermeticity_fixture_is_autouse``.
    """
    value = os.environ.get(var, "")
    # Nie den Wert assertieren: bei AGORA_AUTH_TOKEN stünde sonst das echte
    # Secret im Failure-Report.
    assert not value, (
        f"{var} ist während des Tests gesetzt (Länge {len(value)}). "
        f"Das Root-Conftest muss die Variable pro Test entfernen — siehe "
        f"Modul-Docstring."
    )


@pytest.mark.parametrize("fixture_name", HERMETICITY_FIXTURES)
def test_hermeticity_fixture_is_autouse(fixture_name: str, request) -> None:
    """Strukturbremse: das Fixture ist für jeden Test aktiv — auch ohne ``.env``.

    Geprüft über ``request.fixturenames``: dieser Test fordert die Fixtures
    nirgends an, sie können also nur über ``autouse=True`` in der Liste stehen.
    Das ist versionsstabiler als das interne ``_pytestfixturefunction``-Attribut,
    das es in pytest 9 nicht mehr gibt.

    Ohne diese Prüfung könnte das Fixture entfernt werden, ohne dass in CI etwas
    rot wird; der Schaden zeigt sich dann erst lokal als reihenfolgenabhängige
    401-Fehlschläge.
    """
    assert hasattr(root_conftest, fixture_name), (
        f"{fixture_name} fehlt in tests/conftest.py. Es hält Env-Leaks aus der "
        f"lokalen .env von der Suite fern — siehe Modul-Docstring."
    )
    assert fixture_name in request.fixturenames, (
        f"{fixture_name} ist nicht mehr autouse. Damit greift die Hermetik nur "
        f"noch für Tests, die es explizit anfordern."
    )


def test_auth_token_scrubbing_is_documented_in_root_conftest() -> None:
    """Das Warum muss am Fixture stehen, nicht nur in diesem Test."""
    doc = root_conftest._clean_auth_token_env.__doc__ or ""
    assert "install_blueprint_guard" in doc, (
        "Der Docstring von _clean_auth_token_env muss die eigentliche Ursache "
        "nennen (Blueprint-Singleton behält den Guard), sonst wirkt das Fixture "
        "wie eine kosmetische Env-Bereinigung und wird beim nächsten Aufräumen "
        "entfernt."
    )
