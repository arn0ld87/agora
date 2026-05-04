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
