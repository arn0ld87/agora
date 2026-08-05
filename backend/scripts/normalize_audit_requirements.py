"""normalize_audit_requirements.py — PEP-440-Local-Versions für pip-audit strippen.

``uv export`` schreibt die gepinnte Torch-Variante als ``torch==2.13.0+cpu``
in die requirements.txt. Das ``+cpu`` ist ein PEP-440-*local version label*;
PyPI weist solche Labels beim Upload grundsätzlich zurück, sie existieren nur
in Fremdindizes wie ``download.pytorch.org``. ``pip-audit`` löst jede Zeile
gegen PyPI auf und meldet für ``2.13.0+cpu``::

    ERROR:pip_audit._cli:torch: Dependency not found on PyPI and could not be
    audited: torch (2.13.0+cpu)

Unter ``--strict`` ist „konnte nicht auditiert werden" ein Fehler, der Step
endet mit Exit 1. Lokal auf macOS fällt das nicht auf: ``uv export`` schreibt
beide Marker-Varianten (``sys_platform != 'linux'`` → ``2.13.0``,
``sys_platform == 'linux'`` → ``2.13.0+cpu``), und nur auf Linux greift die
``+cpu``-Zeile.

Ein ``--extra-index-url`` repariert das nicht: pip-audit fragt den
Vulnerability-Service (PyPI/OSV) und nicht den Paket-Index nach der Version.

Das Local-Label zu strippen ist inhaltlich korrekt und konservativ: Advisories
werden gegen die Public-Release-Version geführt (``2.13.0``), und der
``+cpu``-Build stammt aus demselben Upstream-Quellstand. Wer ``2.13.0`` prüft,
prüft dieselbe Codebasis.

Aufruf::

    python backend/scripts/normalize_audit_requirements.py IN.txt OUT.txt
    uv export ... | python backend/scripts/normalize_audit_requirements.py - -

Exit-Codes:
  0 — Datei geschrieben
  2 — Aufruffehler (falsche Argumentzahl, Eingabe nicht lesbar)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Greift auf ``name==version+local`` und behält alles ab dem Marker (`;`) oder
# einem Kommentar unverändert. Das Local-Label ist per PEP 440 auf
# ``[a-z0-9]`` plus ``.``/``-``/``_`` als Trenner beschränkt.
_LOCAL_VERSION_RE = re.compile(
    r"""^(?P<head>\s*[A-Za-z0-9._-]+\s*==\s*[0-9][^\s;#+]*)
        \+(?P<local>[A-Za-z0-9._-]+)
        (?P<tail>.*)$""",
    re.VERBOSE,
)


def strip_local_versions(text: str) -> str:
    """Entfernt PEP-440-Local-Version-Labels aus einer requirements.txt.

    Marker (``; sys_platform == 'linux'``), Kommentare, Index-Direktiven und
    Leerzeilen bleiben unverändert.
    """
    out: list[str] = []
    for line in text.splitlines():
        match = _LOCAL_VERSION_RE.match(line)
        out.append(f"{match['head']}{match['tail']}" if match else line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Strippt PEP-440-Local-Versions (z. B. +cpu) aus einer "
        "requirements.txt, damit pip-audit --strict jede Zeile "
        "gegen PyPI auflösen kann.",
    )
    parser.add_argument("source", help="Eingabedatei oder '-' für stdin")
    parser.add_argument("target", help="Ausgabedatei oder '-' für stdout")
    args = parser.parse_args(argv)

    if args.source == "-":
        text = sys.stdin.read()
    else:
        source = Path(args.source)
        if not source.is_file():
            print(f"::error::Eingabe nicht lesbar: {source}", file=sys.stderr)
            return 2
        text = source.read_text(encoding="utf-8")

    normalized = strip_local_versions(text)

    if args.target == "-":
        sys.stdout.write(normalized)
    else:
        Path(args.target).write_text(normalized, encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI-Einstieg
    sys.exit(main())
