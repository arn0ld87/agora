"""
Utility functions for endpoint resolution and validation.
"""

from typing import Optional


LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"})

# Lokale OpenAI-kompatible Server (z. B. Ollama) ignorieren den API-Key
# vollstaendig, das OpenAI-SDK verlangt aber einen nicht-leeren String (#778).
# Dieser Platzhalter macht die No-Auth-Freigabe fuer lokale Endpoints explizit
# sichtbar, statt still `None` an die Generatoren durchzureichen — deren
# Vertrag "Key und Base-URL aus derselben Quelle" (#778) wuerde sonst bei
# String-Mismatch (z. B. host.docker.internal vs. localhost) faelschlich
# einen ValueError werfen, obwohl die API-Schicht den Lauf bereits freigegeben hat.
LOCAL_NO_AUTH_API_KEY = "local-no-auth"


def is_local_endpoint(base_url: Optional[str]) -> bool:
    """Prüft, ob eine Base-URL auf einen lokalen Endpunkt zeigt.

    Nutzt ``urllib.parse.urlparse`` und vergleicht den Hostnamen explizit gegen
    eine Whitelist (``localhost``, ``127.0.0.1``, ``::1``, ``0.0.0.0``,
    ``host.docker.internal``). Das verhindert Subdomain-Smuggling wie
    ``http://not-localhost.com`` oder ``http://remote-server:11434``, die ein
    reines Substring-Match fälschlich als lokal akzeptiert hätte
    (Gemini-Review PR #466).
    """
    if not base_url:
        return False
    from urllib.parse import urlparse

    try:
        parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return host in LOCAL_HOSTS
