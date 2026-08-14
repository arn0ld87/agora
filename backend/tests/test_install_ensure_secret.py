"""Regressionstest: install.sh ensure_secret repariert fehlende Keys.

Defekt: Ältere .env-Dateien hatten AGORA_SECRET_KEY gar nicht als Zeile.
sed fand nichts, der Key blieb ungesetzt — stiller Fehler.
Fix: ensure_secret hängt fehlende Keys an und fail-fastet wenn danach leer.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

INSTALL_SH = Path(__file__).resolve().parents[2] / "install.sh"


def _run_ensure_secret(env_content: str, key: str = "TEST_SECRET") -> str:
    """Ruft ensure_secret aus install.sh in einer Subshell auf und gibt .env zurück."""
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / ".env"
        env_file.write_text(env_content, encoding="utf-8")

        script = f"""
        set -euo pipefail
        cd "{tmp}"
        # Stub die Logging-Funktionen
        info() {{ :; }}
        die() {{ echo "DIE: $*" >&2; exit 1; }}
        # Source nur die ensure_secret-Funktion
        eval "$(sed -n '/^ensure_secret()/,/^}}/p' "{INSTALL_SH}")"
        ensure_secret "{key}"
        """
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            pytest.fail(f"ensure_secret failed: {result.stderr}")
        return env_file.read_text(encoding="utf-8")


@pytest.mark.skipif(not INSTALL_SH.is_file(), reason="install.sh not found")
class TestEnsureSecret:
    def test_fills_empty_value(self) -> None:
        """Key mit leerer Zuweisung wird inplace befüllt."""
        result = _run_ensure_secret("FOO=bar\nTEST_SECRET=\nBAZ=qux\n")
        assert "TEST_SECRET=" in result
        # Wert darf nicht mehr leer sein
        for line in result.splitlines():
            if line.startswith("TEST_SECRET="):
                assert len(line.split("=", 1)[1].strip()) > 10
                break

    def test_appends_missing_key(self) -> None:
        """Key der ganz fehlt wird am Ende angehängt."""
        result = _run_ensure_secret("FOO=bar\nBAZ=qux\n")
        assert "TEST_SECRET=" in result
        lines = [line for line in result.splitlines() if line.startswith("TEST_SECRET=")]
        assert len(lines) == 1
        assert len(lines[0].split("=", 1)[1].strip()) > 10

    def test_idempotent_when_already_set(self) -> None:
        """Bereits gesetzter Key wird nicht überschrieben."""
        result = _run_ensure_secret("TEST_SECRET=existing-value-42\n")
        assert "TEST_SECRET=existing-value-42" in result

    def test_newline_before_append(self) -> None:
        """Wenn .env nicht mit Newline endet, wird eins eingefügt."""
        result = _run_ensure_secret("FOO=bar")  # kein trailing newline
        assert "TEST_SECRET=" in result
        # Kein zusammengeklebtes "FOO=barTEST_SECRET="
        assert "FOO=bar\n" in result or "FOO=bar\r\n" in result
