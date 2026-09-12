"""Prozess-Identitaet fuer In-Process-Hintergrundjobs (Issue #1472).

Warum das gebraucht wird
------------------------
``reconcile_stale_runs`` erkennt einen verwaisten ``simulation_run`` an der in
``run_state.json`` persistierten ``process_pid`` des OASIS-Subprozesses. Die
In-Process-Jobs (``simulation_prepare``, ``report_generate``, ``graph_build``,
``ontology_generate``) haben keinen Subprozess und damit keine solche PID: sie
laufen als ``threading.Thread(daemon=True)`` im Webprozess selbst. Nach einem
SIGTERM existiert der Thread nicht mehr, das RunRegistry-Manifest bleibt aber
auf ``processing`` stehen — fuer immer, weil nichts mehr existiert, das es je
wieder aendern wuerde.

Die Liveness dieser Jobs haengt deshalb am *Webprozess*, nicht an einem
Subprozess. Genau den identifiziert dieses Modul.

Warum nicht nur die PID
-----------------------
Eine PID allein reicht nicht: nach einem Container-Neustart kann derselbe
Zahlenwert wieder vergeben sein (gerade PID-arme Container beginnen bei
niedrigen Nummern), und ein Manifest des alten Prozesses saehe dann faelschlich
lebendig aus. Das Token ist pro Prozess einmalig und macht diese Verwechslung
unmoeglich.

Warum der Cache nach PID geschluesselt ist
------------------------------------------
Unter gunicorn mit ``preload_app = True`` wird dieses Modul im Master
importiert, *bevor* geforkt wird. Ein beim Import erzeugtes Modul-Token wuerde
an jeden Worker vererbt — alle Worker saehen wie derselbe Prozess aus, und ein
Worker-Replacement waere nicht mehr erkennbar. Das Token entsteht deshalb erst
beim ersten Zugriff und liegt unter der dann aktuellen PID: ein geforktes Kind
erbt zwar den Cache, findet unter seiner eigenen PID aber keinen Eintrag und
erzeugt sein eigenes Token.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict

#: PID -> Token. Siehe Modul-Docstring: die Schluesselung nach PID ist der
#: Fork-Schutz, kein Performance-Detail.
_TOKENS: Dict[int, str] = {}

#: Metadata-Schluessel im RunRegistry-Manifest.
WORKER_PID_KEY = "worker_pid"
WORKER_TOKEN_KEY = "worker_token"


def worker_token() -> str:
    """Einmaliges Token dieses Prozesses, stabil ueber seine Lebensdauer."""
    pid = os.getpid()
    token = _TOKENS.get(pid)
    if token is None:
        token = uuid.uuid4().hex
        _TOKENS[pid] = token
    return token


def current_worker_identity() -> Dict[str, Any]:
    """Identitaet dieses Prozesses fuer das RunRegistry-Manifest."""
    return {WORKER_PID_KEY: os.getpid(), WORKER_TOKEN_KEY: worker_token()}


def owns_run(metadata: Dict[str, Any] | None) -> bool:
    """True, wenn *dieser* Prozess den Job hinter ``metadata`` ausfuehrt.

    ``False`` fuer ein Manifest ohne Token: entweder stammt es aus der Zeit vor
    diesem Mechanismus, oder der stempelnde Prozess ist weg. Beides heisst nach
    einem Neustart dasselbe — niemand fuehrt diesen Job noch aus. Ein Manifest
    eines *laufenden* Prozesses traegt immer ein Token, weil ``enqueue`` es
    setzt, bevor der Thread startet.
    """
    if not metadata:
        return False
    return metadata.get(WORKER_TOKEN_KEY) == worker_token()


__all__ = [
    "WORKER_PID_KEY",
    "WORKER_TOKEN_KEY",
    "current_worker_identity",
    "owns_run",
    "worker_token",
]
