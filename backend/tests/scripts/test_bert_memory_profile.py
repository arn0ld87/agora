"""Regressionstests für die BERT-Memory-Profile in ``_sim_common``.

Hintergrund: Auf 2.8-GiB-Container-Hosts kippt der OASIS-Subprozess mit
``Process exit code: -9`` (Linux-OOM-Killer, ``cgroup memory.events: oom_kill=1``),
sobald ``Twitter/twhin-bert-base`` (1.06 GB safetensors, fp32) im ersten
``update_rec_table()``-Tick lazy geladen wird — plus den 250-350 MB
``torch``/``transformers``/``sentence_transformers``-Import-Overhead aus
``oasis.social_platform.recsys`` und ``process_recsys_posts``.

Zwei ENV-getriebene Härten werden hier verriegelt:

1. ``AGORA_BERT_MEMORY_PROFILE=low`` (Default) — Monkey-Patch auf
   ``transformers.AutoModel.from_pretrained``: für ``Twitter/twhin-bert-base``
   werden ``low_cpu_mem_usage=True`` und ``torch_dtype=torch.float16``
   injiziert. Damit sinkt der dauerhafte RSS-Bedarf des Modells von ~1.2 GB
   auf ~600 MB und der transiente Load-Peak um weitere 300-500 MB. Für
   andere Modellnamen ist der Patch ein No-Op.

2. ``AGORA_DEBUG_MEMORY=1`` — startet einen Background-Thread, der
   ``process.memory_info().rss`` alle 0.5 s in eine NDJSON-Datei unter
   ``sim_dir/mem_profile.ndjson`` schreibt. Damit kann der nächste OOM-Run
   eine echte Boot-Kurve liefern, statt auf Vermutungen angewiesen zu sein.

Beide ENV-Schalter sind **opt-in per Default** (Profil = off, Debug = off) und
werden nur dann aktiv, wenn die jeweilige Variable gesetzt ist. Backwards-
compatibel für alle existierenden Runs.

Seam: die beiden Helper ``install_bert_memory_profile`` und
``install_memory_sampler`` in ``backend.scripts._sim_common``. Der Patch wird
in ``run_parallel_simulation.py`` und ``run_reddit_simulation.py`` direkt
nach ``install_max_tokens_warning_filter`` aktiviert, **bevor** ``oasis``-
Imports ``transformers.AutoModel`` lazy materialisieren. Da Python
Modul-Level-Caching nutzt, sieht der spätere ``from transformers import
AutoModel``-Aufruf in ``oasis.social_platform.process_recsys_posts`` die
gepatchte Methode auf dem selben Klassen-Objekt.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _sim_common import install_bert_memory_profile  # noqa: E402
from _sim_common import install_memory_sampler  # noqa: E402
from _sim_common import _read_rss_mb_linux  # noqa: E402


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stellt sicher, dass kein vorangegangener Test ENV-Leaks hinterlässt."""
    for var in ("AGORA_BERT_MEMORY_PROFILE", "AGORA_DEBUG_MEMORY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def fake_torch() -> mock.Mock:
    """Setzt ``sys.modules["torch"]`` auf ein Modul-Stub mit ``float16``.

    Hintergrund: Auf macOS-ARM mit Python 3.14 crasht ``import torch`` in
    ``libtorch_python.dylib`` zuverlässig (SIGSEGV), wenn der echte
    Torch-Stack im Test-venv initialisiert wird. Da unsere Funktion
    ``torch`` ausschließlich für ``torch.float16`` als ``torch_dtype``-
    Argument benötigt, ist ein Stub mit einem ``float16``-Sentinel
    ausreichend. Wird in jedem Test, der ``AGORA_BERT_MEMORY_PROFILE=low``
    aktiviert, als autouse-Fixture eingehängt.
    """
    stub = mock.Mock(name="torch_stub")
    stub.float16 = "fp16"
    return stub


def _patch_transformers_and_torch(
    fake_module: mock.Mock, fake_torch_module: mock.Mock | None
) -> mock._patch_dict:
    """Overrides für ``sys.modules`` als ``mock.patch.dict``-Manager.

    Im ``transformers``-Mock sitzt ``AutoModel.from_pretrained`` so, dass
    die Tests den echten Monkey-Patch isoliert prüfen können. ``torch``
    wird nur überschrieben, wenn der Test es explizit anfordert — sonst
    könnte ein anderer Test denselben Stub teilen.
    """
    overrides: dict[str, object] = {"transformers": fake_module}
    if fake_torch_module is not None:
        overrides["torch"] = fake_torch_module
    return mock.patch.dict(sys.modules, overrides)


class _DummyKwargs(dict):
    """Dict-Subklasse mit Attributzugriff für ``torch.dtype``-Mock-Kompatibilität."""

    def __getattr__(self, name: str):
        return self.get(name)


def test_default_profile_does_not_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ohne ``AGORA_BERT_MEMORY_PROFILE`` bleibt ``from_pretrained`` unangetastet."""
    monkeypatch.delenv("AGORA_BERT_MEMORY_PROFILE", raising=False)

    sentinel = mock.Mock(name="original_from_pretrained")
    fake_module = mock.Mock()
    fake_module.AutoModel.from_pretrained = sentinel
    with mock.patch.dict(sys.modules, {"transformers": fake_module}):
        install_bert_memory_profile()

    # ``from_pretrained`` darf weder gelesen noch ersetzt worden sein.
    assert fake_module.AutoModel.from_pretrained is sentinel


def test_low_profile_patches_twhin_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``AGORA_BERT_MEMORY_PROFILE=low`` patcht nur ``Twitter/twhin-bert-base``."""
    monkeypatch.setenv("AGORA_BERT_MEMORY_PROFILE", "low")

    captured_calls: list[dict] = []

    def _fake_from_pretrained(*args, **kwargs):
        captured_calls.append({"args": args, "kwargs": kwargs})
        return mock.Mock(name="model")

    fake_module = mock.Mock()
    fake_module.AutoModel.from_pretrained = _fake_from_pretrained
    with mock.patch.dict(sys.modules, {"transformers": fake_module}):
        install_bert_memory_profile()

    patched = fake_module.AutoModel.from_pretrained
    assert patched is not _fake_from_pretrained

    # twhin-bert-base: low_cpu_mem_usage + float16 müssen gesetzt sein.
    patched("Twitter/twhin-bert-base")
    assert len(captured_calls) == 1
    kwargs = captured_calls[0]["kwargs"]
    assert kwargs.get("low_cpu_mem_usage") is True
    assert "torch_dtype" in kwargs  # Wert hängt von torch ab, muss aber gesetzt sein

    # anderes Modell: low_cpu_mem_usage darf NICHT injiziert werden.
    patched("sentence-transformers/all-MiniLM-L6-v2")
    assert len(captured_calls) == 2
    assert "low_cpu_mem_usage" not in captured_calls[1]["kwargs"]


def test_off_profile_does_not_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    """``AGORA_BERT_MEMORY_PROFILE=off`` schaltet den Patch explizit aus."""
    monkeypatch.setenv("AGORA_BERT_MEMORY_PROFILE", "off")

    sentinel = mock.Mock(name="original_from_pretrained")
    fake_module = mock.Mock()
    fake_module.AutoModel.from_pretrained = sentinel
    with mock.patch.dict(sys.modules, {"transformers": fake_module}):
        install_bert_memory_profile()

    assert fake_module.AutoModel.from_pretrained is sentinel


def test_low_profile_preserves_user_overrides(
    monkeypatch: pytest.MonkeyPatch, fake_torch: mock.Mock
) -> None:
    """Wenn der Aufrufer bereits ``torch_dtype`` setzt, wird es nicht überschrieben."""
    monkeypatch.setenv("AGORA_BERT_MEMORY_PROFILE", "low")

    captured: list[dict] = []

    def _fake(*_args: object, **_kwargs: object) -> mock.Mock:
        captured.append(_kwargs)
        return mock.Mock()

    fake_module = mock.Mock()
    fake_module.AutoModel.from_pretrained = _fake
    with _patch_transformers_and_torch(fake_module, fake_torch):
        install_bert_memory_profile()
        patched = fake_module.AutoModel.from_pretrained

    # Aufrufer hat bereits torch_dtype=bfloat16 gesetzt — bleibt.
    sentinel_dtype = object()
    patched("Twitter/twhin-bert-base", torch_dtype=sentinel_dtype)
    assert captured[0]["torch_dtype"] is sentinel_dtype
    # low_cpu_mem_usage wird trotzdem ergänzt (User hat es nicht gesetzt).
    assert captured[0]["low_cpu_mem_usage"] is True


def test_memory_sampler_writes_ndjson_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``AGORA_DEBUG_MEMORY=1`` schreibt mindestens einen RSS-Snapshot in die NDJSON-Datei."""
    monkeypatch.setenv("AGORA_DEBUG_MEMORY", "1")
    sink = tmp_path / "mem.ndjson"

    # Deterministischer RSS-Reader: zyklische Sequenz, damit der Thread
    # auch nach Test-Ende nicht in StopIteration läuft und der Daemon-
    # Cleanup keine unhandled exception wirft.
    import itertools
    rss_values = itertools.cycle([100.0, 100.5, 101.0, 101.5])

    def _fake_reader() -> float:
        return next(rss_values)

    stop = install_memory_sampler(sink=sink, interval_s=0.05, rss_reader=_fake_reader)
    try:
        time.sleep(0.2)  # mindestens 2–3 Samples
    finally:
        stop()

    lines = sink.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2, "Sampler muss mindestens 2 Snapshots schreiben"
    sample = json.loads(lines[0])
    assert sample["label"] == "tick"
    assert isinstance(sample["rss_mb"], float)
    assert sample["rss_mb"] > 0
    assert "time_s" in sample
    # ``time_s`` ist non-negativ (relativ zu Thread-Start); auf macOS kann
    # ``time.monotonic`` fuer sehr kurze Intervalle gleiche Werte liefern,
    # deshalb nur "nicht negativ" pruefen statt strikt monotonic.
    times = [json.loads(line)["time_s"] for line in lines]
    assert all(t >= 0 for t in times)


def test_memory_sampler_is_noop_without_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ohne ``AGORA_DEBUG_MEMORY`` bleibt der Sampler inaktiv und erzeugt keine Datei."""
    monkeypatch.delenv("AGORA_DEBUG_MEMORY", raising=False)
    sink = tmp_path / "mem.ndjson"

    stop = install_memory_sampler(sink=sink, interval_s=0.05)
    try:
        time.sleep(0.15)
    finally:
        stop()

    assert not sink.exists() or sink.read_text(encoding="utf-8") == ""


def test_memory_sampler_stop_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mehrfaches ``stop()`` darf nicht crashen (Cleanup-Pfad ist optional)."""
    monkeypatch.setenv("AGORA_DEBUG_MEMORY", "1")
    sink = tmp_path / "mem.ndjson"

    stop = install_memory_sampler(sink=sink, interval_s=0.05)
    stop()
    stop()  # idempotent


def test_low_profile_does_not_break_if_transformers_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wenn ``transformers`` nicht installiert ist, schlägt der Patch still fehl."""
    monkeypatch.setenv("AGORA_BERT_MEMORY_PROFILE", "low")

    # Simuliere ``ImportError``: transformers aus sys.modules entfernen
    # und ``import transformers`` in einen ImportError laufen lassen.
    with mock.patch.dict(sys.modules, {"transformers": None}):
        # Sollte keine Exception werfen.
        install_bert_memory_profile()