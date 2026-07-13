"""API fuer Embedding-Migration und Ollama-Download (Onboarding Slice 4.3).

Routen unter ``/api/llm/embedding/``:

* ``POST /migrations`` startet eine neue Re-Embedding-Migration fuer eine
  Konfiguration. Body: ``{\"configuration_id\": \"emb-1\"}`` (oder ohne
  Body, wenn die globale aktive Konfiguration gemeint ist).
* ``GET  /migrations`` listet alle Migrations-Jobs (optional mit
  ``?configuration_id=...``).
* ``GET  /migrations/<job_id>`` liefert einen einzelnen Job.
* ``POST /migrations/<job_id>/run`` zieht die Migration durch den
  kompletten Lifecycle.
* ``POST /migrations/<job_id>/cancel`` bricht die Migration ab.
* ``POST /ollama/pull`` laedt ein Ollama-Embedding-Modell herunter.
  Body: ``{\"model\": \"nomic-embed-text\", \"configuration_id\": \"...\"}``.

Die Routen folgen dem Slice-3/4.2-Stil: ``handle_api_errors``-Decorator,
``json_success``/``json_error``, ``KeyError`` -> 404, ``ValueError`` ->
  400/409. Die zugrundeliegende Geschäftslogik liegt im Service
  (``app.services.embedding_migration`` und
  ``app.services.embedding_ollama_pull``).
"""

from __future__ import annotations

from flask import request
from pydantic import BaseModel, ConfigDict, Field

from . import llm_bp
from ..config import Config
from ..contracts.embedding_contract import EmbeddingConfiguration
from ..services.embedding_configuration_store import EmbeddingConfigurationStore
from ..services.embedding_migration import EmbeddingMigrationService
from ..services.embedding_ollama_pull import OllamaPullError, pull_model_via_configuration
from ..services.embedding_reembedder import EmbedTexts, Neo4jReEmbedder
from ..services.llm_provider_secrets_store import get_llm_provider_secrets_store
from ..services.provider_connection_store import ProviderConnectionStore
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.logger import get_logger

logger = get_logger("agora.api.embedding_migrations")

_STRICT = ConfigDict(extra="forbid")


class _StartMigrationRequest(BaseModel):
    model_config = _STRICT

    configuration_id: str = Field(min_length=1)


class _OllamaPullRequest(BaseModel):
    model_config = _STRICT

    model: str = Field(min_length=1, max_length=100)
    configuration_id: str | None = None


def _neo4j_driver():
    """Eigener, lazy erzeugter Driver — die Engine schliesst ihn nach dem Lauf.

    Bewusst kein Zugriff auf den ``Neo4jStorage``-Pool: der Migrationslauf
    ist ein langlaufender Operator-Vorgang und soll den App-Pool nicht
    blockieren.
    """
    from neo4j import GraphDatabase

    return GraphDatabase.driver(
        Config.NEO4J_URI, auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
    )


def _embedder_for_configuration(config: EmbeddingConfiguration) -> EmbedTexts:
    """Baut die Batch-Embedding-Funktion fuer die Ziel-Konfiguration.

    Aufloesung analog zum Probe-Pfad (``EmbeddingConfigurationService``):
    ProviderConnection liefert die ``base_url``, der Secret-Store den
    API-Key. Gemini nutzt ein anderes URL-Schema als der bestehende
    ``EmbeddingService`` und wird ehrlich abgelehnt statt vorgetaeuscht.
    """
    if config.provider_kind == "google":
        raise RuntimeError(
            "Re-Embedding ueber Gemini wird noch nicht unterstuetzt — "
            "bitte einen Ollama- oder OpenAI-kompatiblen Embedding-"
            "Provider verwenden."
        )
    connection = next(
        (
            c
            for c in ProviderConnectionStore().list_connections()
            if c.id == config.provider_connection_id
        ),
        None,
    )
    if connection is None:
        raise KeyError(
            f"ProviderConnection fehlt: {config.provider_connection_id}"
        )
    api_key = (
        get_llm_provider_secrets_store().get_plaintext(connection.secret_ref)
        if connection.secret_ref
        else None
    )
    from ..storage.embedding_service import EmbeddingService

    service = EmbeddingService(
        model=config.model_id,
        base_url=connection.base_url,
        api_key=api_key,
        timeout=60,
    )
    return service.embed_batch


def _service() -> EmbeddingMigrationService:
    return EmbeddingMigrationService(
        store=EmbeddingConfigurationStore(),
        re_embedder=Neo4jReEmbedder(
            driver_factory=_neo4j_driver,
            embedder_factory=_embedder_for_configuration,
        ),
    )


# ---------------------------------------------------------------------------
# Migrations-Lifecycle
# ---------------------------------------------------------------------------


@llm_bp.route("/embedding/migrations", methods=["POST"])
@handle_api_errors(logger=logger)
def start_embedding_migration():
    """Startet eine neue Re-Embedding-Migration."""
    body = request.get_json(silent=True) or {}
    try:
        parsed = _StartMigrationRequest.model_validate(body)
    except ValueError as exc:
        # Pydantic wirft einen ValidationError (Subklasse von ValueError);
        # wir normalisieren auf 400 mit den strukturierten Fehler-Daten.
        return json_error(
            "Invalid migration request",
            status=400,
            code="invalid_request",
            extra={"errors": exc.errors(include_url=False)},
        )
    try:
        job = _service().start(parsed.configuration_id)
    except KeyError as exc:
        return json_error(str(exc), status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=409, code="invalid_status_transition")
    return json_success({"job": job.model_dump(mode="json")})


@llm_bp.route("/embedding/migrations", methods=["GET"])
@handle_api_errors(logger=logger)
def list_embedding_migrations():
    configuration_id = request.args.get("configuration_id")
    jobs = _service().list_jobs(configuration_id=configuration_id)
    return json_success(
        {
            "jobs": [j.model_dump(mode="json") for j in jobs],
        }
    )


@llm_bp.route("/embedding/migrations/<job_id>", methods=["GET"])
@handle_api_errors(logger=logger)
def get_embedding_migration(job_id: str):
    job = _service().get_job(job_id)
    if job is None:
        return json_error(
            f"Unbekannter Migration-Job: {job_id}",
            status=404,
            code="not_found",
        )
    return json_success({"job": job.model_dump(mode="json")})


@llm_bp.route("/embedding/migrations/<job_id>/run", methods=["POST"])
@handle_api_errors(logger=logger)
def run_embedding_migration(job_id: str):
    try:
        final = _service().run(job_id)
    except KeyError as exc:
        return json_error(str(exc), status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=409, code="invalid_status_transition")
    return json_success({"job": final.model_dump(mode="json")})


@llm_bp.route("/embedding/migrations/<job_id>/cancel", methods=["POST"])
@handle_api_errors(logger=logger)
def cancel_embedding_migration(job_id: str):
    try:
        final = _service().cancel(job_id)
    except KeyError as exc:
        return json_error(str(exc), status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=409, code="invalid_status_transition")
    return json_success({"job": final.model_dump(mode="json")})


# ---------------------------------------------------------------------------
# Ollama-Download
# ---------------------------------------------------------------------------


@llm_bp.route("/embedding/ollama/pull", methods=["POST"])
@handle_api_errors(logger=logger)
def pull_ollama_embedding_model():
    body = request.get_json(silent=True) or {}
    try:
        parsed = _OllamaPullRequest.model_validate(body)
    except ValueError as exc:
        return json_error(
            "Invalid Ollama-pull request",
            status=400,
            code="invalid_request",
            extra={"errors": exc.errors(include_url=False)},
        )
    try:
        report = pull_model_via_configuration(
            model=parsed.model,
            configuration_id=parsed.configuration_id,
            connection_store=ProviderConnectionStore(),
            secrets_store=get_llm_provider_secrets_store(),
        )
    except OllamaPullError as exc:
        return json_error(str(exc), status=502, code="upstream_error")
    except KeyError as exc:
        return json_error(str(exc), status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=400, code="invalid_request")
    return json_success({"report": report.__dict__})
