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
from unittest import mock

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _sim_common import install_bert_memory_profile  # noqa: E402
from _sim_common import install_memory_sampler  # noqa: E402


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stellt sicher, dass kein vorangegangener Test ENV-Leaks hinterlässt."""
    for var in ("AGORA_BERT_MEMORY_PROFILE", "AGORA_DEBUG_MEMORY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def fake_torch() -> mock.Mock:
    """
    Erstellt einen Torch-Stub mit einem `float16`-Sentinel für Tests des Low-Memory-Profils.
    
    Returns:
        mock.Mock: Ein Stub mit dem Attribut `float16`.
    """
    stub = mock.Mock(name="torch_stub")
    stub.float16 = "fp16"
    return stub


def _patch_transformers_and_torch(
    fake_module: mock.Mock, fake_torch_module: mock.Mock | None
) -> mock._patch_dict:
    """
    Erzeugt einen Patch-Manager für die vorübergehende Ersetzung von `transformers` und optional `torch` in `sys.modules`.
    
    Returns:
        mock._patch_dict: Patch-Manager für das `sys.modules`-Overlay.
    """
    overrides: dict[str, object] = {"transformers": fake_module}
    if fake_torch_module is not None:
        overrides["torch"] = fake_torch_module
    return mock.patch.dict(sys.modules, overrides)


class _DummyKwargs(dict):
    """Dict-Subklasse mit Attributzugriff für ``torch.dtype``-Mock-Kompatibilität."""

    def __getattr__(self, name: str):
        """
        Liefert den Wert des angegebenen Attributnamens aus dem Wörterbuch.
        
        Parameter:
            name (str): Der abzurufende Attributname.

        Returns:
            Der zugehörige Wert oder `None`, wenn der Name nicht vorhanden ist.
        """
        return self.get(name)


def test_default_profile_patches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default-Profil IST ``low`` (per ``_BERT_PROFILE_DEFAULT``) — patching
    MUSS stattfinden. Verifiziert, dass die Idempotenz-Pruefung im Helper
    nicht fälschlich frueh zurueckkehrt.

    Wichtig: ``original`` ist eine echte Funktion (kein ``mock.Mock``).
    ``install_bert_memory_profile`` prueft per
    ``getattr(original, "_agora_bert_memory_profile_applied", False)``
    auf Idempotenz; ein ``Mock``-Sentinel wuerde das Attribut truthy
    auto-magieren und der Patch wuerde stillschweigend ueberspringen
    (CodeRabbit-Finding #859).
    """
    monkeypatch.delenv("AGORA_BERT_MEMORY_PROFILE", raising=False)

    def sentinel(*_args: object, **_kwargs: object) -> mock.Mock:
        return mock.Mock(name="model")

    fake_module = mock.Mock()
    fake_module.AutoModel.from_pretrained = sentinel
    with mock.patch.dict(sys.modules, {"transformers": fake_module}):
        install_bert_memory_profile()

    # Default = "low" → Patching MUSS stattgefunden haben.
    assert fake_module.AutoModel.from_pretrained is not sentinel
    # Das gesetzte Flag haengt am neuen (gepatchten) Callable, nicht am
    # Original — verhindert Doppel-Wrapping bei wiederholten Aufrufen.
    assert getattr(
        fake_module.AutoModel.from_pretrained,
        "_agora_bert_memory_profile_applied",
        False,
    ) is True


def test_low_profile_patches_twhin_only(
    monkeypatch: pytest.MonkeyPatch, fake_torch: mock.Mock
) -> None:
    """``AGORA_BERT_MEMORY_PROFILE=low`` patcht nur ``Twitter/twhin-bert-base``.

    Nutzt ``fake_torch`` (Fixture) statt des echten torch-Moduls — sonst
    haengt der Test an der Test-Umgebung (passiert nur, weil im Dev-venv
    ``torch`` installiert ist). Fix fuer CodeRabbit-Finding #859: ohne
    Isolation schleppte der Test reale torch-Imports in andere Tests.
    """
    monkeypatch.setenv("AGORA_BERT_MEMORY_PROFILE", "low")

    captured_calls: list[dict] = []

    def _fake_from_pretrained(*args, **kwargs):
        captured_calls.append({"args": args, "kwargs": kwargs})
        return mock.Mock(name="model")

    fake_module = mock.Mock()
    fake_module.AutoModel.from_pretrained = _fake_from_pretrained
    with _patch_transformers_and_torch(fake_module, fake_torch):
        install_bert_memory_profile()

    patched = fake_module.AutoModel.from_pretrained
    assert patched is not _fake_from_pretrained

    # twhin-bert-base: low_cpu_mem_usage + float16 müssen gesetzt sein.
    patched("Twitter/twhin-bert-base")
    assert len(captured_calls) == 1
    kwargs = captured_calls[0]["kwargs"]
    assert kwargs.get("low_cpu_mem_usage") is True
    assert "torch_dtype" in kwargs  # fake_torch.float16 = "fp16" sentinel

    # anderes Modell: low_cpu_mem_usage darf NICHT injiziert werden.
    patched("sentence-transformers/all-MiniLM-L6-v2")
    assert len(captured_calls) == 2
    assert "low_cpu_mem_usage" not in captured_calls[1]["kwargs"]


def test_off_profile_does_not_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    """``AGORA_BERT_MEMORY_PROFILE=off`` schaltet den Patch explizit aus."""
    monkeypatch.setenv("AGORA_BERT_MEMORY_PROFILE", "off")

    def sentinel(*_args: object, **_kwargs: object) -> mock.Mock:
        return mock.Mock(name="model")

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
        """
        Erfasst die Schlüsselwortargumente eines Aufrufs und liefert einen Mock zurück.
        
        Returns:
            mock.Mock: Ein neuer Mock als Rückgabewert des Aufrufs.
        """
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
        """Liest den nächsten RSS-Speicherwert aus der Testsequenz.
        
        Returns:
            float: Der nächste konfigurierte RSS-Wert in Megabyte.
        """
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


# ---------------------------------------------------------------------------
# CodeRabbit Review #859 — Regressionstests fuer Findings 1, 3-5, 7
# ---------------------------------------------------------------------------


def test_memory_sampler_preserves_user_reader_when_returning_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 1: macOS-Fallback darf einen vom Caller uebergebenen
    ``rss_reader`` NICHT durch ein No-Op ersetzen, nur weil der Reader
    (transient) ``None`` liefert.

    Vor dem Fix: ``rss_reader() is None`` + ``/proc/self/status`` fehlt →
    die Funktion definierte ``rss_reader`` lokal neu als
    ``return None`` und schluckte damit den Caller-Reader. Tests, die
    einen Reader liefern, der periodisch ``None`` zurueckgibt, schreiben
    danach unsichtbare Samples.
    """
    monkeypatch.setenv("AGORA_DEBUG_MEMORY", "1")
    sink = tmp_path / "mem.ndjson"

    call_count = {"n": 0}

    def user_reader() -> float | None:
        call_count["n"] += 1
        return None  # simuliert macOS / kein RSS zugaenglich

    # macOS simulieren: ``/proc/self/status`` darf nicht "existieren".
    real_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        if str(self).startswith("/proc/") and "status" in str(self):
            return False
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    stop = install_memory_sampler(
        sink=sink, interval_s=0.05, rss_reader=user_reader
    )
    try:
        time.sleep(0.2)  # mindestens 2–3 Sample-Ticks
    finally:
        stop()

    # Initialer Probe-Aufruf (1) + Thread-Loop-Calls (>=2) — beweist, dass
    # der Caller-Reader NICHT durch den macOS-Fallback ersetzt wurde.
    assert call_count["n"] >= 2, (
        f"User-rss_reader wurde nur {call_count['n']}x aufgerufen — "
        "macOS-Fallback hat den Caller-Reader ueberschrieben."
    )


def test_make_default_memory_sink_includes_pid(tmp_path: Path) -> None:
    """Findings 3-5: Default-Sink-Pfad muss die PID enthalten, damit
    parallele Sim-Runs nicht denselben NDJSON-Sink ueberschreiben.

    Vor dem Fix: alle 3 ``run_*_simulation.py``-Caller schrieben auf
    ``<project_root>/.runtime/mem_profile.ndjson`` ohne PID —
    POSIX-Append-Concurrency fuehrte zu zerschossenem NDJSON.
    """
    from _sim_common import make_default_memory_sink

    sink = make_default_memory_sink(tmp_path)

    assert sink.parent == tmp_path / ".runtime", (
        f"Default-Sink muss unter <project_root>/.runtime liegen, "
        f"bekam parent: {sink.parent}"
    )
    assert sink.name.startswith("mem_profile."), (
        f"Erwarteter Prefix 'mem_profile.', bekam: {sink.name}"
    )
    assert sink.name.endswith(".ndjson"), (
        f"Erwartetes Suffix '.ndjson', bekam: {sink.name}"
    )
    assert f".{os.getpid()}." in sink.name, (
        f"Sink-Dateiname muss die PID enthalten (für Concurrent-Runs), "
        f"bekam: {sink.name}"
    )


def test_low_profile_no_torch_does_not_inject_torch_dtype(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 7: Auch ohne ``torch`` (oder mit unavailable torch) darf
    der Patch ``low_cpu_mem_usage=True`` setzen — ``torch_dtype`` wird
    dann gar nicht injiziert, weil die Quelle fehlt.

    Sperrt das Verhalten fest, sodass der bestehende Test
    ``test_low_profile_patches_twhin_only`` (der das aktuell nur per
    Glueck durchlaeuft, weil das Test-venv echtes torch hat) auf eine
    deterministische fake_torch-Fixture umgestellt werden kann.
    """
    monkeypatch.setenv("AGORA_BERT_MEMORY_PROFILE", "low")

    # Torch komplett aus sys.modules entfernen → ImportError.
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.setitem(sys.modules, "torch", None)

    captured_calls: list[dict] = []

    def _fake_from_pretrained(*args: object, **kwargs: object) -> mock.Mock:
        captured_calls.append({"args": args, "kwargs": kwargs})
        return mock.Mock(name="model")

    fake_module = mock.Mock()
    fake_module.AutoModel.from_pretrained = _fake_from_pretrained
    with mock.patch.dict(sys.modules, {"transformers": fake_module}):
        install_bert_memory_profile()

    patched = fake_module.AutoModel.from_pretrained
    assert patched is not _fake_from_pretrained

    patched("Twitter/twhin-bert-base")
    assert len(captured_calls) == 1
    kwargs = captured_calls[0]["kwargs"]
    assert kwargs.get("low_cpu_mem_usage") is True
    # Kein torch → kein torch_dtype-Key (sonst wuerde der echte
    # AutoModel.from_pretrained mit einem ungueltigen dtype fehlschlagen).
    assert "torch_dtype" not in kwargs


# ---------------------------------------------------------------------------
# fix/oasis-fp16-round0-hang: host-adaptives "auto"-Profil
# ---------------------------------------------------------------------------
# Root cause: ``install_bert_memory_profile`` zwang TWHIN-BERT immer auf fp16.
# fp16 hat auf CPU keine nativen Kernel -> langsame single-threaded Emulation
# -> ein ``update_rec_table()``-Forward blockierte den asyncio-Event-Loop der
# OASIS-Plattform ~12 min (Round 0-Hang). fp32 laeuft 16-threaded in ~14 s.
# Fix: neuer Default ``"auto"`` — fp16 nur noch bei knappem Container-RAM
# (< _BERT_FP32_MIN_AVAIL_MB), sonst fp32. ``low``/``off`` bleiben unveraendert.
# ---------------------------------------------------------------------------

import _sim_common as _sim_common_module  # noqa: E402


def test_auto_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default-Profil ist ``"auto"`` (nicht mehr ``"low"``). Sichert, dass
    der Fix-Default nicht versehentlich zurueckgesetzt wird."""
    monkeypatch.delenv("AGORA_BERT_MEMORY_PROFILE", raising=False)
    # _read_available_mb_linux deterministisch stubben, damit der Test nicht
    # vom echten Host-RAM abhaengt.
    monkeypatch.setattr(_sim_common_module, "_read_available_mb_linux", lambda: 8192.0)

    def sentinel(*_args: object, **_kwargs: object) -> mock.Mock:
        return mock.Mock(name="model")

    fake_module = mock.Mock()
    fake_module.AutoModel.from_pretrained = sentinel
    with mock.patch.dict(sys.modules, {"transformers": fake_module}):
        result = install_bert_memory_profile()
    assert result == "auto"
    # Patch wird dennoch installiert (low_cpu_mem_usage immer).
    assert fake_module.AutoModel.from_pretrained is not sentinel


def test_auto_profile_fp32_when_ram_plenty(
    monkeypatch: pytest.MonkeyPatch, fake_torch: mock.Mock
) -> None:
    """``auto`` + reichlich Container-RAM (>= Schwellenwert) -> fp32:
    ``low_cpu_mem_usage=True``, aber KEIN ``torch_dtype`` (kein fp16)."""
    monkeypatch.setenv("AGORA_BERT_MEMORY_PROFILE", "auto")
    monkeypatch.setattr(
        _sim_common_module, "_read_available_mb_linux", lambda: 8192.0
    )

    captured_calls: list[dict] = []

    def _fake_from_pretrained(*args, **kwargs):
        captured_calls.append({"args": args, "kwargs": kwargs})
        return mock.Mock(name="model")

    fake_module = mock.Mock()
    fake_module.AutoModel.from_pretrained = _fake_from_pretrained
    with _patch_transformers_and_torch(fake_module, fake_torch):
        install_bert_memory_profile()
        patched = fake_module.AutoModel.from_pretrained

    patched("Twitter/twhin-bert-base")
    assert len(captured_calls) == 1
    kwargs = captured_calls[0]["kwargs"]
    assert kwargs.get("low_cpu_mem_usage") is True
    # Genug RAM -> fp32 -> torch_dtype darf NICHT injiziert werden.
    assert "torch_dtype" not in kwargs


def test_auto_profile_fp16_when_ram_low(
    monkeypatch: pytest.MonkeyPatch, fake_torch: mock.Mock
) -> None:
    """``auto`` + knapper Container-RAM (< Schwellenwert) -> fp16:
    ``low_cpu_mem_usage=True`` UND ``torch_dtype=fp16`` (OOM-Schutz aktiv)."""
    monkeypatch.setenv("AGORA_BERT_MEMORY_PROFILE", "auto")
    monkeypatch.setattr(
        _sim_common_module, "_read_available_mb_linux", lambda: 1024.0
    )

    captured_calls: list[dict] = []

    def _fake_from_pretrained(*args, **kwargs):
        captured_calls.append({"args": args, "kwargs": kwargs})
        return mock.Mock(name="model")

    fake_module = mock.Mock()
    fake_module.AutoModel.from_pretrained = _fake_from_pretrained
    with _patch_transformers_and_torch(fake_module, fake_torch):
        install_bert_memory_profile()
        patched = fake_module.AutoModel.from_pretrained

    patched("Twitter/twhin-bert-base")
    assert len(captured_calls) == 1
    kwargs = captured_calls[0]["kwargs"]
    assert kwargs.get("low_cpu_mem_usage") is True
    assert kwargs.get("torch_dtype") == "fp16"  # fake_torch.float16 sentinel


def test_auto_profile_fp16_when_ram_unknown(
    monkeypatch: pytest.MonkeyPatch, fake_torch: mock.Mock
) -> None:
    """``auto`` + RAM nicht ermittelbar (``None``, z.B. macOS) ->
    konservativ fp16 (OOM-Schutz bleibt als Safe-Default erhalten)."""
    monkeypatch.setenv("AGORA_BERT_MEMORY_PROFILE", "auto")
    monkeypatch.setattr(
        _sim_common_module, "_read_available_mb_linux", lambda: None
    )

    captured_calls: list[dict] = []

    def _fake_from_pretrained(*args, **kwargs):
        captured_calls.append({"args": args, "kwargs": kwargs})
        return mock.Mock(name="model")

    fake_module = mock.Mock()
    fake_module.AutoModel.from_pretrained = _fake_from_pretrained
    with _patch_transformers_and_torch(fake_module, fake_torch):
        install_bert_memory_profile()
        patched = fake_module.AutoModel.from_pretrained

    patched("Twitter/twhin-bert-base")
    kwargs = captured_calls[0]["kwargs"]
    assert kwargs.get("low_cpu_mem_usage") is True
    assert kwargs.get("torch_dtype") == "fp16"


def test_auto_profile_boundary_exact_threshold(
    monkeypatch: pytest.MonkeyPatch, fake_torch: mock.Mock
) -> None:
    """Genau am Schwellenwert (``_BERT_FP32_MIN_AVAIL_MB``) -> fp32
    (``>=``-Bedingung). Verriegelt die Grenze gegen Off-by-One-Drift."""
    monkeypatch.setenv("AGORA_BERT_MEMORY_PROFILE", "auto")
    threshold = _sim_common_module._BERT_FP32_MIN_AVAIL_MB
    monkeypatch.setattr(
        _sim_common_module, "_read_available_mb_linux", lambda: float(threshold)
    )

    captured_calls: list[dict] = []

    def _fake_from_pretrained(*args, **kwargs):
        captured_calls.append({"args": args, "kwargs": kwargs})
        return mock.Mock(name="model")

    fake_module = mock.Mock()
    fake_module.AutoModel.from_pretrained = _fake_from_pretrained
    with _patch_transformers_and_torch(fake_module, fake_torch):
        install_bert_memory_profile()
        patched = fake_module.AutoModel.from_pretrained

    patched("Twitter/twhin-bert-base")
    kwargs = captured_calls[0]["kwargs"]
    assert "torch_dtype" not in kwargs  # >= threshold -> fp32