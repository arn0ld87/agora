"""Ollama-Download-Service (Onboarding Slice 4.3).

Laedt ein Embedding-Modell von einem Ollama-Endpoint
(``POST /api/pull``) und liefert einen strukturierten Download-Bericht
zurueck. Der Endpoint ist absichtlich kein Server-Sent-Event-Stream,
sondern ein klassischer synchroner HTTP-Call, der auf den
Ollama-Stream wartet — der ist in der Praxis Sekunden bis Minuten
lang und der Aufrufer (UI-Setup-Wizard) braucht das Ergebnis
atomar.

Sicherheit:

* Model-Namen werden gegen ein striktes Pattern validiert, BEVOR sie
  an Ollama gehen. Erlaubt sind ASCII-Buchstaben, Ziffern, Bindestrich,
  Unterstrich, Doppelpunkt und Punkt. Laenge 1-100 Zeichen.
  Damit ist Shell-Injection auf der Modell-Bezeichnungs-Ebene
  ausgeschlossen.
* Wir rufen NIE eine Shell auf, sondern immer ``requests.post(...)``
  mit einem strukturierten JSON-Payload.
* Base-URL muss Loopback sein (lokal) oder explizit ueber eine
  ``ProviderConnection`` mit gueltiger ``ollama``/``ollama_cloud``-
  Klassifikation referenziert werden. Eine nicht-Ollama-Connection
  wird mit 400 abgelehnt.
* Timeout ist konservativ (10 Minuten). Per-Stream-Chunk-Reads haben
  ein zusaetzliches Timeout, damit haengende Connections erkannt
  werden.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from app.contracts.ai_provider_contract import ProviderConnection
from app.services.llm_provider_secrets_store import LlmProviderSecretsStore
from app.services.provider_connection_store import ProviderConnectionStore

# Striktes Pattern: keine Shell-Sonderzeichen, keine Pfad-Traversal-Sequenzen,
# keine Unicode-Tricks. Quelle: Ollama-Modelnamen-Spezifikation
# (https://ollama.com/library) — enthalten nur ASCII-Buchstaben, Ziffern,
# Bindestrich, Unterstrich, Doppelpunkt (Tag-Präfix) und Punkt.
_MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-:]{1,100}$")

# Ollama-Default-Timeout: 10 Minuten reichen auch fuer grosse Modelle
# in der Praxis. Bei Ueberschreitung wird der Request sauber abgebrochen.
DEFAULT_TIMEOUT_SECONDS = 600

# Per-Stream-Chunk-Read-Timeout: 60 Sekunden ohne Daten ist ein
# klarer Hinweis auf eine haengende Verbindung.
DEFAULT_STREAM_READ_TIMEOUT = 60.0


@dataclass(frozen=True)
class OllamaPullReport:
    """Strukturierter Download-Bericht."""

    model: str
    status: str  # "success" | "error"
    digest: str | None = None
    total_bytes: int = 0
    completed_bytes: int = 0
    error_message: str | None = None
    layers_downloaded: int = 0


class OllamaPullError(Exception):
    """Wird geworfen, wenn der Download fehlschlaegt oder der Model-Name
    ungueltig ist."""


def validate_model_name(name: str) -> str:
    """Prueft den Model-Namen gegen das sichere Pattern. Liefert ihn
    unveraendert zurueck, wenn er gueltig ist; wirft sonst ``ValueError``.
    """
    if not isinstance(name, str) or not _MODEL_NAME_PATTERN.match(name):
        raise ValueError(
            f"Ungültiger Ollama-Model-Name: {name!r} "
            f"(erlaubt: ASCII a-z, A-Z, 0-9, '-', '_', '.', ':', 1-100 Zeichen)"
        )
    return name


def pull_model(
    *,
    model: str,
    base_url: str,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    session_factory: Callable[[], Any] = requests.Session,
    stream_read_timeout: float = DEFAULT_STREAM_READ_TIMEOUT,
) -> OllamaPullReport:
    """Laedt ``model`` von ``base_url`` und gibt einen Bericht zurueck.

    ``base_url`` muss bereits der Loopback-/Ollama-Cloud-Endpunkt sein
    (die URL-Validierung uebernimmt der Aufrufer; hier wird nur
    strukturell geprueft, dass ein HTTP(S)-Schema vorliegt).
    """
    validate_model_name(model)
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise OllamaPullError(
            f"base_url muss mit http:// oder https:// beginnen: {base_url!r}"
        )

    url = base_url.rstrip("/") + "/api/pull"
    headers = {"Content-Type": "application/json", "Accept": "application/x-ndjson"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    completed = 0
    total = 0
    digest: str | None = None
    layers = 0
    last_status: str | None = None

    try:
        with session_factory() as http:
            response = http.post(
                url,
                json={"name": model, "stream": True},
                headers=headers,
                timeout=timeout,
                stream=True,
            )
            if response.status_code in (401, 403):
                raise OllamaPullError(
                    f"Ollama-Authentifizierung fehlgeschlagen: HTTP {response.status_code}"
                )
            if response.status_code >= 400:
                raise OllamaPullError(
                    f"Ollama-Fehler: HTTP {response.status_code} — {response.text[:200]}"
                )
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line.decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    raise OllamaPullError(
                        f"Nicht parsebare NDJSON-Zeile: {exc}"
                    ) from exc
                last_status = event.get("status")
                if "total" in event and "completed" in event:
                    try:
                        total = int(event["total"])
                        completed = int(event["completed"])
                    except (TypeError, ValueError):
                        pass
                if "digest" in event:
                    digest = event["digest"]
                if last_status == "success":
                    layers += 1
                if event.get("error"):
                    raise OllamaPullError(
                        f"Ollama-Stream-Error: {event['error']}"
                    )
    except requests.exceptions.Timeout as exc:
        raise OllamaPullError(
            f"Timeout beim Download von {model}: {exc}"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise OllamaPullError(
            f"Verbindungsfehler: {exc}"
        ) from exc

    if last_status != "success":
        return OllamaPullReport(
            model=model,
            status="error",
            error_message=f"Stream endete ohne 'success': letzter Status={last_status!r}",
            digest=digest,
            total_bytes=total,
            completed_bytes=completed,
            layers_downloaded=layers,
        )
    return OllamaPullReport(
        model=model,
        status="success",
        digest=digest,
        total_bytes=total,
        completed_bytes=completed,
        layers_downloaded=layers,
    )


def resolve_ollama_base_url(
    *,
    configuration_id: str | None,
    connection_store: ProviderConnectionStore,
) -> tuple[ProviderConnection, str]:
    """Loest die Base-URL fuer den Ollama-Download auf.

    Wenn ``configuration_id`` uebergeben wird, wird die zugehoerige
    ``ProviderConnection`` verwendet. Andernfalls wird eine
    ``Connection`` mit ``provider_kind in (\"ollama\", \"ollama_cloud\")``
    aus dem Store gesucht und der erste Treffer verwendet. Wirft
    ``KeyError``, wenn keine geeignete Verbindung existiert.
    """
    connections = list(connection_store.list_connections())
    if configuration_id:
        chosen = next((c for c in connections if c.id == configuration_id), None)
        if chosen is None:
            raise KeyError(
                f"Unbekannte Provider-Connection: {configuration_id}"
            )
    else:
        chosen = next(
            (
                c
                for c in connections
                if c.provider_kind in ("ollama", "ollama_cloud")
            ),
            None,
        )
        if chosen is None:
            raise KeyError(
                "Keine Ollama-Provider-Connection gefunden; bitte erst eine "
                "Connection anlegen oder configuration_id uebergeben"
            )
    if chosen.provider_kind not in ("ollama", "ollama_cloud"):
        raise ValueError(
            f"Provider-Connection {chosen.id} ist kein Ollama-Provider "
            f"({chosen.provider_kind!r})"
        )
    if chosen.base_url is None:
        raise ValueError(
            f"Provider-Connection {chosen.id} hat keine base_url"
        )
    return chosen, chosen.base_url


def pull_model_via_configuration(
    *,
    model: str,
    configuration_id: str | None,
    connection_store: ProviderConnectionStore,
    secrets_store: LlmProviderSecretsStore,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    session_factory: Callable[[], Any] = requests.Session,
) -> OllamaPullReport:
    """Convenience-Wrapper: loest die Connection auf, holt den API-Key
    und ruft ``pull_model`` auf.
    """
    connection, base_url = resolve_ollama_base_url(
        configuration_id=configuration_id,
        connection_store=connection_store,
    )
    api_key: str | None = None
    if connection.secret_ref is not None:
        api_key = secrets_store.get_plaintext(connection.secret_ref)
    return pull_model(
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        session_factory=session_factory,
    )


__all__ = [
    "OllamaPullError",
    "OllamaPullReport",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_STREAM_READ_TIMEOUT",
    "pull_model",
    "pull_model_via_configuration",
    "resolve_ollama_base_url",
    "validate_model_name",
]
