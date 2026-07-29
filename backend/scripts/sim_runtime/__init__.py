"""Shared runtime for OASIS simulation runner scripts.

Centralisiert Logik, die bisher in ``run_twitter_simulation.py``,
``run_reddit_simulation.py`` und ``run_parallel_simulation.py``
dupliziert war. Das Paket liegt bewusst flach in ``backend/scripts/``,
sodass die Runner-Skripte es sowohl als Paket (``from .sim_runtime.ipc
import IPCHandler``) als auch im Direkt-Aufruf (``from sim_runtime.ipc
import IPCHandler``) erreichen — analog zum bestehenden ``_sim_common``
Import-Muster.

Module halten Oasis/CAMEL-Symbole bewusst aus dem Modul-Level heraus
(Injektion statt Modul-Import), damit der Paket-Import ohne die
torch-abhängige Oasis-Laufzeit funktioniert und im Test-Tree
charakterisierbar bleibt.
"""

from __future__ import annotations