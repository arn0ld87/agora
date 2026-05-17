"""WSGI-Entrypoint für gunicorn mit korrekt früher gevent-Monkey-Patch-Reihenfolge.

Hintergrund (Issue #529):
Mit ``gunicorn -k gevent --preload app:create_app()`` lädt der Master alle
App-Imports (``requests``, ``urllib3``, ``ssl``, ``redis``, ``anyio.streams.tls``)
BEVOR der gevent-Worker beim Boot ``gevent.monkey.patch_all()`` ausführt.
gevent warnt explizit: ``Monkey-patching ssl after ssl has already been
imported may lead to errors, including RecursionError``.

Sichtbares Symptom war ``maximum recursion depth exceeded`` in jedem
``requests.get`` / ``urllib3.PoolManager.request``-Aufruf aus Request-Handlern
(z. B. ``model_catalog_service._fetch_live`` für die LLM-Modell-Discovery).

Lösung: Dieses Modul als gunicorn-App-Target nutzen (``wsgi:app``). Hier ist
``patch_all()`` das ABSOLUT ERSTE Statement — vor jedem App-Import. So ist
``socket``/``ssl``/``ssl_wrap_socket`` schon gepatcht, wenn die App-Factory
ihre Library-Tree-Importe macht.

Reihenfolge ist nicht verhandelbar. Nichts oberhalb dieser Zeilen einfügen
(auch keine ``from __future__``-Imports).
"""

import gevent.monkey

gevent.monkey.patch_all()

# Erst NACH patch_all() darf die App importiert werden — sonst hat dieses
# Modul keinen Effekt.
from app import create_app  # noqa: E402

app = create_app()
