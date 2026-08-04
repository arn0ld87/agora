"""Performance-Budget-Tests für Persona-Generierung (Issue #217 Stufe 1: Messung).

Stufe 1 ist deterministisch (Mock-LLM, kein echter Ollama-Call) und läuft
im Default-CI. Stufe 2 (echter LLM, -m 'perf and llm') folgt als separater
Slice, der das ≥ 30 %-Reduktionsziel von Issue #217 messen kann.

Hinweis zum Logging-Capture:
    Das `agora`-Logger-Setup setzt ``propagate=False`` auf dem Parent-Logger
    (``setup_logger`` in ``app/utils/logger.py``). pytest's ``caplog``-Fixture
    hängt ihren Handler am Root-Logger ein und erfasst daher keine Records aus
    ``agora.*``-Loggern. Stattdessen wird ein eigener Handler direkt an
    ``agora.llm_latency`` gehängt (etabliertes Muster, siehe
    ``tests/api/test_logs_stream_reconnect.py`` und ``tests/test_llm_client.py``).

Stufe 2a (Issue #217):
    ``test_generate_profiles_from_entities_resolves_parallel_count_from_env`` —
    deterministisch, kein LLM, prüft dass ``parallel_count=None`` korrekt aus env
    aufgelöst wird (Default CI).

    ``test_persona_generation_perf_real_llm`` — Real-LLM-Bench, Marker ``perf``
    und ``llm``. Läuft NUR manuell via ``pytest -m 'perf and llm'``; wird NICHT
    im Default-CI ausgeführt. Benötigt LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME
    im env.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import pytest

from app.utils.llm_latency import measure_llm_latency

pytestmark = pytest.mark.perf


# ---------------------------------------------------------------------------
# Hilfsfunktion: temporären Record-Capture-Handler an agora.llm_latency hängen
# ---------------------------------------------------------------------------


class _RecordCapture(logging.Handler):
    """Minimaler Handler, der LogRecords in einer Liste sammelt."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _attach_capture() -> tuple[logging.Logger, _RecordCapture]:
    """Hängt einen frischen _RecordCapture an 'agora.llm_latency' und gibt beides zurück."""
    target = logging.getLogger('agora.llm_latency')
    # Sicherstellen, dass Records diesen Logger erreichen
    target.setLevel(logging.DEBUG)
    capture = _RecordCapture()
    target.addHandler(capture)
    return target, capture


def _detach_capture(target: logging.Logger, capture: _RecordCapture) -> None:
    target.removeHandler(capture)


# ---------------------------------------------------------------------------
# Test 1: Decorator emittiert strukturierten Log-Record bei Erfolg
# ---------------------------------------------------------------------------


def test_measure_llm_latency_emits_structured_log():
    @measure_llm_latency(operation='unit_test_op')
    def fake_call(model: str = 'qwen2.5:14b') -> dict[str, Any]:
        time.sleep(0.01)
        return {'ok': True}

    target, capture = _attach_capture()
    try:
        result = fake_call(model='qwen2.5:14b')
    finally:
        _detach_capture(target, capture)

    assert result == {'ok': True}
    records = [r for r in capture.records if r.name == 'agora.llm_latency']
    assert len(records) == 1
    rec = records[0]
    assert rec.operation == 'unit_test_op'  # type: ignore[attr-defined]
    assert rec.function == 'test_measure_llm_latency_emits_structured_log.<locals>.fake_call'  # type: ignore[attr-defined]
    assert rec.latency_ms >= 10.0  # type: ignore[attr-defined]
    assert rec.latency_ms < 1000.0  # type: ignore[attr-defined]
    assert rec.roundtrips == 1  # type: ignore[attr-defined]
    assert rec.success is True  # type: ignore[attr-defined]
    assert rec.error_type is None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test 2: Decorator loggt auch bei Exception, re-raised Exception sauber
# ---------------------------------------------------------------------------


def test_measure_llm_latency_logs_on_exception():
    @measure_llm_latency(operation='failing_op')
    def fake_call() -> None:
        raise RuntimeError('boom')

    target, capture = _attach_capture()
    try:
        with pytest.raises(RuntimeError, match='boom'):
            fake_call()
    finally:
        _detach_capture(target, capture)

    records = [r for r in capture.records if r.name == 'agora.llm_latency']
    assert len(records) == 1
    rec = records[0]
    assert rec.success is False  # type: ignore[attr-defined]
    assert rec.error_type == 'RuntimeError'  # type: ignore[attr-defined]
    assert rec.roundtrips == 1  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test 3: __wrapped__ bestätigt Decorator auf _generate_profile_with_llm
# ---------------------------------------------------------------------------


def test_generate_profile_with_llm_decorator_applied():
    """Prüft, dass @measure_llm_latency tatsächlich auf die Methode appliziert wurde.

    Komplexes Mocking (Neo4jStorage, EntityNode, Container-Init) ist unverhältnismäßig
    für Stufe 1. Stattdessen: functools.wraps setzt __wrapped__ — dessen Existenz
    beweist, dass der Decorator angewendet wurde.

    TODO Stufe 2: Echter Roundtrip-Test mit gemocktem LLM-Server gegen reale
    Methodenpfade; misst Latenz-Reduktion ≥ 30 % vs. Baseline (Issue #217).
    """
    from app.services.oasis_profile_generator import OasisProfileGenerator

    method = OasisProfileGenerator._generate_profile_with_llm
    assert hasattr(method, '__wrapped__'), (
        "Decorator @measure_llm_latency wurde nicht auf "
        "OasisProfileGenerator._generate_profile_with_llm appliziert. "
        "functools.wraps setzt __wrapped__ — fehlt es, ist der Decorator nicht aktiv."
    )


# ---------------------------------------------------------------------------
# Test 4: extract_model-Extractor liefert model_name aus self
# ---------------------------------------------------------------------------


def test_measure_llm_latency_extract_model():
    """Decorator mit extract_model-Extractor loggt das Modell korrekt."""

    class FakeLLMService:
        model_name = 'ollama/qwen2.5:14b'

        @measure_llm_latency(
            operation='extract_model_test',
            extract_model=lambda self, *a, **kw: getattr(self, 'model_name', None),
        )
        def run(self) -> str:
            return 'done'

    svc = FakeLLMService()
    target, capture = _attach_capture()
    try:
        result = svc.run()
    finally:
        _detach_capture(target, capture)

    assert result == 'done'
    records = [r for r in capture.records if r.name == 'agora.llm_latency']
    assert len(records) == 1
    assert records[0].model == 'ollama/qwen2.5:14b'  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test 5: Extractor-Exception bricht nicht den eigentlichen Call ab
# ---------------------------------------------------------------------------


def test_measure_llm_latency_extractor_exception_is_swallowed():
    """Wenn extract_model/extract_prompt_chars wirft, darf der Decorator nicht crashen."""

    def bad_extractor(*args: Any, **kwargs: Any) -> None:
        raise ValueError('extractor kaputt')

    @measure_llm_latency(
        operation='extractor_fault_test',
        extract_model=bad_extractor,
        extract_prompt_chars=bad_extractor,
    )
    def stable_call() -> int:
        return 42

    target, capture = _attach_capture()
    try:
        result = stable_call()
    finally:
        _detach_capture(target, capture)

    assert result == 42
    records = [r for r in capture.records if r.name == 'agora.llm_latency']
    assert len(records) == 1
    rec = records[0]
    # Extractor-Fehler → konservativ None, kein eigener Crash
    assert rec.model is None  # type: ignore[attr-defined]
    assert rec.prompt_chars is None  # type: ignore[attr-defined]
    assert rec.success is True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Stufe 2a: env-Resolution-Test (deterministisch, kein LLM, Default-CI)
# ---------------------------------------------------------------------------


def test_generate_profiles_from_entities_resolves_parallel_count_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """parallel_count=None liest AGORA_PARALLEL_PERSONA_COUNT, default 10.

    Prüft, dass ThreadPoolExecutor mit dem aus env aufgelösten max_workers
    instanziiert wird. Kein echter LLM-Call — generate_profile_from_entity
    wird komplett gepatcht.
    """
    import concurrent.futures
    from unittest.mock import MagicMock, patch

    from app.services.entity_reader import EntityNode
    from app.services.oasis_profile_generator import OasisProfileGenerator

    monkeypatch.setenv('AGORA_PARALLEL_PERSONA_COUNT', '7')

    # OasisProfileGenerator benötigt LLM_API_KEY + OpenAI-Client im __init__.
    # Wir patchen OpenAI weg, damit kein echter HTTP-Call stattfindet.
    with patch('app.services.oasis_profile_generator.OpenAI'):
        generator = OasisProfileGenerator(
            api_key='dummy-key',
            base_url='http://localhost:11434/v1',
            model_name='qwen2.5:14b',
        )

    # generate_profile_from_entity ist der eigentliche LLM-Pfad — patchen.
    fake_profile = MagicMock()
    generator.generate_profile_from_entity = MagicMock(return_value=fake_profile)  # type: ignore[method-assign]

    entities = [
        EntityNode(f'perf-uuid-{i}', f'Testperson {i}', ['Entity', 'Person'], f'Summary {i}', {})
        for i in range(3)
    ]

    captured_max_workers: list[int] = []
    original_executor = concurrent.futures.ThreadPoolExecutor

    def capturing_executor(*args: Any, **kwargs: Any) -> concurrent.futures.ThreadPoolExecutor:
        if 'max_workers' in kwargs:
            captured_max_workers.append(kwargs['max_workers'])
        elif args:
            captured_max_workers.append(args[0])
        return original_executor(*args, **kwargs)

    with patch('concurrent.futures.ThreadPoolExecutor', side_effect=capturing_executor):
        generator.generate_profiles_from_entities(
            entities=entities,
            use_llm=True,
            parallel_count=None,
        )

    assert captured_max_workers, "ThreadPoolExecutor wurde nicht instanziiert"
    assert captured_max_workers[0] == 7, (
        f"Erwartet max_workers=7 (aus AGORA_PARALLEL_PERSONA_COUNT=7), "
        f"erhalten: {captured_max_workers[0]}"
    )


# ---------------------------------------------------------------------------
# Stufe 2a: Real-LLM-Bench (Marker perf + llm — NICHT im Default-CI)
# ---------------------------------------------------------------------------


def _build_synthetic_entities(count: int) -> list[Any]:
    """Deterministic synthetic EntityNodes for perf benchmarks (no Neo4j needed)."""
    from app.services.entity_reader import EntityNode

    return [
        EntityNode(
            uuid=f'perf-uuid-{idx}',
            name=f'Testperson Beispiel {idx}',
            labels=['Entity', 'Person'],
            summary=f'Synthetische Testperson #{idx} fuer Perf-Benchmark. '
                    f'Wohnhaft in Deutschland, berufstaetig im Dienstleistungssektor.',
            attributes={},
        )
        for idx in range(count)
    ]


@pytest.mark.perf
@pytest.mark.llm
@pytest.mark.parametrize('parallel_count', [5, 10, 15])
def test_persona_generation_perf_real_llm(parallel_count: int) -> None:
    """Real-LLM Latenz-Benchmark.

    Misst Wall-Clock + per-Persona-Latency fuer 10 Personas bei verschiedenen
    parallel_count-Werten. Der Orchestrator fuehrt diesen Test manuell fuer die
    Vorher/Nachher-Tabelle aus (Issue #217 Stufe 2a).

    Voraussetzung: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME im env gesetzt.
    Skip wenn nicht konfiguriert.

    Hinweis: OasisProfileGenerator.__init__ erstellt einen echten OpenAI-Client.
    Falls LLM_BASE_URL nicht gesetzt ist, wird der Test uebersprungen.
    Falls die Verbindung fehlschlaegt, schlaegt der Test fehl (kein silentes Skip).
    """
    import os

    if not os.environ.get('LLM_BASE_URL'):
        pytest.skip('LLM_BASE_URL nicht gesetzt — Real-LLM-Test uebersprungen.')

    from app.services.oasis_profile_generator import OasisProfileGenerator

    generator = OasisProfileGenerator()

    entities = _build_synthetic_entities(10)

    target, capture = _attach_capture()
    try:
        start = time.perf_counter()
        profiles = generator.generate_profiles_from_entities(
            entities=entities,
            use_llm=True,
            parallel_count=parallel_count,
        )
        wall_ms = (time.perf_counter() - start) * 1000.0
    finally:
        _detach_capture(target, capture)

    assert len(profiles) == 10, f'Persona-Generation lieferte {len(profiles)} statt 10 Profile'

    latencies = [
        r.latency_ms  # type: ignore[attr-defined]
        for r in capture.records
        if r.name == 'agora.llm_latency' and hasattr(r, 'latency_ms')
    ]
    assert len(latencies) >= 10, f'Nur {len(latencies)} Decorator-Records (erwartet >=10)'

    sorted_lats = sorted(latencies)
    p50 = sorted_lats[len(sorted_lats) // 2]
    p95_idx = min(int(len(sorted_lats) * 0.95), len(sorted_lats) - 1)
    p95 = sorted_lats[p95_idx]

    # Print-Output fuer Tabelle (test-output, kein Logger — Ausnahme per CLAUDE.md)
    print(
        f'\n[perf] parallel_count={parallel_count} wall_ms={wall_ms:.0f} '
        f'per_call_p50={p50:.0f} per_call_p95={p95:.0f} count={len(latencies)}'
    )


# ---------------------------------------------------------------------------
# Stufe 2b: AGORA_PERSONA_DETAIL_LEVEL-Resolution-Tests (deterministisch, kein LLM)
# ---------------------------------------------------------------------------


def test_resolve_persona_detail_level_default_is_standard(
    monkeypatch: pytest.MonkeyPatch, hermetic_settings
) -> None:
    """Default ohne env ist standard."""
    monkeypatch.delenv('AGORA_PERSONA_DETAIL_LEVEL', raising=False)
    detail = hermetic_settings._resolve_persona_detail_level()
    assert '700' in detail['word_count_de']
    assert detail['context_limit'] == 2000


@pytest.mark.parametrize('level,expected_word_marker,expected_ctx', [
    ('compact', '300', 1200),
    ('standard', '700', 2000),
    ('rich', '1500', 3000),
    ('COMPACT', '300', 1200),   # case-insensitive
    ('  rich  ', '1500', 3000),  # whitespace
])
def test_resolve_persona_detail_level_known_values(
    monkeypatch: pytest.MonkeyPatch,
    hermetic_settings,
    level: str,
    expected_word_marker: str,
    expected_ctx: int,
) -> None:
    monkeypatch.setenv('AGORA_PERSONA_DETAIL_LEVEL', level)
    detail = hermetic_settings._resolve_persona_detail_level()
    assert expected_word_marker in detail['word_count_de']
    assert detail['context_limit'] == expected_ctx


def test_resolve_persona_detail_level_unknown_falls_back_to_standard(
    monkeypatch: pytest.MonkeyPatch,
    hermetic_settings,
) -> None:
    """Unbekannter Wert faellt auf 'standard' zurueck."""
    monkeypatch.setenv('AGORA_PERSONA_DETAIL_LEVEL', 'epic')
    detail = hermetic_settings._resolve_persona_detail_level()
    assert '700' in detail['word_count_de']
    assert detail['context_limit'] == 2000
