"""
EmbeddingService — local embedding via Ollama API

Replaces Zep Cloud's built-in embedding with a local Ollama embedding model.
Output dimension depends on the model (see Config.VECTOR_DIM).

Stub-Modus (AGORA_E2E_LLM_MODE=stub):
    embed() und embed_batch() liefern deterministischen Vector ohne Netzwerkaufruf.
    Dimension: Config.VECTOR_DIM (identisch mit Prod-Konfiguration).
    Determinismus: hash(text)-basiert, L2-normalisiert — Cosine-Similarity ist
    textspezifisch (nicht konstant 1.0), um Section-Dedup-Fehler nicht zu verschleiern.
    health_check() gibt True zurück.
"""

import math
import os
import time
import logging
from typing import List, Optional

import requests

from ..config import Config, infer_vector_dim_for_model
from ..llm.providers.registry import detect_embedding_provider

logger = logging.getLogger('agora.embedding')


def validate_embedding_configuration(
    model: Optional[str] = None,
    vector_dim: Optional[int] = None,
    base_url: Optional[str] = None,
    timeout: int = 15,
    skip_probe: bool = False,
) -> Optional[int]:
    """Fail fast if the configured embedding model/dimension combination is invalid.

    When ``skip_probe`` is True, only the static KNOWN_EMBEDDING_DIMS lookup runs
    (no network call). Returns None in that case. Used in CI environments without
    a reachable embedding backend (siehe AGORA_SKIP_EMBEDDING_PROBE).
    """
    effective_model = model or Config.EMBEDDING_MODEL
    effective_dim = vector_dim or Config.VECTOR_DIM
    effective_base_url = base_url or Config.EMBEDDING_BASE_URL

    expected_dim = infer_vector_dim_for_model(effective_model)
    if expected_dim and effective_dim != expected_dim:
        raise EmbeddingError(
            f"VECTOR_DIM={effective_dim} does not match known dimension {expected_dim} "
            f"for EMBEDDING_MODEL='{effective_model}'"
        )

    if skip_probe:
        return None

    service = EmbeddingService(
        model=effective_model,
        base_url=effective_base_url,
        api_key=Config.EMBEDDING_API_KEY,
        max_retries=3,
        timeout=timeout,
    )
    vector = service.embed("dimension probe")
    actual_dim = len(vector)

    if actual_dim != effective_dim:
        raise EmbeddingError(
            f"Embedding probe for model '{effective_model}' returned dimension {actual_dim}, "
            f"but VECTOR_DIM is configured as {effective_dim}"
        )

    return actual_dim


class EmbeddingService:
    """Generate embeddings through the independently configured embedding route.

    Chat routing and embedding configuration are deliberately separate per
    ADR-0007; this service therefore does not use the chat-provider registry.
    """

    # Class-level flag: stub-mode log wird nur einmal ausgegeben (alle Instanzen).
    _stub_mode_logged: bool = False

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 30,
    ):
        self.model = model or Config.EMBEDDING_MODEL
        self.base_url = (base_url or Config.EMBEDDING_BASE_URL).rstrip('/')
        self.api_key = api_key or Config.EMBEDDING_API_KEY or ''
        self.max_retries = max_retries
        self.timeout = timeout
        self._provider = self._detect_provider()
        self._embed_url = self._build_embed_url()

        # Simple in-memory cache (text -> embedding vector)
        # Using dict instead of lru_cache because lists aren't hashable
        self._cache: dict[str, List[float]] = {}
        self._cache_max_size = 2000

    # ------------------------------------------------------------------
    # Stub-Modus Helpers (AGORA_E2E_LLM_MODE=stub)
    # ------------------------------------------------------------------

    def _stub_vector(self, text: str) -> List[float]:
        """Erzeugt einen deterministischen, L2-normierten Vector für den Stub-Modus.

        Formel: vec[i] = ((hash(text) + i) % 1000 - 500) / 500.0, dann L2-normiert.
        Jeder Text liefert einen einzigartigen Vector — Cosine-Similarity ist NICHT
        konstant 1.0, sodass Section-Dedup-Fehler nicht verschleiert werden.

        Dimension: Config.VECTOR_DIM (identisch mit Prod-Konfiguration).
        """
        if not EmbeddingService._stub_mode_logged:
            logger.info(
                "EmbeddingService: stub-mode aktiv, dim=%d (AGORA_E2E_LLM_MODE=stub)",
                Config.VECTOR_DIM,
            )
            EmbeddingService._stub_mode_logged = True

        h = hash(text)
        dim = Config.VECTOR_DIM
        vec = [((h + i) % 1000 - 500) / 500.0 for i in range(dim)]

        # L2-Normalisierung: verhindert konstante Cosine-Similarity = 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0.0:
            vec = [v / norm for v in vec]

        return vec

    def embed(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            Float vector sized according to Config.VECTOR_DIM

        Raises:
            EmbeddingError: If Ollama request fails after retries
        """
        if not text or not text.strip():
            raise EmbeddingError("Cannot embed empty text")

        text = text.strip()

        # Stub-Modus: kein Netzwerkaufruf, deterministischer Vector.
        # Aktiviert ausschließlich via AGORA_E2E_LLM_MODE=stub (CI-Umgebung).
        if os.environ.get("AGORA_E2E_LLM_MODE") == "stub":
            stub_vec = self._stub_vector(text)
            self._cache_put(text, stub_vec)
            return stub_vec

        # Check cache
        if text in self._cache:
            return self._cache[text]

        vectors = self._request_embeddings([text])
        vector = vectors[0]

        # Cache result
        self._cache_put(text, vector)

        return vector

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Processes in batches to avoid overwhelming Ollama.

        Args:
            texts: List of input texts
            batch_size: Number of texts per request

        Returns:
            List of embedding vectors (same order as input)
        """
        if not texts:
            return []

        # Stub-Modus: kein Netzwerkaufruf, deterministischer Vector pro Text.
        # Aktiviert ausschließlich via AGORA_E2E_LLM_MODE=stub (CI-Umgebung).
        if os.environ.get("AGORA_E2E_LLM_MODE") == "stub":
            return [
                self._stub_vector(t.strip()) if (t and t.strip()) else [0.0] * Config.VECTOR_DIM
                for t in texts
            ]

        results: List[Optional[List[float]]] = [None] * len(texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        # Check cache first
        for i, text in enumerate(texts):
            text = text.strip() if text else ""
            if text in self._cache:
                results[i] = self._cache[text]
            elif text:
                uncached_indices.append(i)
                uncached_texts.append(text)
            else:
                # Empty text — zero vector (matches configured VECTOR_DIM)
                results[i] = [0.0] * Config.VECTOR_DIM

        # Batch-embed uncached texts
        if uncached_texts:
            all_vectors: List[List[float]] = []
            for start in range(0, len(uncached_texts), batch_size):
                batch = uncached_texts[start:start + batch_size]
                vectors = self._request_embeddings(batch)
                all_vectors.extend(vectors)

            # Place results and cache
            for idx, vec, text in zip(uncached_indices, all_vectors, uncached_texts):
                results[idx] = vec
                self._cache_put(text, vec)

        return results  # type: ignore

    def _request_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Make HTTP request to the configured embedding provider.

        Supports Ollama `/api/embed` and OpenAI-compatible `/v1/embeddings`.
        """
        payload = {
            "model": self.model,
            "input": texts,
        }
        headers = self._request_headers()
        provider_label = 'OpenAI-compatible' if self._provider == 'openai' else 'Ollama'

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self._embed_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                embeddings = self._extract_embeddings(data)

                if len(embeddings) != len(texts):
                    raise EmbeddingError(
                        f"Expected {len(texts)} embeddings, got {len(embeddings)}"
                    )

                return embeddings

            except requests.exceptions.ConnectionError as e:
                last_error = e
                logger.warning(
                    f"{provider_label} connection failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(
                    f"{provider_label} request timed out (attempt {attempt + 1}/{self.max_retries})"
                )
            except requests.exceptions.HTTPError as e:
                last_error = e
                body = e.response.text[:500] if e.response is not None else ''
                logger.error(
                    "%s HTTP error: %s - %s",
                    provider_label,
                    e.response.status_code if e.response is not None else 'n/a',
                    body,
                )
                if e.response is not None and e.response.status_code >= 500:
                    pass
                else:
                    raise EmbeddingError(f"{provider_label} embedding failed: {e}") from e
            except (KeyError, ValueError, TypeError) as e:
                raise EmbeddingError(f"Invalid {provider_label} response: {e}") from e

            if attempt < self.max_retries - 1:
                wait = 2 ** attempt
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

        raise EmbeddingError(
            f"{provider_label} embedding failed after {self.max_retries} retries: {last_error}"
        )

    def _detect_provider(self) -> str:
        """Infer which embeddings API shape to use from the configured base URL/model.

        Delegiert an ``detect_embedding_provider`` (SSoT-Registry,
        ``app/llm/providers/registry.py``, Issue #671). Verhalten unveraendert.
        """
        return detect_embedding_provider(self.base_url, self.model)

    def _build_embed_url(self) -> str:
        if self._provider == 'openai':
            if self.base_url.endswith('/v1') or self.base_url.endswith('/v1/'):
                return f"{self.base_url.rstrip('/')}/embeddings"
            return f"{self.base_url.rstrip('/')}/v1/embeddings"
        return f"{self.base_url}/api/embed"

    def _request_headers(self) -> dict[str, str]:
        headers = {'Content-Type': 'application/json'}
        if self._provider == 'openai':
            if not self.api_key:
                raise EmbeddingError('EMBEDDING_API_KEY/LLM_API_KEY is required for OpenAI embeddings')
            headers['Authorization'] = f'Bearer {self.api_key}'
        return headers

    def _extract_embeddings(self, data: dict) -> List[List[float]]:
        if self._provider == 'openai':
            items = data.get('data', [])
            return [item['embedding'] for item in items]
        return data.get('embeddings', [])

    def _cache_put(self, text: str, vector: List[float]) -> None:
        """Add to cache, evicting oldest entries if full."""
        if len(self._cache) >= self._cache_max_size:
            # Remove ~10% of oldest entries
            keys_to_remove = list(self._cache.keys())[:self._cache_max_size // 10]
            for key in keys_to_remove:
                del self._cache[key]
        self._cache[text] = vector

    def health_check(self) -> bool:
        """Check if Ollama embedding endpoint is reachable.

        Im Stub-Modus (AGORA_E2E_LLM_MODE=stub) wird kein Netzwerkaufruf gemacht
        — health_check() gibt immer True zurück.
        """
        if os.environ.get("AGORA_E2E_LLM_MODE") == "stub":
            return True
        try:
            vec = self.embed("health check")
            return len(vec) > 0
        except Exception:  # noqa: BLE001 — health check returns False on any error
            return False


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""
    pass
