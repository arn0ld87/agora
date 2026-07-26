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
import subprocess
import sys
from pathlib import Path

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

# Im Subprozess von ``test_fixture_actually_scrubs_a_preseeded_token`` gesetzt,
# damit dieser Test sich dort nicht selbst erneut startet.
_SUBPROCESS_MARKER = "_AGORA_HERMETICITY_SUBPROCESS"

# Kein echtes Secret — nur ein Wert, dessen Verschwinden beobachtbar ist.
PROBE_TOKEN = "probe-token-not-a-real-secret"  # noqa: S105


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


@pytest.mark.skipif(
    os.environ.get(_SUBPROCESS_MARKER) == "1",
    reason="Läuft im Subprozess dieses Tests — würde sich sonst rekursiv starten.",
)
def test_fixture_actually_scrubs_a_preseeded_token() -> None:
    """Wirkungsnachweis: ein *vorbelegter* Token wird vom Fixture entfernt.

    Die beiden Prüfungen darüber reichen nicht aus (Codex-Finding P2 auf PR #895):
    auf CI-Runnern ohne ``.env`` startet ``test_leaky_env_var_is_unset_during_tests``
    mit einem ohnehin abwesenden Token, und die Strukturprüfung sieht nur die
    Registrierung — ein zum No-op ausgehöhlter Fixture-Body bliebe grün.

    Hier wird ``AGORA_AUTH_TOKEN`` deshalb explizit gesetzt und ein pytest im
    Subprozess gestartet. Dessen Test kann nur bestehen, wenn das Fixture den
    vorbelegten Wert tatsächlich überschreibt — unabhängig davon, ob eine ``.env``
    existiert.
    """
    backend_root = Path(root_conftest.__file__).resolve().parent.parent
    env = {
        **os.environ,
        "AGORA_AUTH_TOKEN": PROBE_TOKEN,
        _SUBPROCESS_MARKER: "1",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/contracts/test_suite_hermeticity.py::test_leaky_env_var_is_unset_during_tests",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        cwd=backend_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        "Der Subprozess sah AGORA_AUTH_TOKEN trotz aktivem _clean_auth_token_env. "
        "Das Fixture scrubbt nicht mehr — genau der Zustand, der lokal die "
        "401-Fehlschläge in tests/api erzeugt hat.\n"
        f"--- stdout ---\n{result.stdout[-2000:]}"
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
