"""Direkte Persona-Interviews ohne lebenden OASIS-Worker.

Post-Simulations-Interviews brauchen keine laufende OASIS-Umgebung: Persona-
Profile, Simulationskontext und Trace-DBs sind persistiert. Dieser Pfad
beantwortet Interview-Anfragen daher im Flask-Prozess über den zentralen
``LLMClient`` und spiegelt die Ergebnisform des IPC-Pfads, damit API-Layer und
Frontend unverändert bleiben.

Bewusst ``LLMClient.chat`` statt ``chat_json``: eine Interview-Antwort ist
Freitext, exakt wie die OASIS-Interview-Action ihn liefert. Die
chat_json-SSoT-Regel adressiert strukturierte JSON-Outputs; ein JSON-Wrapper um
einen einzigen Prosa-String erzeugt hier nur eine zusätzliche Fehlerklasse
(Provider ohne strict-json_schema-Support antworten mit Prosa und der Call
scheitert am Parser).

``interview_client`` routet auf dieses Modul, sobald kein IPC-Poller lebt.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ...utils.logger import get_logger
from ..artifact_store import resolve_default_store

logger = get_logger("agora.interview_direct")

# Parallelität für Batch-Interviews. Jeder Worker bekommt einen eigenen
# LLM-Client (thread-local), damit kein Client-State geteilt wird.
_MAX_WORKERS = 4

DEFAULT_PLATFORM = "reddit"


def _store():
    """Return the active SimulationArtifactStore (lazy, no app-context required)."""
    return resolve_default_store()


# ---------------------------------------------------------------------------
# Persona-Laden
# ---------------------------------------------------------------------------


def _load_personas(
    simulation_id: str,
    platform: str,
    *,
    run_state_dir: str,
) -> List[Dict[str, Any]]:
    """Lade die persistierten Persona-Profile einer Simulation.

    Reddit-Profile liegen als JSON-Liste im Artifact-Store, Twitter-Profile als
    CSV neben den Simulationsdaten. Fehler werden geloggt und als leere Liste
    behandelt — der Aufrufer entscheidet, ob das ein harter Fehler ist.
    """
    if platform == "twitter":
        profiles_path = os.path.join(run_state_dir, simulation_id, "twitter_profiles.csv")
        if not os.path.exists(profiles_path):
            return []
        try:
            with open(profiles_path, "r", encoding="utf-8") as handle:
                return list(csv.DictReader(handle))
        except OSError as exc:
            logger.warning(f"Twitter-Profile nicht lesbar ({simulation_id}): {exc}")
            return []

    try:
        profiles = _store().read_json(simulation_id, "reddit_profiles", default=[]) or []
    except Exception as exc:  # noqa: BLE001 — Store-Fehler ist kein Interview-Fehler
        logger.warning(f"Reddit-Profile nicht lesbar ({simulation_id}): {exc}")
        return []
    return profiles if isinstance(profiles, list) else []


def _resolve_persona(
    personas: List[Dict[str, Any]], agent_id: Any
) -> Optional[Dict[str, Any]]:
    """Finde die Persona zu einer ``agent_id``.

    Das Frontend adressiert Personas über den Listenindex (so werden sie auch
    angezeigt), OASIS über ``user_id``. Index hat Vorrang, damit Label und
    Antwort zusammenpassen; ``user_id`` ist der Fallback.
    """
    try:
        index = int(agent_id)
    except (TypeError, ValueError):
        return None

    if 0 <= index < len(personas):
        return personas[index]

    for persona in personas:
        raw_id = persona.get("user_id")
        try:
            if raw_id is not None and int(raw_id) == index:
                return persona
        except (TypeError, ValueError):
            continue
    return None


def direct_interviews_available(simulation_id: str, *, run_state_dir: str) -> bool:
    """``True``, wenn Interviews ohne lebenden Worker beantwortet werden können."""
    for platform in ("reddit", "twitter"):
        if _load_personas(simulation_id, platform, run_state_dir=run_state_dir):
            return True
    return False


# ---------------------------------------------------------------------------
# Prompt-Bau
# ---------------------------------------------------------------------------


def _simulation_context(simulation_id: str) -> Dict[str, Any]:
    """Lies Fragestellung und Sprache aus dem persistierten Simulations-Config."""
    try:
        config = _store().read_json(simulation_id, "simulation_config", default=None) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Simulations-Config nicht lesbar ({simulation_id}): {exc}")
        config = {}
    return {
        "requirement": (config.get("simulation_requirement") or "").strip(),
        "language": config.get("language") or "de",
        # Route des Laufs — siehe _default_client_factory.
        "llm_model": (config.get("llm_model") or "").strip(),
        "llm_base_url": (config.get("llm_base_url") or "").strip(),
    }


def _persona_label(persona: Dict[str, Any], agent_id: Any) -> str:
    return (
        persona.get("name")
        or persona.get("username")
        or persona.get("user_name")
        or f"agent_{agent_id}"
    )


def _persona_description(persona: Dict[str, Any]) -> str:
    """Baue den Profilblock für den System-Prompt aus den vorhandenen Feldern."""
    # user_char stammt aus dem Twitter-CSV und enthält bio + persona bereits kombiniert.
    fields = [
        ("Beruf/Rolle", persona.get("profession")),
        ("Alter", persona.get("age")),
        ("Land", persona.get("country")),
        ("Kurzprofil", persona.get("bio") or persona.get("description")),
        ("Persona", persona.get("persona") or persona.get("user_char")),
    ]
    lines = [f"- {label}: {value}" for label, value in fields if value not in (None, "", [])]

    topics = persona.get("interested_topics")
    if isinstance(topics, str):
        topics = [topics] if topics else []
    if topics:
        lines.append(f"- Interessen: {', '.join(str(t) for t in topics)}")
    return "\n".join(lines)


def build_persona_messages(
    persona: Dict[str, Any],
    agent_id: Any,
    prompt: str,
    *,
    context: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Baue die chat_json-Messages für ein einzelnes Persona-Interview."""
    label = _persona_label(persona, agent_id)
    language = "Deutsch" if str(context.get("language", "de")).startswith("de") else "Englisch"
    requirement = context.get("requirement") or "(keine Fragestellung hinterlegt)"

    system = (
        f"Du bist {label}, eine simulierte Persona aus einer Agora-Zielgruppensimulation.\n\n"
        f"Profil:\n{_persona_description(persona)}\n\n"
        f"Fragestellung der Simulation:\n{requirement}\n\n"
        "Regeln:\n"
        "- Antworte durchgehend in der Ich-Form aus Sicht dieser Persona.\n"
        "- Bleibe bei dem, was aus Profil und Fragestellung plausibel ist.\n"
        "- Erfinde keine Zahlen, Studien, Zitate oder Fakten ueber reale Personen "
        "oder Unternehmen.\n"
        "- Wenn du etwas aus deiner Rolle heraus nicht wissen kannst, sage das offen.\n"
        f"- Antworte auf {language}, 2 bis 6 Saetze, konkret und ohne Marketingsprache.\n"
        "- Deine Antwort ist eine Simulation, keine Aussage einer realen Person."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]


# ---------------------------------------------------------------------------
# Persistenz (Trace-DB)
# ---------------------------------------------------------------------------


_TRACE_DDL = """
CREATE TABLE IF NOT EXISTS trace (
    user_id INTEGER,
    created_at DATETIME,
    action TEXT,
    info TEXT,
    PRIMARY KEY(user_id, created_at, action, info)
)
"""


def _persist_interview(
    simulation_id: str,
    platform: str,
    agent_id: Any,
    prompt: str,
    response: str,
    *,
    run_state_dir: str,
) -> None:
    """Schreibe das Interview in die Trace-DB der Plattform (best effort).

    Damit bleibt ``/interview/history`` auch für den Direktpfad gefüllt. Fehler
    werden geloggt und niemals an den Aufrufer weitergereicht — eine bereits
    erzeugte Antwort darf an der Persistenz nicht scheitern.
    """
    db_path = os.path.join(run_state_dir, simulation_id, f"{platform}_simulation.db")
    info = json.dumps(
        {"prompt": prompt, "response": response, "source": "direct"},
        ensure_ascii=False,
    )
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(_TRACE_DDL)
            conn.execute(
                "INSERT OR REPLACE INTO trace (user_id, created_at, action, info) "
                "VALUES (?, ?, ?, ?)",
                (int(agent_id), datetime.now().isoformat(sep=" "), "interview", info),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — Persistenz ist Zusatz, kein Hotpath
        logger.warning(
            f"Interview-Trace nicht geschrieben ({simulation_id}/{platform}): {exc}"
        )


# ---------------------------------------------------------------------------
# Interview-Ausführung
# ---------------------------------------------------------------------------


def _default_client_factory(
    timeout: float, context: Dict[str, Any]
) -> Callable[[], Any]:
    """Client-Factory, die die im Lauf verwendete Route bevorzugt.

    Ein blanker ``LLMClient()`` würde die *aktuelle* Workspace-Auswahl auflösen.
    Dieselbe Persona antwortete dann je nach Zeitpunkt mit einem anderen Modell
    oder sogar über einen anderen Provider, nur weil das Interview nach
    Simulationsende gestellt wurde. ``simulation_config`` hält ``llm_model`` und
    ``llm_base_url`` des Laufs fest — die haben Vorrang.

    Der Lauf persistiert keine ``connection_id`` — nur ``llm_model`` und
    ``llm_base_url`` (siehe ``simulation_run.py``). Die Base-URL identifiziert
    die Connection aber genauso eindeutig, wie sie es für Legacy-Profile tut
    (``profile_connection_resolver``); ``resolve_connection_for_base_url``
    löst darüber den API-Key aus dem Connection-Store auf, statt auf
    ``Config.LLM_API_KEY`` zu vertrauen, der nie zur richtigen Connection
    gehören muss.

    Lässt sich damit kein Client bauen (z. B. weil der Key des Laufs nicht mehr
    auflösbar ist), fällt die Factory sichtbar auf die aktive Konfiguration
    zurück, statt das Interview scheitern zu lassen — diese Degradierung wird
    immer geloggt, unabhängig davon, ob der Fallback-Aufbau selbst gelingt.
    """

    def factory():
        from ...config import Config
        from ...llm.client import LLMClient
        from ...llm.factory import resolve_connection_for_base_url
        from ..profile_connection_resolver import normalize_endpoint_url

        model = context.get("llm_model") or None
        base_url = context.get("llm_base_url") or None
        if model:
            connection_key = connection_id = connection_auth_mode = None
            if base_url:
                connection_key, connection_id, connection_auth_mode = (
                    resolve_connection_for_base_url(base_url)
                )

            if connection_id is not None and (
                connection_auth_mode == "none" or connection_key
            ):
                try:
                    return LLMClient(
                        model=model,
                        base_url=base_url,
                        api_key=connection_key or "ollama",
                        route_provider_id=connection_id,
                        api_key_source="connection_store",
                        use_active_config=False,
                        allow_api_key_fallback=False,
                        timeout=timeout,
                    )
                except Exception as exc:  # noqa: BLE001 — Fallback ist besser als Abbruch
                    logger.warning(
                        "Connection %s der Lauf-Route (model=%s) nicht nutzbar (%s) "
                        "— Interview nutzt die aktive Konfiguration",
                        connection_id,
                        model,
                        exc,
                    )
            elif connection_id is not None:
                # Der Endpunkt trifft eine aktivierte Connection, deren Secret
                # aber fehlt, leer ist oder sich nicht entschluesseln laesst.
                # Config.LLM_API_KEY mit der Base-URL des Laufs zu kombinieren
                # wuerde einen fremden Key an genau den Endpunkt schicken, den
                # dieser Fix absichern soll (#778). Deshalb vollstaendige
                # Degradierung auf die aktive Konfiguration statt einer halben
                # Route aus zwei Quellen.
                logger.warning(
                    "ProviderConnection %s (auth_mode=%s) haelt kein nutzbares "
                    "Secret — Interview faellt vollstaendig auf die aktive "
                    "Konfiguration zurueck; die Base-URL des Laufs wird nicht "
                    "mit einem fremden Key kombiniert",
                    connection_id,
                    connection_auth_mode,
                )
            elif base_url and normalize_endpoint_url(base_url) != normalize_endpoint_url(
                Config.LLM_BASE_URL
            ):
                # Keine Connection zu diesem Endpunkt, und er ist nicht der
                # globale. Auch hier gilt #778: Key und Base-URL stammen aus
                # derselben Quelle oder gar nicht.
                logger.warning(
                    "Lauf-Route (model=%s, base_url=%s) referenziert keine "
                    "aktivierte ProviderConnection und zeigt nicht auf den "
                    "globalen Endpunkt — Interview faellt vollstaendig auf die "
                    "aktive Konfiguration zurueck",
                    model,
                    base_url,
                )
            else:
                # Endpunkt des Laufs ist der globale: Config.LLM_API_KEY gehoert
                # zu genau dieser Base-URL, die Invariante bleibt gewahrt.
                logger.warning(
                    "Lauf-Route (model=%s, base_url=%s) referenziert keine "
                    "aktivierte ProviderConnection — Interview faellt auf "
                    "Config.LLM_API_KEY am selben Endpunkt zurueck",
                    model,
                    base_url,
                )
                try:
                    return LLMClient(model=model, base_url=base_url, timeout=timeout)
                except Exception as exc:  # noqa: BLE001 — Fallback ist besser als Abbruch
                    logger.warning(
                        "Route des Laufs (model=%s) nicht nutzbar (%s) — Interview "
                        "nutzt die aktive Konfiguration",
                        model,
                        exc,
                    )
        return LLMClient(timeout=timeout)

    return factory


class _ThreadLocalClients:
    """Ein LLM-Client pro Worker-Thread — kein geteilter Client-State."""

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._local = threading.local()

    def get(self):
        client = getattr(self._local, "client", None)
        if client is None:
            client = self._factory()
            self._local.client = client
        return client


def _answer_one(
    clients: _ThreadLocalClients,
    persona: Dict[str, Any],
    agent_id: Any,
    prompt: str,
    *,
    context: Dict[str, Any],
    max_tokens: int,
) -> str:
    messages = build_persona_messages(persona, agent_id, prompt, context=context)
    answer = clients.get().chat(
        messages=messages,
        temperature=0.7,
        max_tokens=max_tokens,
        context="chat",
    )
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("LLM lieferte keine verwertbare Interview-Antwort")
    return answer.strip()


def interview_agents_batch_direct(
    simulation_id: str,
    interviews: List[Dict[str, Any]],
    platform: Optional[str] = None,
    timeout: float = 120.0,
    *,
    run_state_dir: str,
    client_factory: Optional[Callable[[], Any]] = None,
    max_tokens: int = 1024,
    max_workers: int = _MAX_WORKERS,
) -> Dict[str, Any]:
    """Beantworte mehrere Interviews direkt über den LLM-Client.

    Die Ergebnisform spiegelt den IPC-Batch-Pfad
    (``{"result": {"results": {"<platform>_<agent_id>": {...}}}}``) und ergänzt
    ``mode="direct"`` sowie ``simulated=True`` je Eintrag.

    Zwei bewusste Abweichungen vom IPC-Pfad:

    - Ohne ``platform`` fächert IPC das Interview auf *beide* Plattformen auf.
      Der Direktpfad tut das nicht: dieselbe Frage an dieselbe Persona zweimal
      zu stellen verdoppelt nur Kosten und Laufzeit, und das Frontend
      dedupliziert ohnehin auf eine Antwort pro ``agent_id``. Personas werden
      pro *effektiver* Plattform des Items aufgelöst, ein
      ``platform``-Override je Item greift also wirklich.
    - ``timeout`` gilt als Deadline für den gesamten Batch, nicht pro Item.

    Raises:
        ValueError: Simulation existiert nicht oder es sind für keine Plattform
            Personas persistiert.
    """
    sim_dir = os.path.join(run_state_dir, simulation_id)
    if not os.path.exists(sim_dir):
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    persona_cache: Dict[str, List[Dict[str, Any]]] = {}

    def _personas_for(name: str) -> List[Dict[str, Any]]:
        if name not in persona_cache:
            persona_cache[name] = _load_personas(
                simulation_id, name, run_state_dir=run_state_dir
            )
        return persona_cache[name]

    requested_platform = platform if platform in ("twitter", "reddit") else None
    # Default-Plattform: die angeforderte, sonst die mit persistierten Personas.
    default_platform = requested_platform or DEFAULT_PLATFORM
    if not _personas_for(default_platform):
        fallback = "twitter" if default_platform == "reddit" else "reddit"
        if _personas_for(fallback):
            default_platform = fallback

    if not any(_personas_for(name) for name in ("reddit", "twitter")):
        raise ValueError(
            f"Keine Persona-Profile fuer Simulation {simulation_id} persistiert — "
            "Interview ohne laufende Umgebung nicht moeglich"
        )

    context = _simulation_context(simulation_id)
    clients = _ThreadLocalClients(
        client_factory or _default_client_factory(timeout, context)
    )
    timestamp = datetime.now().isoformat()
    # Gesamt-Deadline: ohne sie summieren sich bei mehr als _MAX_WORKERS Items
    # die Wellen zu einem Vielfachen des angefragten Timeouts auf. Ein bereits
    # laufender Call wird nicht abgebrochen — die Obergrenze ist damit
    # Deadline plus die Dauer eines einzelnen Calls.
    deadline = time.monotonic() + max(1.0, timeout)

    def _run(item: Dict[str, Any]) -> Dict[str, Any]:
        agent_id = item.get("agent_id")
        prompt = item.get("prompt", "")
        item_platform = item.get("platform")
        if item_platform not in ("twitter", "reddit"):
            item_platform = default_platform

        personas = _personas_for(item_platform)
        if not personas and item_platform != default_platform:
            # Item verlangt eine Plattform ohne Profile — auf die Plattform
            # ausweichen, die welche hat, statt hart zu scheitern.
            item_platform = default_platform
            personas = _personas_for(item_platform)

        entry: Dict[str, Any] = {
            "agent_id": agent_id,
            "platform": item_platform,
            "prompt": prompt,
            "response": None,
            "timestamp": timestamp,
            "simulated": True,
            "mode": "direct",
        }

        persona = _resolve_persona(personas, agent_id)
        if persona is None:
            entry["error"] = f"Keine Persona zu agent_id={agent_id} gefunden"
            return entry

        if time.monotonic() >= deadline:
            entry["error"] = (
                f"Batch-Deadline von {timeout:.0f}s überschritten — Interview "
                "nicht mehr gestartet"
            )
            return entry

        try:
            entry["response"] = _answer_one(
                clients,
                persona,
                agent_id,
                prompt,
                context=context,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001 — ein Fehler kippt nicht den Batch
            logger.warning(
                f"Direkt-Interview fehlgeschlagen ({simulation_id}, agent_id={agent_id}): {exc}"
            )
            entry["error"] = str(exc)
            return entry

        _persist_interview(
            simulation_id,
            item_platform,
            agent_id,
            prompt,
            entry["response"],
            run_state_dir=run_state_dir,
        )
        return entry

    logger.info(
        f"Direkt-Interview (ohne IPC): simulation_id={simulation_id}, "
        f"count={len(interviews)}, platform={default_platform}"
    )

    entries: List[Dict[str, Any]] = []
    if interviews:
        workers = max(1, min(max_workers, len(interviews)))
        if workers == 1:
            entries = [_run(item) for item in interviews]
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                entries = list(pool.map(_run, interviews))

    results = {f"{e['platform']}_{e['agent_id']}": e for e in entries}
    succeeded = [e for e in entries if e.get("response")]

    return {
        "success": bool(succeeded),
        "interviews_count": len(results),
        "mode": "direct",
        "result": {
            "interviews_count": len(results),
            "results": results,
        },
        "timestamp": timestamp,
    }


def interview_agent_direct(
    simulation_id: str,
    agent_id: int,
    prompt: str,
    platform: Optional[str] = None,
    timeout: float = 60.0,
    *,
    run_state_dir: str,
    client_factory: Optional[Callable[[], Any]] = None,
) -> Dict[str, Any]:
    """Beantworte ein einzelnes Interview direkt über den LLM-Client.

    Ergebnisform spiegelt den IPC-Einzelpfad
    (``{"success", "agent_id", "prompt", "result", "timestamp"}``).
    """
    batch = interview_agents_batch_direct(
        simulation_id,
        [{"agent_id": agent_id, "prompt": prompt, "platform": platform}],
        platform,
        timeout,
        run_state_dir=run_state_dir,
        client_factory=client_factory,
    )
    entries = list(batch["result"]["results"].values())
    entry = entries[0] if entries else {}

    result: Dict[str, Any] = {
        "success": bool(entry.get("response")),
        "agent_id": agent_id,
        "prompt": prompt,
        "mode": "direct",
        "result": entry,
        "timestamp": batch["timestamp"],
    }
    if entry.get("error"):
        result["error"] = entry["error"]
    return result
