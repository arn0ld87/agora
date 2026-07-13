"""Central workspace path-boundary checks (SEC-1).

Verhindert Path-Traversal über user-kontrollierte IDs (``simulation_id``,
``run_id``, ``report_id``), die an Speicher-Adapter weitergereicht werden.

Kontext: Die Pydantic-Verträge validieren diese IDs bisher nur mit
``Field(min_length=1)`` — ohne Pattern. CodeQL (``py/path-injection``) modelliert
die Schema-Validierung nicht und flaggt jeden Flow von Request-Input in
``os.path.join``/Dateioperationen. Dieser Helper ist die kanonische,
plattform-sichere Boundary-Prüfung, die an den Speicher-Call-Sites als einziger
Pfad-Resolver verwendet wird.

Design-Entscheidungen (SEC-1-Anforderungen):

- IDs werden *vor* der Pfad-Konstruktion streng validiert (keine Separatoren,
  kein ``..``, kein absoluter Pfad, kein führender Punkt, kein Backslash,
  kein Null-Byte). Reale Agora-IDs sind ``sim_<hex>`` / UUID-Derivate und
  matchen ``[A-Za-z0-9_-]+``.
- Der kanonische Ziel-Pfad wird via ``os.path.realpath`` aufgelöst (resolviert
  Symlinks und ``..``) und muss innerhalb des kanonischen Roots bleiben
  (``os.path.commonpath``-Containment, kein String-Prefix-Vergleich).
- Positive wie negative Cases sind testbar; normale IDs bleiben funktionsfähig.
"""

from __future__ import annotations

import os


class PathTraversalError(ValueError):
    """Kanonischer Pfad verlässt das erlaubte Root oder enthält illegale Bestandteile."""


# Erlaubte Zeichen für Workspace-IDs: alphanumerisch plus ``_`` und ``-``.
# Deckt reale Agora-IDs (``sim_<hex>``, ``run_<id>``, ``rep_<id>``). ``.``, ``/``,
# ``\`` und Null-Bytes sind verboten — damit sind ``..``, absolute Pfade und
# Separatoren-Injektion strukturell ausgeschlossen.
_ID_ALLOWED = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


def validate_path_id(value: str, *, field_name: str = "id") -> str:
    """Validiere eine user-kontrollierte Workspace-ID streng.

    Lässt ``[A-Za-z0-9_-]+`` zu; verwirft leere Werte, absolute Pfade,
    Separatoren (``/``, ``\\``), ``..``, führende ``.`` und Null-Bytes.
    Gibt den Wert unverändert zurück, sodass die Funktion als Inline-Guard
    am Call-Site dienen kann.
    """
    if value is None:
        raise PathTraversalError(f"{field_name} must not be None")
    if not isinstance(value, str):
        raise PathTraversalError(f"{field_name} must be a string, got {type(value)!r}")
    if value == "":
        raise PathTraversalError(f"{field_name} must not be empty")
    if "\x00" in value:
        raise PathTraversalError(f"{field_name} contains null byte")
    if os.path.isabs(value):
        raise PathTraversalError(f"{field_name} must not be absolute: {value!r}")
    if value.startswith("."):
        raise PathTraversalError(f"{field_name} must not start with '.': {value!r}")
    if "/" in value or "\\" in value:
        raise PathTraversalError(f"{field_name} must not contain path separators: {value!r}")
    if not set(value) <= _ID_ALLOWED:
        raise PathTraversalError(
            f"{field_name} contains illegal characters (allowed: [A-Za-z0-9_-]): {value!r}"
        )
    return value


def safe_join_within_root(root: str, *parts: str) -> str:
    """Füge ``parts`` unter ``root`` zusammen und stelle sicher, dass der
    kanonische Ziel-Pfad innerhalb von ``root`` bleibt.

    ``parts`` dürfen relative Sub-Pfade (z. B. ``ipc_commands/cmd1.json``)
    enthalten — die kanonische Containment-Prüfung fängt jeden Escape ab.
    Absolute ``parts`` und Null-Bytes werden vorab verworfen.

    Rückgabe: absoluter kanonischer Pfad innerhalb von ``root``.
    Raise: ``PathTraversalError`` bei Escape-Versuch oder illegalem Part.
    """
    if not parts:
        raise PathTraversalError("safe_join_within_root requires at least one part")
    root_real = os.path.realpath(root)
    norm_parts: list[str] = []
    for p in parts:
        if p is None or p == "":
            raise PathTraversalError("empty path part rejected")
        if "\x00" in p:
            raise PathTraversalError(f"path part contains null byte: {p!r}")
        if os.path.isabs(p):
            raise PathTraversalError(f"absolute path part rejected: {p!r}")
        norm_parts.append(p)
    target_real = os.path.realpath(os.path.join(root_real, *norm_parts))
    # ``commonpath`` ist die plattform-sichere Containment-Prüfung (kein
    # String-Prefix-Vergleich). Gleiche Pfade → commonpath == root_real.
    if os.path.commonpath([root_real, target_real]) != root_real:
        raise PathTraversalError(
            f"path escapes root: {target_real!r} not within {root_real!r}"
        )
    return target_real