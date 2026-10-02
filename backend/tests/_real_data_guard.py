"""Schreibsperre der Testsuite für die echten Datenverzeichnisse (#1632).

Die Suite hat Run-Manifeste mit Fixture-IDs (``sim_abcdef012345``) in das
echte ``backend/uploads/run_registry/`` auf armserver geschrieben. Die
Isolation über ``tmp_path`` (``tests/conftest.py``) verhindert das für die
bekannten Pfade; dieser Guard sichert ab, dass ein künftiger Test, der an der
Isolation vorbeischreibt, scheitert, statt still echte Daten anzulegen.

Mechanik: ein Audit-Hook (PEP 578, ``sys.addaudithook``) sieht jedes
``open``, ``os.mkdir``, ``os.rename``/``os.replace``, ``os.link``,
``os.symlink``, ``os.remove``, ``os.rmdir``, ``os.truncate`` und
``shutil.rmtree`` im Prozess, auch aus Bibliotheken.
Schreibende Operationen unterhalb eines geschützten Verzeichnisses werfen
:class:`RealDataWriteError`. Weil Anwendungscode Fehler gern mit ``except
Exception`` loggt und weiterläuft, wird jeder Treffer zusätzlich notiert. Der
autouse-Fixture in ``conftest.py`` lässt den Test dann trotzdem scheitern.

Geschützt sind:

- ``backend/uploads`` (der Default von ``Config.UPLOAD_FOLDER``),
- ``backend/data`` (der Fallback von ``resolve_data_dir()``),
- das ``AGORA_DATA_DIR``, das beim Start der Suite in der Umgebung stand.

Die Wurzeln werden aus der Lage dieser Datei berechnet, nicht aus
``Config``. Der Isolations-Fixture biegt ``Config.UPLOAD_FOLDER`` je Test auf
``tmp_path`` um, die Sperre muss aber weiter auf das echte Verzeichnis zeigen.

Grenzen: Kindprozesse (``subprocess``) erben den Hook nicht. Dateien, die
C-Code ohne ``open``-Event anlegt (etwa SQLite über ``sqlite3.connect``),
sieht er nicht. Relative Namen zu einem Verzeichnis-FD (``dir_fd``) prüft er
nicht, weil sich ihr Ort nicht zuverlässig bestimmen lässt.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Iterable

BACKEND_DIR = Path(__file__).resolve().parents[1]

_WRITE_FLAGS = (
    os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
)

_WATCHED_EVENTS = frozenset({
    "open", "os.mkdir", "os.rename", "os.link", "os.symlink", "os.remove",
    "os.rmdir", "shutil.rmtree", "os.truncate",
})


class RealDataWriteError(PermissionError):
    """Ein Test hat versucht, in ein echtes Datenverzeichnis zu schreiben."""


def default_protected_roots(env_data_dir: str | None) -> list[Path]:
    roots = [BACKEND_DIR / "uploads", BACKEND_DIR / "data"]
    if env_data_dir:
        roots.append(Path(env_data_dir).expanduser())
    return roots


def _normalize(path: Path | str) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def _normalize_entry(path: Path | str) -> str:
    """Wie :func:`_normalize`, folgt aber keinem Symlink in der letzten Komponente.

    ``unlink``, ``rmdir``, ``rename`` und ``symlink`` treffen den
    Verzeichniseintrag selbst. Ein Link in tmp, der auf ``backend/uploads``
    zeigt, darf gelöscht werden; nur Schreiben *durch* ihn ist verboten.
    """
    absolute = os.path.abspath(os.fspath(path))
    parent, name = os.path.split(absolute)
    return os.path.normcase(os.path.join(os.path.realpath(parent), name))


class RealDataGuard:
    """Hält die geschützten Wurzeln und die notierten Verstöße.

    Pro Prozess existiert genau eine aktive Instanz (``install``). Audit-Hooks
    lassen sich nicht wieder entfernen; ``armed`` schaltet die Prüfung ab.
    """

    def __init__(self, roots: Iterable[Path | str]):
        self.roots = tuple(sorted({_normalize(r) for r in roots}))
        self.armed = True
        self._violations: list[tuple[str, str, str]] = []
        self._lock = threading.Lock()
        self._local = threading.local()

    # -- Prüfung ---------------------------------------------------------

    def is_protected(self, path: object, *, entry: bool = False) -> bool:
        """``entry=True``: die Operation trifft den Eintrag, nicht das Link-Ziel."""
        if isinstance(path, int) or path is None:
            return False  # Dateideskriptor: Pfad nicht bekannt
        try:
            decoded = os.fsdecode(path)  # type: ignore[arg-type]
            candidate = _normalize_entry(decoded) if entry else _normalize(decoded)
        except (TypeError, ValueError):
            return False
        return any(
            candidate == root or candidate.startswith(root + os.sep)
            for root in self.roots
        )

    @staticmethod
    def _is_write_open(mode: object, flags: object) -> bool:
        if isinstance(mode, str):
            return any(ch in mode for ch in "wax+")
        return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)

    @staticmethod
    def _relative_to_fd(path: object, dir_fd: object) -> bool:
        """Relativer Name zu einem Verzeichnis-FD, nicht zum cwd.

        ``shutil.rmtree`` löscht intern per ``os.unlink(name, dir_fd=…)``. Den
        Namen gegen das cwd aufzulösen, machte aus einem ``data/``-Eintrag in
        einem tmp-Baum ``backend/data``. Solche Events werden übersprungen; das
        Top-Level-Event ``shutil.rmtree`` mit absolutem Pfad deckt echtes
        Löschen weiter ab.
        """
        if dir_fd is None or isinstance(path, int):
            return False
        try:
            return not os.path.isabs(os.fsdecode(path))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False

    def _write_targets(self, event: str, args: tuple) -> tuple[tuple[object, bool], ...]:
        """Liefert ``(Pfad, entry)`` je betroffenem Ziel."""
        padded = tuple(args) + (None, None, None, None)
        if event == "open":
            path, mode, flags = padded[:3]
            return ((path, False),) if self._is_write_open(mode, flags) else ()
        if event == "os.mkdir":
            path, _mode, dir_fd = padded[:3]
            if self._relative_to_fd(path, dir_fd):
                return ()
            # ``os.makedirs(..., exist_ok=True)`` ruft mkdir auch für ein
            # bestehendes Verzeichnis auf. Das schreibt nichts.
            if not isinstance(path, int) and os.path.isdir(os.fsdecode(path)):
                return ()
            return ((path, True),)
        if event in {"os.rename", "os.link"}:
            src, dst, src_fd, dst_fd = padded[:4]
            targets = [] if event == "os.link" else [(src, src_fd)]
            targets.append((dst, dst_fd))
            return tuple(
                (path, True) for path, fd in targets if not self._relative_to_fd(path, fd)
            )
        if event == "os.symlink":
            _src, dst, dir_fd = padded[:3]
            return () if self._relative_to_fd(dst, dir_fd) else ((dst, True),)
        if event in {"os.remove", "os.rmdir", "shutil.rmtree"}:
            path, dir_fd = padded[:2]
            return () if self._relative_to_fd(path, dir_fd) else ((path, True),)
        if event == "os.truncate":
            return ((padded[0], False),)
        return ()

    def audit(self, event: str, args: tuple) -> None:
        if not self.armed or getattr(self._local, "busy", False):
            return
        if event not in _WATCHED_EVENTS:
            return
        # Die Prüfung selbst ruft realpath/isdir; ohne Sperre liefe der Hook
        # rekursiv in sich hinein.
        self._local.busy = True
        try:
            for target, entry in self._write_targets(event, args):
                if self.is_protected(target, entry=entry):
                    shown = os.fsdecode(target)  # type: ignore[arg-type]
                    with self._lock:
                        self._violations.append(
                            (event, shown, threading.current_thread().name)
                        )
                    raise RealDataWriteError(
                        f"Test schreibt in ein echtes Datenverzeichnis ({event}): "
                        f"{shown}. Pfad über tmp_path isolieren (#1632)."
                    )
        finally:
            self._local.busy = False

    # -- Verstöße --------------------------------------------------------

    def mark(self) -> int:
        with self._lock:
            return len(self._violations)

    def violations_since(self, mark: int) -> list[tuple[str, str, str]]:
        with self._lock:
            return list(self._violations[mark:])

    def discard_since(self, mark: int) -> list[tuple[str, str, str]]:
        """Entfernt Verstöße ab ``mark`` und gibt sie zurück.

        Nur für Tests des Guards selbst, die einen Verstoß absichtlich auslösen.
        """
        with self._lock:
            taken = self._violations[mark:]
            del self._violations[mark:]
            return taken

    @staticmethod
    def describe(violations: list[tuple[str, str, str]]) -> str:
        return "\n".join(
            f"  {event}: {path} (Thread {thread})" for event, path, thread in violations
        )


_ACTIVE: RealDataGuard | None = None


def install(roots: Iterable[Path | str]) -> RealDataGuard:
    """Installiert den Hook einmal pro Prozess und liefert den Guard."""
    global _ACTIVE
    if _ACTIVE is None:
        _ACTIVE = RealDataGuard(roots)
        sys.addaudithook(_ACTIVE.audit)
    return _ACTIVE


def active_guard() -> RealDataGuard:
    if _ACTIVE is None:
        raise RuntimeError("Real-Data-Guard ist nicht installiert")
    return _ACTIVE
