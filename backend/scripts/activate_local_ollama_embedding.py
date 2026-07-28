"""Activate local Ollama embedding configuration (Issue #934).

Liest ``Config.EMBEDDING_*`` aus der Umgebung und pinnt die aktive
``EmbeddingConfiguration`` ueber die Store-API auf das konfigurierte
Modell. Idempotent — wiederholte Aufrufe konvergieren in den gleichen
Zustand.

Verwendung (aus ``backend/``):

    uv run python -m scripts.activate_local_ollama_embedding
    uv run python -m scripts.activate_local_ollama_embedding \
        --model embeddinggemma:300m --dimensions 768

Ausgabe: JSON-Report mit der aktivierten ``EmbeddingConfiguration`` auf
stdout. Der vorherige aktive Konfigurationsknoten wird auf
``status='rolled_back'`` gesetzt (Audit-Trail; nicht geloescht).

Read-only-Disclaimer: dieses Skript schreibt ausschliesslich ueber
``EmbeddingConfigurationStore`` und ``ProviderConnectionStore`` — keine
direkten Cypher- oder File-Schreibwege.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ``scripts/`` liegt ausserhalb des ``app``-Package — sicherstellen, dass
# ``backend/`` importierbar ist, unabhaengig vom aktuellen Working-Dir.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Config  # noqa: E402
from app.services.embedding_configuration_store import (  # noqa: E402
    EmbeddingConfigurationStore,
)
from app.services.embedding_configurations.activate_ollama import (  # noqa: E402
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_DIMENSIONS,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_DISPLAY_NAME,
    activate_ollama_embedding,
)
from app.services.llm_provider_secrets_store import (  # noqa: E402
    LlmProviderSecretsStore,
)
from app.services.provider_connection_store import (  # noqa: E402
    ProviderConnectionStore,
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="activate_local_ollama_embedding",
        description=(
            "Pinnt die aktive Embedding-Konfiguration auf lokales Ollama. "
            "Idempotent; vorherige aktive Konfigurationen werden auf "
            "status='rolled_back' gesetzt (Audit-Trail)."
        ),
    )
    default_model = (Config.EMBEDDING_MODEL or "").strip() or DEFAULT_OLLAMA_MODEL
    parser.add_argument(
        "--model",
        default=default_model,
        help=(
            "Embedding-Modell (default: Config.EMBEDDING_MODEL oder "
            f"{DEFAULT_OLLAMA_MODEL!r})."
        ),
    )
    parser.add_argument(
        "--dimensions",
        type=int,
        default=Config.VECTOR_DIM or DEFAULT_OLLAMA_DIMENSIONS,
        help=(
            "Vektor-Dimension (default: Config.VECTOR_DIM oder "
            f"{DEFAULT_OLLAMA_DIMENSIONS})."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_OLLAMA_BASE_URL,
        help=(
            "Loopback-Base-URL fuer die ProviderConnection-Metadaten. "
            "Die Runtime-URL (z.B. http://host.docker.internal:11434) "
            "wird weiterhin ueber Config.EMBEDDING_BASE_URL aufgeloest."
        ),
    )
    parser.add_argument(
        "--display-name",
        default=DEFAULT_OLLAMA_DISPLAY_NAME,
        help="Display-Name der ProviderConnection.",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help=(
            "Optionales AGORA_DATA_DIR. Default: aus Umgebung oder "
            "Repo-Default."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.data_dir:
        os.environ["AGORA_DATA_DIR"] = args.data_dir

    configuration_store = EmbeddingConfigurationStore()
    connection_store = ProviderConnectionStore()
    secrets_store = LlmProviderSecretsStore()

    active = activate_ollama_embedding(
        model_id=args.model,
        dimensions=args.dimensions,
        base_url=args.base_url,
        display_name=args.display_name,
        configuration_store=configuration_store,
        connection_store=connection_store,
        secrets_store=secrets_store,
    )
    report = {
        "activated": active.model_dump(mode="json"),
        "note": (
            "Konfigurations-Knoten ist jetzt aktiv. Vorhandene aktive "
            "Konfigurationen im selben Scope wurden auf "
            "status='rolled_back' gesetzt (Audit-Trail; nicht geloescht)."
        ),
    }
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
