"""Regressionstest: install.sh ensure_secret repariert fehlende/platzhalter Keys.

Defekt 1 (aeltere Version): Aeltere .env-Dateien hatten AGORA_SECRET_KEY gar
nicht als Zeile. sed fand nichts, der Key blieb ungesetzt — stiller Fehler.
Fix: ensure_secret haengt fehlende Keys an und fail-fastet wenn danach leer.

Defekt 2 (Tech-Review 2026-09-07, Slice 8, Falle F1): ``.env.example``
enthaelt NICHT-LEERE Platzhalter (``SECRET_KEY=change-me-use-token_urlsafe-32``,
``NEO4J_PASSWORD=change-me``). Der alte ensure_secret-Fruehausstieg
(``grep -qE "^KEY=[^[:space:]]+"``) haelt einen Platzhalter fuer "gesetzt"
und tut im Host-Modus nichts. Fix: Platzhalter werden wie ungesetzt
behandelt (Bash-Kopie der Python-frozensets aus ``app.config``).

Defekt 3 (Falle F2): ``AGORA_SECRET_KEY``/``AGORA_FERNET_KEY`` muessen
gueltige Fernet-Keys sein — ``secrets.token_urlsafe(32)`` ist es nicht.
Fix: key-abhaengiger Generator, fuer diese beiden Keys per
``base64.urlsafe_b64encode(os.urandom(32))`` (== ``Fernet.generate_key()``,
aber ohne ``cryptography``-Abhaengigkeit zum Installationszeitpunkt).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import pytest

INSTALL_SH = Path(__file__).resolve().parents[2] / "install.sh"


def _extract_ensure_secret_source() -> str:
    """Extrahiert ENSURE_SECRET_PLACEHOLDERS + ensure_secret() aus install.sh.

    Beide gehoeren zusammen: ensure_secret() referenziert das Array. Der
    Bereich beginnt bei der Array-Definition und endet an der ersten
    Zeile, die nur aus ``}`` besteht (dem Ende der Funktion).
    """
    result = subprocess.run(
        ["sed", "-n", "/^ENSURE_SECRET_PLACEHOLDERS=/,/^}/p", str(INSTALL_SH)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    source = result.stdout
    assert "ENSURE_SECRET_PLACEHOLDERS=(" in source, "Array-Definition nicht gefunden"
    assert "ensure_secret() {" in source, "Funktionsdefinition nicht gefunden"
    return source


def _run_bash_snippet(
    tmp: str,
    body: str,
    *,
    extra_path: str | None = None,
    timeout: float = 10,
) -> subprocess.CompletedProcess[str]:
    path_prefix = f'export PATH="{extra_path}:$PATH"\n        ' if extra_path else ""
    source = _extract_ensure_secret_source()
    script = f"""
    set -euo pipefail
    {path_prefix}cd "{tmp}"
    # Stub die Logging-Funktionen
    info() {{ :; }}
    die() {{ echo "DIE: $*" >&2; exit 1; }}
    {source}
    {body}
    """
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_ensure_secret(env_content: str, key: str = "TEST_SECRET") -> str:
    """Ruft ensure_secret aus install.sh in einer Subshell auf und gibt .env zurück."""
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / ".env"
        env_file.write_text(env_content, encoding="utf-8")
        result = _run_bash_snippet(tmp, f'ensure_secret "{key}"')
        if result.returncode != 0:
            pytest.fail(f"ensure_secret failed: {result.stderr}")
        return env_file.read_text(encoding="utf-8")


def _value_of(env_text: str, key: str) -> str | None:
    for line in env_text.splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


@pytest.mark.skipif(not INSTALL_SH.is_file(), reason="install.sh not found")
class TestEnsureSecret:
    def test_fills_empty_value(self) -> None:
        """Key mit leerer Zuweisung wird inplace befüllt."""
        result = _run_ensure_secret("FOO=bar\nTEST_SECRET=\nBAZ=qux\n")
        assert "TEST_SECRET=" in result
        # Wert darf nicht mehr leer sein
        value = _value_of(result, "TEST_SECRET")
        assert value is not None and len(value) > 10

    def test_appends_missing_key(self) -> None:
        """Key der ganz fehlt wird am Ende angehängt."""
        result = _run_ensure_secret("FOO=bar\nBAZ=qux\n")
        lines = [line for line in result.splitlines() if line.startswith("TEST_SECRET=")]
        assert len(lines) == 1
        assert len(lines[0].split("=", 1)[1].strip()) > 10

    def test_idempotent_when_already_set(self) -> None:
        """Bereits gesetzter (Nicht-Platzhalter-)Key wird nicht überschrieben."""
        result = _run_ensure_secret("TEST_SECRET=existing-value-42\n")
        assert "TEST_SECRET=existing-value-42" in result

    def test_newline_before_append(self) -> None:
        """Wenn .env nicht mit Newline endet, wird eins eingefügt."""
        result = _run_ensure_secret("FOO=bar")  # kein trailing newline
        assert "TEST_SECRET=" in result
        # Kein zusammengeklebtes "FOO=barTEST_SECRET="
        assert "FOO=bar\n" in result or "FOO=bar\r\n" in result


@pytest.mark.skipif(not INSTALL_SH.is_file(), reason="install.sh not found")
class TestEnsureSecretPlaceholders:
    """F1: bekannte Platzhalter werden wie ungesetzt behandelt."""

    @pytest.mark.parametrize(
        "placeholder",
        ["change-me", "change-me-use-token_urlsafe-32", "agora", "AGORA", "password", "neo4j"],
    )
    def test_replaces_known_placeholder(self, placeholder: str) -> None:
        result = _run_ensure_secret(f"TEST_SECRET={placeholder}\n")
        value = _value_of(result, "TEST_SECRET")
        assert value is not None
        assert value.lower() != placeholder.lower()
        assert len(value) > 10

    def test_placeholder_list_matches_config(self) -> None:
        """Drift-Guard: die Bash-Kopie der Platzhalter (install.sh) muss exakt
        der Vereinigung aus SECRET_KEY_PLACEHOLDERS und
        NEO4J_PASSWORD_PLACEHOLDERS (app.config) entsprechen. Ohne diesen Test
        driftet die Zweitkopie garantiert auseinander — install.sh kann die
        Python-Konstanten nicht importieren, weil es vor der
        Dependency-Installation laeuft."""
        from app.config import NEO4J_PASSWORD_PLACEHOLDERS, SECRET_KEY_PLACEHOLDERS

        text = INSTALL_SH.read_text(encoding="utf-8")
        match = re.search(r"^ENSURE_SECRET_PLACEHOLDERS=\(([^)]*)\)", text, re.MULTILINE)
        assert match, "ENSURE_SECRET_PLACEHOLDERS-Array nicht in install.sh gefunden"
        bash_values = set(match.group(1).split())
        expected = SECRET_KEY_PLACEHOLDERS | NEO4J_PASSWORD_PLACEHOLDERS
        assert bash_values == expected, (
            f"Bash-Platzhalterliste driftet von app.config ab: "
            f"bash={bash_values} config={expected}"
        )

    def test_final_placeholder_guard_dies(self) -> None:
        """Verteidigungs-Check: bleibt nach der Generierung (z. B. durch einen
        kaputten Generator) ein bekannter Platzhalter stehen, bricht
        ensure_secret hart mit klarer Meldung ab statt eine kaputte .env
        durchzureichen (Auftragspunkt: 'Nach setup_env bricht install.sh mit
        klarer Meldung ab, wenn noch ein Platzhalter steht')."""
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("TEST_SECRET=change-me\n", encoding="utf-8")

            fake_bin = Path(tmp) / "fakebin"
            fake_bin.mkdir()
            fake_python3 = fake_bin / "python3"
            fake_python3.write_text("#!/bin/sh\necho agora\n", encoding="utf-8")
            fake_python3.chmod(0o755)

            result = _run_bash_snippet(
                tmp, 'ensure_secret "TEST_SECRET"', extra_path=str(fake_bin)
            )
            assert result.returncode != 0, (
                "ensure_secret haette abbrechen muessen, lief aber durch: "
                f"stdout={result.stdout!r} env={env_file.read_text()!r}"
            )
            assert "DIE:" in result.stderr
            assert "Platzhalter" in result.stderr


@pytest.mark.skipif(not INSTALL_SH.is_file(), reason="install.sh not found")
class TestEnsureSecretFernetKeys:
    """F2: AGORA_SECRET_KEY/AGORA_FERNET_KEY müssen gültige Fernet-Keys sein."""

    @pytest.mark.parametrize("key", ["AGORA_SECRET_KEY", "AGORA_FERNET_KEY"])
    def test_generates_value_accepted_by_fernet(self, key: str) -> None:
        from cryptography.fernet import Fernet

        result = _run_ensure_secret("FOO=bar\n", key=key)
        value = _value_of(result, key)
        assert value is not None
        # Fernet(...) wirft ValueError bei ungültigem Key-Format — kein
        # Exception heißt: Wert ist akzeptiert. Kein Secret-Wert wird
        # ausgegeben, nur das Ergebnis der Validierung geprüft.
        Fernet(value.encode("utf-8"))


@pytest.mark.skipif(not INSTALL_SH.is_file(), reason="install.sh not found")
class TestEnsureSecretHostMode:
    """F1+F2 kombiniert: Host-Modus-Aufrufreihenfolge aus install.sh."""

    def test_host_mode_generates_all_three_secrets(self) -> None:
        """Simuliert die drei ensure_secret-Aufrufe, die install.sh im
        Host-Modus nach `setup_env ".env.example"` ausführt, gegen die
        echten .env.example-Platzhalter. NEO4J_PASSWORD bleibt im Host-Modus
        bewusst unangetastet (externe Neo4j-Instanz, kein Auto-Secret)."""
        env_content = "SECRET_KEY=change-me-use-token_urlsafe-32\nNEO4J_PASSWORD=change-me\n"
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(env_content, encoding="utf-8")
            body = (
                'ensure_secret "SECRET_KEY"\n'
                '    ensure_secret "AGORA_SECRET_KEY"\n'
                '    ensure_secret "AGORA_FERNET_KEY"'
            )
            result = _run_bash_snippet(tmp, body)
            assert result.returncode == 0, result.stderr
            content = env_file.read_text(encoding="utf-8")

            from cryptography.fernet import Fernet

            for key in ("SECRET_KEY", "AGORA_SECRET_KEY", "AGORA_FERNET_KEY"):
                lines = [line for line in content.splitlines() if line.startswith(f"{key}=")]
                assert len(lines) == 1, f"{key} sollte genau einmal vorkommen"
                value = lines[0].split("=", 1)[1].strip()
                assert len(value) > 10
                assert value.lower() not in {"change-me", "change-me-use-token_urlsafe-32"}

            for key in ("AGORA_SECRET_KEY", "AGORA_FERNET_KEY"):
                value = _value_of(content, key)
                assert value is not None
                Fernet(value.encode("utf-8"))

            # NEO4J_PASSWORD wird im Host-Modus nicht automatisch erzeugt.
            assert "NEO4J_PASSWORD=change-me" in content

    def test_install_sh_host_mode_calls_ensure_secret_for_all_three(self) -> None:
        """Statischer Beleg, dass install.sh im Host-Modus (nicht nur die
        Funktion isoliert im Test oben) tatsächlich alle drei
        ensure_secret-Aufrufe ausführt — sonst bliebe der Verhaltenstest
        oben grün, obwohl die Verdrahtung in install.sh entfernt wurde."""
        text = INSTALL_SH.read_text(encoding="utf-8")
        host_start = text.index('setup_env ".env.example"')
        host_block = text[host_start : host_start + 400]
        assert "ensure_secret SECRET_KEY" in host_block
        assert "ensure_secret AGORA_SECRET_KEY" in host_block
        assert "ensure_secret AGORA_FERNET_KEY" in host_block

    def test_install_sh_docker_mode_also_ensures_both_master_keys(self) -> None:
        """Der Docker-Modus braucht dieselben zwei Master-Keys wie der Host.

        Ohne ``AGORA_FERNET_KEY`` wirft ``api_keys_persistence.py`` ausserhalb
        des Debug-Modus ``RuntimeError``; ohne ``AGORA_SECRET_KEY`` faellt
        ``llm_provider_secrets_store.py`` beim ersten Zugriff aus. Beide
        fehlten im Docker-Zweig, weil ``.env.docker.example`` sie nie gefuehrt
        hat und der Zweig nur die drei historisch bekannten Keys absicherte.
        """
        text = INSTALL_SH.read_text(encoding="utf-8")
        docker_start = text.index('setup_env ".env.docker.example"')
        docker_block = text[docker_start : text.index('setup_env ".env.example"')]
        for key in (
            "SECRET_KEY",
            "AGORA_AUTH_TOKEN",
            "NEO4J_PASSWORD",
            "AGORA_SECRET_KEY",
            "AGORA_FERNET_KEY",
        ):
            assert f"ensure_secret {key}" in docker_block, (
                f"Docker-Modus sichert {key} nicht ab — eine Docker-Installation "
                "startet damit ohne diesen Pflicht-Key."
            )
