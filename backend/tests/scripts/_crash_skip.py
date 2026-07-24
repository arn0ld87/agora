"""Skip-Helper fuer native-Crash-Isolierung unter CPython 3.14 / linux-aarch64.

Siehe ``HANDOVER-2026-07-25-crash-diag-followup.md`` (Aufgabe 3).

CPython 3.14 auf linux-aarch64 crasht beim Modul-Import von
``run_parallel_simulation`` (Modul-Level ``from oasis import ...`` zieht
transitiv ``oasis.social_platform.recsys`` -> ``torch`` -> Segfault in
``libtorch_python.so initModule``) bzw. im GC-Pfad
(``camel.toolkits`` -> ``mcp`` -> ``pydantic_settings`` -> Segfault in
``annotationlib.__forward_code__``). Beide Signaturen treten
nicht-deterministisch an derselben Import-Zeile auf, reproduzierbar in der
vollen ``tests/scripts``-Suite (2/2), nicht isoliert (3/3 gruen). Auf
x86/CI bleiben die Tests aktiv.
"""
from __future__ import annotations

import platform
import sys
import sysconfig

import pytest

_PY314_AARCH64 = (
    sysconfig.get_platform().startswith("linux-aarch64")
    and sys.version_info >= (3, 14)
    and platform.machine() == "aarch64"
)

#: Skip-Marker fuer Tests, die ``run_parallel_simulation`` /
#: ``run_reddit_simulation`` / ``run_twitter_simulation`` importieren und
#: damit den oben beschriebenen nativen Crash-Pfad triggern.
skipif_py314_aarch64 = pytest.mark.skipif(
    _PY314_AARCH64,
    reason=(
        "Native Segfault unter CPython 3.14 / linux-aarch64 beim Import von "
        "run_parallel_simulation (oasis -> torch / camel.toolkits -> mcp). "
        "Isoliert, nicht per App-Code weg (siehe Handover 2026-07-25)."
    ),
)