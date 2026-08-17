"""Gemeinsame Datei- und Sperrmechanik der dateibasierten JSON-Stores.

``OnboardingStateStore``, ``UserProfileStore`` und ``WorkspaceRoutingStore``
trugen bis zum 17.08.2026 je eine eigene, zeichengleiche Kopie von ``__init__``,
``_file_lock`` und ``reset_for_tests``. Bei der Sperrmechanik ist das die
teuerste Sorte Duplikation: ein vergessenes ``LOCK_UN`` oder ein falsch
gesetztes ``try``/``finally`` in einer der Kopien fällt nicht beim Lesen auf,
sondern erst als hängender Prozess unter Last.

Die Klasse ist bewusst **schmal**: sie kennt Pfad, Sperre und Aufräumen, aber
weder Payload noch Serialisierung. Die erbenden Stores behalten ihre
``load``/``save``-Logik vollständig; es gibt keine abstrakten Hooks, die sie
bedienen müssten.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator, Optional

import fcntl

from .data_dir import resolve_data_dir


class JsonFileStore:
    """Pfadableitung, Prozess- und Dateisperre für einen JSON-Store.

    Schreib-Operationen der erbenden Stores sind sowohl innerhalb eines
    Prozesses (``threading.Lock`` auf ``self._lock``) als auch zwischen
    Prozessen (``fcntl.flock`` auf ``self._lock_path``) atomar.
    """

    def __init__(self, filename: str, *, data_dir: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
        self._data_dir = data_dir or resolve_data_dir()
        self._path = self._data_dir / filename
        self._lock_path = self._path.with_suffix(".lock")

    @contextmanager
    def _file_lock(self) -> Iterator[IO[str]]:
        """Hält einen exklusiven ``fcntl.flock`` für die Lebensdauer des Blocks.

        Read-modify-write-Sequenzen müssen den Lock über Load **und** Save
        halten — sonst überschreiben zwei parallele Worker dasselbe Dokument
        und Updates gehen verloren.
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "w", encoding="utf-8") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            try:
                yield lock_fh
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)

    def reset_for_tests(self) -> None:
        """Entfernt Nutzdaten- und Lock-Datei. Nur für Tests gedacht."""
        with self._lock:
            if self._path.exists():
                self._path.unlink()
            if self._lock_path.exists():
                self._lock_path.unlink()
