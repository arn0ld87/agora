import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.config import Config, infer_vector_dim_for_model
from app.llm.providers.registry import detect_embedding_provider
from app.storage.embedding_service import (
    EmbeddingBackendUnavailableError,
    EmbeddingError,
    EmbeddingService,
    validate_embedding_configuration,
)


@pytest.mark.parametrize(
    ("base_url", "model"),
    [
        ("http://localhost:11434/v1", "nomic-embed-text"),
        ("http://localhost:11434", "nomic-embed-text"),
        ("https://api.openai.com", "text-embedding-3-small"),
        ("http://localhost:11434", "text-embedding-3-small"),
    ],
)
def test_detect_provider_delegates_to_registry_ssot(base_url, model):
    """Issue #671 — EmbeddingService._detect_provider MUSS byte-genau das
    liefern, was detect_embedding_provider() (SSoT-Registry) liefert. Kein
    lokal divergentes Verhalten mehr."""
    service = EmbeddingService(model=model, base_url=base_url, api_key='dummy-key')
    assert service._detect_provider() == detect_embedding_provider(base_url, model)


def test_embed_uses_embedding_specific_openai_shape_from_hostname(monkeypatch):
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
    response = MagicMock()
    response.json.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

    with patch("app.storage.embedding_service.requests.post", return_value=response) as post:
        vector = EmbeddingService(
            model="custom-embedding-model",
            base_url="https://api.openai.com/custom",
            api_key="sk-test",
            max_retries=1,
        ).embed("document")

    assert vector == [0.1, 0.2]
    assert post.call_args.args[0] == "https://api.openai.com/custom/v1/embeddings"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-test"


def test_embed_keeps_ollama_embedding_detection_separate(monkeypatch):
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
    response = MagicMock()
    response.json.return_value = {"embeddings": [[0.3, 0.4]]}

    with patch("app.storage.embedding_service.requests.post", return_value=response) as post:
        vector = EmbeddingService(
            # api_key="" explizit — siehe Begruendung an ``_service()``.
            model="nomic-embed-text",
            base_url="http://ollama.internal:11434",
            api_key="",
            max_retries=1,
        ).embed("document")

    assert vector == [0.3, 0.4]
    assert post.call_args.args[0] == "http://ollama.internal:11434/api/embed"
    assert "Authorization" not in post.call_args.kwargs["headers"]


@pytest.mark.parametrize(
    ("base_url", "expected_url"),
    [
        # Gemini OpenAI-Compat-Endpoint enthaelt bereits ``/v1beta/openai`` —
        # ein zusaetzliches ``/v1``-Segment wuerde ``/v1beta/openai/v1/embeddings``
        # ergeben und 404 antworten. Direkt ``/embeddings`` anhängen.
        ("https://generativelanguage.googleapis.com/v1beta/openai", "https://generativelanguage.googleapis.com/v1beta/openai/embeddings"),
        ("https://generativelanguage.googleapis.com/v1beta/openai/", "https://generativelanguage.googleapis.com/v1beta/openai/embeddings"),
    ],
)
def test_embed_uses_gemini_openai_compat_url_without_extra_v1_segment(
    monkeypatch, base_url: str, expected_url: str
) -> None:
    """Issue: Gemini OpenAI-Compat-Endpoint darf NICHT zu ``/v1beta/openai/v1/embeddings`` werden.

    Der Endpunkt akzeptiert nur ``/v1beta/openai/embeddings`` direkt — ein
    weiteres ``/v1``-Segment wuerde 404 auslösen. Regressionstest fuer den
    Whitelist-Suffix in ``EmbeddingService._build_embed_url``.
    """
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
    response = MagicMock()
    response.json.return_value = {"data": [{"embedding": [0.5, 0.6]}]}

    with patch("app.storage.embedding_service.requests.post", return_value=response) as post:
        vector = EmbeddingService(
            model="text-embedding-3-small",
            base_url=base_url,
            api_key="sk-test",
            max_retries=1,
        ).embed("document")

    assert vector == [0.5, 0.6]
    assert post.call_args.args[0] == expected_url
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-test"


def test_infer_vector_dim_for_known_models():
    assert infer_vector_dim_for_model('nomic-embed-text') == 768
    assert infer_vector_dim_for_model('nomic-embed-text:latest') == 768
    assert infer_vector_dim_for_model('qwen3-embedding:4b') == 2560
    assert infer_vector_dim_for_model('qwen3-embedding:8b') == 4096


def test_infer_vector_dim_for_gemini_embedding_001_is_3072():
    """gemini-embedding-001 liefert 3072, nicht 768.

    ``KNOWN_EMBEDDING_DIMS`` fuehrte 768 — den Matryoshka-Kuerzungswert, nicht
    die Default-Ausgabe. Das Modell antwortet per Default mit 3072 Dimensionen
    und laesst sich nur ueber ``output_dimensionality`` kuerzen; der
    OpenAI-Compat-Pfad in ``EmbeddingService`` sendet diesen Parameter nicht.
    Mit dem alten Wert legte Agora den Neo4j-Vektorindex auf 768 an und der
    erste echte Embed-Call scheiterte am Dimension-Mismatch.

    ``gemini-embedding-2`` wird mitgeprueft: beide Schluessel teilen sich das
    Praefix ``gemini-embedding-``, und ``infer_vector_dim_for_model`` matcht
    per ``startswith`` ueber ein Dict — ein hier eingefuegter kuerzerer
    Schluessel wuerde den laengeren verschatten.
    """
    assert infer_vector_dim_for_model('gemini-embedding-001') == 3072
    assert infer_vector_dim_for_model('gemini-embedding-2') == 3072


def test_validate_embedding_configuration_rejects_stale_gemini_768():
    """Der alte 768er-Wert wird als Mismatch abgelehnt, nicht stillschweigend akzeptiert.

    Pinnt die Korrektur auch im Validierungspfad: wer ``VECTOR_DIM=768`` gegen
    ``gemini-embedding-001`` konfiguriert, bekommt beim Start einen harten
    Fehler statt eines Neo4j-Index in falscher Form.
    """
    with pytest.raises(
        EmbeddingError, match='VECTOR_DIM=768 does not match known dimension 3072'
    ):
        validate_embedding_configuration(
            model='gemini-embedding-001',
            vector_dim=768,
            base_url='https://generativelanguage.googleapis.com/v1beta/openai',
        )


def test_validate_embedding_configuration_rejects_known_dim_mismatch():
    with pytest.raises(EmbeddingError, match='VECTOR_DIM=768 does not match known dimension 2560'):
        validate_embedding_configuration(
            model='qwen3-embedding:4b',
            vector_dim=768,
            base_url='http://localhost:11434',
        )


def test_validate_embedding_configuration_rejects_runtime_dim_mismatch():
    with patch('app.storage.embedding_service.EmbeddingService.embed', return_value=[0.0] * 2560):
        with pytest.raises(EmbeddingError, match='returned dimension 2560, but VECTOR_DIM is configured as 768'):
            validate_embedding_configuration(
                model='custom-embed-model',
                vector_dim=768,
                base_url='http://localhost:11434',
            )


def test_validate_embedding_configuration_returns_actual_dimension_on_success():
    with patch('app.storage.embedding_service.EmbeddingService.embed', return_value=[0.0] * 2560):
        actual_dim = validate_embedding_configuration(
            model='qwen3-embedding:4b',
            vector_dim=2560,
            base_url='http://localhost:11434',
        )

    assert actual_dim == 2560


def test_validate_embedding_configuration_skip_probe_returns_none():
    """When skip_probe=True, no network call is made and None is returned."""
    with patch('app.storage.embedding_service.EmbeddingService.embed') as mock_embed:
        result = validate_embedding_configuration(
            model='qwen3-embedding:4b',
            vector_dim=2560,
            base_url='http://nonexistent:11434',
            skip_probe=True,
        )
    assert result is None
    mock_embed.assert_not_called()


def test_validate_embedding_configuration_skip_probe_still_rejects_known_dim_mismatch():
    """skip_probe must not bypass the static KNOWN_EMBEDDING_DIMS check."""
    with pytest.raises(EmbeddingError, match='VECTOR_DIM=768 does not match known dimension 2560'):
        validate_embedding_configuration(
            model='qwen3-embedding:4b',
            vector_dim=768,
            base_url='http://nonexistent:11434',
            skip_probe=True,
        )


def test_validate_embedding_configuration_default_still_probes():
    """Default behavior (skip_probe omitted/False) preserves the network probe."""
    with patch('app.storage.embedding_service.EmbeddingService.embed', return_value=[0.0] * 768) as mock_embed:
        result = validate_embedding_configuration(
            model='nomic-embed-text',
            vector_dim=768,
            base_url='http://localhost:11434',
        )
    assert result == 768
    mock_embed.assert_called_once()


# ---------------------------------------------------------------------------
# Stub-Modus Tests (AGORA_E2E_LLM_MODE=stub)
# ---------------------------------------------------------------------------

class TestEmbeddingServiceStubMode:
    """EmbeddingService im Stub-Modus liefert deterministischen Vector ohne Netzwerk."""

    def test_stub_embed_returns_correct_dimension(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """embed() im Stub-Modus liefert Vector mit len == Config.VECTOR_DIM."""
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        EmbeddingService._stub_mode_logged = False  # Zustand zurücksetzen

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")
        vec = svc.embed("hallo welt")

        assert len(vec) == Config.VECTOR_DIM, (
            f"Stub-Vector muss dim={Config.VECTOR_DIM} haben, war {len(vec)}"
        )

    def test_stub_embed_is_deterministic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """embed() im Stub-Modus ist bytewise deterministisch (gleicher Text → gleicher Vector)."""
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        EmbeddingService._stub_mode_logged = False

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")
        v1 = svc.embed("deterministic text")
        v2 = svc.embed("deterministic text")

        assert v1 == v2, "Gleicher Text muss gleichen Stub-Vector liefern"

    def test_stub_embed_different_texts_produce_different_vectors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """embed() im Stub-Modus liefert verschiedene Vektoren für verschiedene Texte.

        Verhindert, dass Cosine-Similarity konstant 1.0 ist und Section-Dedup-Fehler
        verschleiert werden.
        """
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        EmbeddingService._stub_mode_logged = False

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")
        v1 = svc.embed("text alpha")
        v2 = svc.embed("text beta")

        assert v1 != v2, "Verschiedene Texte müssen verschiedene Stub-Vektoren liefern"

    def test_stub_embed_batch_returns_correct_count_and_dimension(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """embed_batch() im Stub-Modus liefert Liste mit korrekter Länge und Dimension."""
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        EmbeddingService._stub_mode_logged = False

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")
        batch = svc.embed_batch(["a", "b", "c"])

        assert len(batch) == 3
        for vec in batch:
            assert len(vec) == Config.VECTOR_DIM, (
                f"Stub-Batch-Vector muss dim={Config.VECTOR_DIM} haben, war {len(vec)}"
            )

    def test_stub_health_check_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """health_check() im Stub-Modus gibt True ohne Netzwerkaufruf."""
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")
        assert svc.health_check() is True

    def test_stub_no_network_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Im Stub-Modus wird _request_embeddings() niemals aufgerufen."""
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        EmbeddingService._stub_mode_logged = False

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")

        with patch.object(svc, "_request_embeddings") as mock_req:
            svc.embed("kein netzwerk bitte")
            svc.embed_batch(["a", "b"])
            mock_req.assert_not_called()

    def test_stub_vector_is_l2_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Stub-Vector ist L2-normiert (|v|₂ ≈ 1.0)."""
        import math
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        EmbeddingService._stub_mode_logged = False

        svc = EmbeddingService(model="nomic-embed-text", base_url="http://x:11434")
        vec = svc.embed("normalization test")

        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 1e-9, f"Stub-Vector ist nicht L2-normiert: |v|₂={norm}"


# ---------------------------------------------------------------------------
# Provider-Ausfall vs. Fehlkonfiguration
#
# Am 12.08.2026 hat Googles Spend Cap den Embeddings-Endpunkt dauerhaft mit
# 429 antworten lassen. Weil create_app() jeden EmbeddingError als fatal
# behandelt hat, ist das Backend in einen Crash-Loop gelaufen (162 Restarts)
# und agora-nginx lieferte 502 auf /api/*. Ein erschöpftes Kontingent ist
# aber kein Konfigurationsfehler: die Config ist korrekt, der Provider ist
# nur gerade nicht verfügbar.
#
# Die Trennung verläuft entlang der Frage "hilft ein Neustart?":
#   - 429 / 5xx / Connection / Timeout -> EmbeddingBackendUnavailableError
#     (transient, Neustart hilft nicht, Betrieb degradiert weiter)
#   - 401 / 403 / 404 / Dimension-Mismatch -> EmbeddingError
#     (echte Fehlkonfiguration, muss laut und fatal sein)
# ---------------------------------------------------------------------------


def _http_error(status: int) -> requests.exceptions.HTTPError:
    """Baut einen HTTPError mit echtem Response-Objekt (Status + Body)."""
    response = MagicMock()
    response.status_code = status
    response.text = f"body for {status}"
    error = requests.exceptions.HTTPError(f"{status} Error")
    error.response = response
    return error


def _service(max_retries: int = 1) -> EmbeddingService:
    # ``api_key=""`` explizit: ohne das Argument faellt der Konstruktor auf
    # ``Config.EMBEDDING_API_KEY`` zurueck. Ist in der Umgebung des Entwicklers
    # ein Embedding-Key gesetzt, schlaegt
    # ``ensure_credentialed_transport_security`` fuer den http-Host zu und der
    # Test scheitert im Konstruktor mit ``InsecureTransportError`` — bevor er
    # ueberhaupt beim Statuscode-Verhalten ankommt. ``Config`` liest das Env
    # beim Import, ein ``monkeypatch.delenv`` im Test kaeme zu spaet.
    return EmbeddingService(
        model="nomic-embed-text",
        base_url="http://ollama.internal:11434",
        api_key="",
        max_retries=max_retries,
    )


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_provider_failure_is_backend_unavailable(monkeypatch, status):
    """429 (Quota) und 5xx sind Provider-Ausfälle, keine Fehlkonfiguration."""
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
    monkeypatch.setattr("app.storage.embedding_service.time.sleep", lambda _s: None)

    response = MagicMock()
    response.raise_for_status.side_effect = _http_error(status)

    with patch("app.storage.embedding_service.requests.post", return_value=response):
        with pytest.raises(EmbeddingBackendUnavailableError):
            _service().embed("dokument")


@pytest.mark.parametrize("status", [401, 403, 404])
def test_misconfiguration_stays_fatal(monkeypatch, status):
    """Falscher Key oder fehlendes Modell bleibt ein harter Konfigurationsfehler.

    404 ist der Fall "model not found, try pulling it first" — daran soll der
    Start weiterhin scheitern, sonst läuft Agora dauerhaft ohne Embeddings.
    """
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
    monkeypatch.setattr("app.storage.embedding_service.time.sleep", lambda _s: None)

    response = MagicMock()
    response.raise_for_status.side_effect = _http_error(status)

    with patch("app.storage.embedding_service.requests.post", return_value=response):
        with pytest.raises(EmbeddingError) as excinfo:
            _service().embed("dokument")

    assert not isinstance(excinfo.value, EmbeddingBackendUnavailableError), (
        f"HTTP {status} ist eine Fehlkonfiguration und darf nicht als "
        f"transienter Provider-Ausfall durchgehen"
    )


def test_google_quota_exhaustion_is_backend_unavailable(monkeypatch):
    """Der Vorfall selbst: gemini-embedding-001 antwortet 429 wegen Spend Cap.

    Die uebrigen Faelle hier bauen einen Ollama-foermigen Service
    (``ollama.internal`` → ``/api/embed``). Ausgefallen ist am 12.08.2026 aber
    der Google-Pfad — ``generativelanguage.googleapis.com/v1beta/openai``
    → ``/embeddings``, und zwar mit dem Modell, auf dem diese Installation
    produktiv laeuft. ``_build_embed_url`` verzweigt pro Provider, die
    Fehlerklassifikation in ``_request_embeddings`` ist dagegen gemeinsam;
    dieser Test haelt fest, dass die Verzweigung daran nichts aendert, und
    bildet den dokumentierten Vorfall 1:1 ab statt einen Nachbarpfad.
    """
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
    monkeypatch.setattr("app.storage.embedding_service.time.sleep", lambda _s: None)

    response = MagicMock()
    response.raise_for_status.side_effect = _http_error(429)

    service = EmbeddingService(
        model="gemini-embedding-001",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="test-key",
        max_retries=1,
    )

    with patch(
        "app.storage.embedding_service.requests.post", return_value=response
    ) as post:
        with pytest.raises(EmbeddingBackendUnavailableError):
            service.embed("dokument")

    assert post.call_args.args[0] == (
        "https://generativelanguage.googleapis.com/v1beta/openai/embeddings"
    )


def test_connection_error_is_backend_unavailable(monkeypatch):
    """Nicht erreichbarer Embedding-Host ist ebenfalls transient."""
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
    monkeypatch.setattr("app.storage.embedding_service.time.sleep", lambda _s: None)

    with patch(
        "app.storage.embedding_service.requests.post",
        side_effect=requests.exceptions.ConnectionError("connection refused"),
    ):
        with pytest.raises(EmbeddingBackendUnavailableError):
            _service().embed("dokument")


def _prepare_startup_env(monkeypatch):
    """Bringt create_app() bis zum Embedding-Block.

    Ohne ``AGORA_ALLOW_ANONYMOUS`` scheitert ``Config.validate()`` vorher am
    fehlenden ``AGORA_AUTH_TOKEN`` (das conftest-Fixture setzt ihn bewusst auf
    Leerstring) — der Test wuerde dann gruen sein, ohne den Embedding-Pfad je
    erreicht zu haben.
    """
    monkeypatch.setenv("FLASK_DEBUG", "false")
    monkeypatch.setenv("AGORA_ALLOW_ANONYMOUS", "true")
    monkeypatch.delenv("AGORA_CORS_ALLOW_ALL", raising=False)
    monkeypatch.delenv("AGORA_SKIP_EMBEDDING_PROBE", raising=False)

    from app.config import Config as _Config
    monkeypatch.setattr(_Config, "DEBUG", False)


def test_create_app_survives_unavailable_embedding_backend(monkeypatch):
    """Regression: ein 429 des Providers darf create_app() NICHT abbrechen.

    Das ist der Defekt hinter dem Crash-Loop vom 12.08.2026. Geprueft wird der
    degradierte Zweig selbst (Log + Flag), nicht ein vollstaendig
    hochgefahrenes Backend — spaetere Startschritte wie Neo4j sind hier
    ausdruecklich egal, solange sie nicht am Embedding scheitern.
    """
    _prepare_startup_env(monkeypatch)
    monkeypatch.setattr(
        "app.storage.embedding_service.validate_embedding_configuration",
        MagicMock(side_effect=EmbeddingBackendUnavailableError("429 quota exceeded")),
    )

    from app import create_app

    # Spy auf dem 'agora'-Logger statt caplog: create_app() konfiguriert das
    # Logging waehrend des Starts neu (``setup_logger('agora')``) und setzt
    # dabei Handler und propagate zurueck — caplog sieht davon nichts. Das
    # Logger-Objekt selbst ist prozessweit gecacht, die Identitaet bleibt also
    # ueber den create_app()-Aufruf hinweg stabil.
    error_spy = MagicMock()
    monkeypatch.setattr(logging.getLogger("agora"), "error", error_spy)

    app = create_app()

    assert app.config.get("EMBEDDING_DEGRADED") is True, (
        "Degradierter Start muss als solcher markiert sein"
    )
    assert any(
        "DEGRADED" in str(call.args[0]) for call in error_spy.call_args_list if call.args
    ), (
        "Der degradierte Start muss laut geloggt werden, sonst faellt der "
        "Ausfall im Betrieb nicht auf"
    )


def test_create_app_still_fails_on_embedding_misconfiguration(monkeypatch):
    """Gegenprobe: echte Fehlkonfiguration bleibt fatal."""
    _prepare_startup_env(monkeypatch)
    monkeypatch.setattr(
        "app.storage.embedding_service.validate_embedding_configuration",
        MagicMock(side_effect=EmbeddingError("VECTOR_DIM=768 does not match 3072")),
    )

    from app import create_app

    with pytest.raises(RuntimeError, match="Embedding configuration invalid"):
        create_app()
