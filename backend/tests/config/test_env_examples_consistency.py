"""Tests für die Konsistenz der Env-Beispieldateien (PR 1, Finding 1.1).

Hintergrund: Der bisherige Quickstart empfahl `cp .env.example .env` und
danach `docker compose up`. `.env.example` enthielt aber Host-Defaults
(`LLM_BASE_URL=http://localhost:11434/v1`, `EMBEDDING_BASE_URL=…/11434`,
`NEO4J_URI=bolt://localhost:7687`), die in Compose den container-internen
`localhost` meinen — und damit auf den Container selbst zeigen statt auf
Host-Ollama oder den `neo4j`-Service.

Verträge:
  A. `.env.example` darf keine *aktiv gesetzten* localhost-Default-Werte
     für `LLM_BASE_URL`, `EMBEDDING_BASE_URL` oder `NEO4J_URI` enthalten.
     Diese Schlüssel müssen entweder auskommentiert oder per
     Compose-Default überschrieben werden.
  B. `.env.docker.example` existiert und ist container-tauglich:
     `host.docker.internal` für Ollama, `bolt://neo4j:7687`,
     `EMBEDDING_MODEL=qwen3-embedding:4b` mit passendem `VECTOR_DIM=2560`.
  C. `.env.docker.example` setzt keine Geheimnis-Klartexte — `SECRET_KEY`,
     `AGORA_AUTH_TOKEN` und `NEO4J_PASSWORD` müssen vom Operator gefüllt
     werden (leerer Wert oder Generieren-Marker, kein hartcodierter Wert).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
ENV_DOCKER_EXAMPLE = REPO_ROOT / ".env.docker.example"


def _parse_active_keys(path: Path) -> Dict[str, str]:
    """Parst nur unkommentierte KEY=VALUE-Zeilen einer .env-Datei.

    Kommentar-Marker am Zeilenanfang (mit optionalem Whitespace) machen
    die Zeile zu einer Vorlage, kein aktiver Default.
    """
    result: Dict[str, str] = {}
    if not path.is_file():
        return result
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


# ---------------------------------------------------------------------------
# Vertrag A — .env.example darf keine kaputten Docker-Defaults aktiv haben
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env_example_active() -> Dict[str, str]:
    return _parse_active_keys(ENV_EXAMPLE)


def test_env_example_exists(env_example_active):
    assert ENV_EXAMPLE.is_file(), f".env.example fehlt unter {ENV_EXAMPLE}"


def test_env_example_does_not_set_active_localhost_llm_base_url(env_example_active):
    """`LLM_BASE_URL=http://localhost:...` ist im Compose-Pfad eine Falle —
    in der Vorlage muss diese Zeile auskommentiert sein."""
    value = env_example_active.get("LLM_BASE_URL", "")
    assert "localhost" not in value, (
        "LLM_BASE_URL in .env.example zeigt aktiv auf localhost. "
        "Das gewinnt gegen den Compose-Default host.docker.internal und "
        "routet im Container auf den Container selbst. Auskommentieren."
    )


def test_env_example_does_not_set_active_localhost_embedding_base_url(env_example_active):
    value = env_example_active.get("EMBEDDING_BASE_URL", "")
    assert "localhost" not in value, (
        "EMBEDDING_BASE_URL in .env.example zeigt aktiv auf localhost. "
        "Auskommentieren — sonst überschreibt der Wert den Compose-Default."
    )


def test_env_example_does_not_set_active_localhost_neo4j_uri(env_example_active):
    value = env_example_active.get("NEO4J_URI", "")
    assert "localhost" not in value, (
        "NEO4J_URI in .env.example zeigt aktiv auf localhost. Im Compose-Pfad "
        "muss bolt://neo4j:7687 gewinnen — diese Zeile auskommentieren."
    )


# ---------------------------------------------------------------------------
# Vertrag B — .env.docker.example existiert mit container-tauglichen Werten
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env_docker_example_active() -> Dict[str, str]:
    return _parse_active_keys(ENV_DOCKER_EXAMPLE)


def test_env_docker_example_exists():
    assert ENV_DOCKER_EXAMPLE.is_file(), (
        f".env.docker.example fehlt unter {ENV_DOCKER_EXAMPLE} — Quickstart "
        "verweist auf `cp .env.docker.example .env`."
    )


def test_env_docker_example_llm_base_url_uses_host_docker_internal(env_docker_example_active):
    value = env_docker_example_active.get("LLM_BASE_URL", "")
    assert "host.docker.internal" in value, (
        f"LLM_BASE_URL in .env.docker.example muss host.docker.internal "
        f"verwenden (aktuell: {value!r})."
    )


def test_env_docker_example_embedding_base_url_uses_host_docker_internal(env_docker_example_active):
    value = env_docker_example_active.get("EMBEDDING_BASE_URL", "")
    assert "host.docker.internal" in value, (
        f"EMBEDDING_BASE_URL in .env.docker.example muss host.docker.internal "
        f"verwenden (aktuell: {value!r})."
    )


def test_env_docker_example_neo4j_uri_uses_service_name(env_docker_example_active):
    value = env_docker_example_active.get("NEO4J_URI", "")
    assert value.startswith("bolt://neo4j:"), (
        f"NEO4J_URI in .env.docker.example muss den Compose-Service-Namen "
        f"`neo4j` verwenden (aktuell: {value!r})."
    )


def test_env_docker_example_embedding_dim_matches_qwen3(env_docker_example_active):
    """qwen3-embedding:4b → 2560-dim. Falsche Kombi sprengt den
    Neo4j-Vector-Index sofort beim ersten Insert."""
    model = env_docker_example_active.get("EMBEDDING_MODEL", "")
    dim = env_docker_example_active.get("VECTOR_DIM", "")
    assert model == "qwen3-embedding:4b", (
        f"EMBEDDING_MODEL in .env.docker.example sollte qwen3-embedding:4b "
        f"sein (aktuell: {model!r})."
    )
    assert dim == "2560", (
        f"VECTOR_DIM in .env.docker.example muss 2560 sein für "
        f"qwen3-embedding:4b (aktuell: {dim!r})."
    )


# ---------------------------------------------------------------------------
# Vertrag C — keine hartcodierten Geheimnisse in der Vorlage
# ---------------------------------------------------------------------------


_PLACEHOLDER_TOKENS = {
    "",
    "change-me",
    "change-me-use-token_urlsafe-32",
    "set-me",
    "generate-with-secrets.token_urlsafe-32",
}


@pytest.mark.parametrize("key", ["SECRET_KEY", "AGORA_AUTH_TOKEN", "NEO4J_PASSWORD"])
def test_env_docker_example_secrets_are_placeholders(env_docker_example_active, key):
    """Die Docker-Vorlage darf keine echten Geheimnisse hartkodieren.
    Operator soll die Werte bewusst generieren / setzen."""
    value = env_docker_example_active.get(key, "")
    assert value in _PLACEHOLDER_TOKENS, (
        f"{key} in .env.docker.example darf kein hartcodiertes Geheimnis "
        f"sein — aktuell: {value!r}. Akzeptierte Platzhalter: "
        f"{sorted(_PLACEHOLDER_TOKENS)}."
    )
