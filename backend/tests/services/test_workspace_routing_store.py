"""Tests für Workspace-Routing-Store."""
from __future__ import annotations

import json
import logging
import stat
import subprocess
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.contracts.llm_routing_contract import StageId, StageLLMRoute
from app.contracts.workspace_routing_contract import WorkspaceLlmRoutingDefaults
from app.services.workspace_routing_store import (
    WorkspaceRoutingStore,
    get_workspace_routing_store,
    reset_singleton_for_tests,
)


@pytest.fixture
def store(tmp_path: Path):
    s = WorkspaceRoutingStore(data_dir=tmp_path)
    yield s


def test_load_empty_returns_defaults(store):
    defaults = store.load()
    assert isinstance(defaults, WorkspaceLlmRoutingDefaults)
    assert defaults.stage_overrides == {}


def test_save_and_load_roundtrip(store):
    payload = WorkspaceLlmRoutingDefaults(
        global_default=StageLLMRoute(provider_id="openai", model="gpt-4o-mini"),
        stage_overrides={
            "report_generation": StageLLMRoute(provider_id="openai", model="gpt-4o"),
        },
    )
    store.save(payload)
    loaded = store.load()
    assert loaded.global_default.model == "gpt-4o-mini"
    assert loaded.stage_overrides["report_generation"].model == "gpt-4o"
    assert loaded.updated_at is not None


def test_set_stage_override(store):
    route = StageLLMRoute(provider_id="google", model="gemini-1.5-pro")
    updated = store.set_stage_override("persona_generation", route)
    assert updated.stage_overrides["persona_generation"].model == "gemini-1.5-pro"


def test_clear_stage_override(store):
    route = StageLLMRoute(provider_id="google", model="gemini-1.5-pro")
    store.set_stage_override("persona_generation", route)
    cleared = store.set_stage_override("persona_generation", None)
    assert "persona_generation" not in cleared.stage_overrides


def test_set_global_default(store):
    route = StageLLMRoute(provider_id="openai", model="gpt-4o-mini")
    updated = store.set_global_default(route)
    assert updated.global_default.model == "gpt-4o-mini"


def test_singleton_uses_env_data_dir(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    reset_singleton_for_tests()
    s = get_workspace_routing_store()
    s.set_global_default(StageLLMRoute(provider_id="openai", model="gpt-4o"))
    assert (tmp_path / "workspace_llm_routing.json").exists()
    reset_singleton_for_tests()


# --- Issue #450 P1.2 — Multi-Worker-Dateikonsistenz -------------------------


_CHILD_WORKER_TEMPLATE = textwrap.dedent(
    """
    import sys
    import time
    from pathlib import Path

    sys.path.insert(0, {backend_path!r})
    from app.contracts.llm_routing_contract import StageLLMRoute
    from app.services.workspace_routing_store import WorkspaceRoutingStore

    ready_path = Path({ready_path!r})
    start_path = Path({start_path!r})
    ready_path.touch()
    while not start_path.exists():
        time.sleep(0.01)

    store = WorkspaceRoutingStore(data_dir=Path({data_dir!r}))
    store.set_stage_override(
        {stage_id!r},
        StageLLMRoute(provider_id="openai", model={model!r}),
    )
    """
)


def _spawn_child_set_override(
    backend_path: Path,
    data_dir: Path,
    ready_path: Path,
    start_path: Path,
    stage_id: StageId,
    model: str,
) -> subprocess.Popen[bytes]:
    """Startet einen echten Interpreter mit expliziter Readiness-Barriere."""
    code = _CHILD_WORKER_TEMPLATE.format(
        backend_path=str(backend_path),
        data_dir=str(data_dir),
        ready_path=str(ready_path),
        start_path=str(start_path),
        stage_id=stage_id,
        model=model,
    )
    return subprocess.Popen([sys.executable, "-c", code])


def test_parallel_processes_no_lost_update(tmp_path: Path):
    """Issue #450 P1.2 — parallele Prozesse dürfen sich Stage-Overrides nicht überschreiben.

    Vorher (nur ``threading.Lock`` + ``os.replace``): jeder Worker las die
    leeren Defaults, schrieb seinen eigenen Override und überschrieb damit
    die Updates der anderen Worker. Mit ``fcntl.flock`` über die gesamte
    read-modify-write-Sequenz bleibt jeder Override erhalten.

    Jeder Worker meldet nach seinen Cold Imports explizit Readiness. Erst wenn
    alle sieben bereit sind, gibt der Parent die gleichzeitigen Writes frei.
    Damit misst die gemeinsame 30-Sekunden-Deadline echte Child-/Lock-Hänger
    statt plattformabhängiger Importzeit; die Prozess- und ``flock``-Grenze
    bleibt vollständig erhalten.
    """
    stages_and_models: list[tuple[StageId, str]] = [
        ("document_ingest", "gpt-4o-mini"),
        ("ontology_generation", "gpt-4o"),
        ("graph_build", "gpt-4o"),
        ("persona_generation", "gemini-1.5-pro"),
        ("simulation_rounds", "claude-3-5-sonnet"),
        ("report_generation", "gpt-4o"),
        ("evaluation", "gpt-4o-mini"),
    ]
    backend_path = Path(__file__).resolve().parents[2]
    start_path = tmp_path / ".routing-workers-start"
    workers: list[tuple[StageId, Path, subprocess.Popen[bytes]]] = []
    try:
        for index, (stage, model) in enumerate(stages_and_models):
            ready_path = tmp_path / f".routing-worker-{index}.ready"
            process = _spawn_child_set_override(
                backend_path,
                tmp_path,
                ready_path,
                start_path,
                stage,
                model,
            )
            workers.append((stage, ready_path, process))

        # Import-Readiness ist eine Umgebungsbedingung, nicht die getestete
        # Lock-Invariante. 120 s sind ein Safety-Bound für langsame lokale
        # Cold-Starts; gewartet wird auf Marker, nicht auf eine feste Pause.
        import_deadline = time.monotonic() + 120
        while not all(ready_path.exists() for _, ready_path, _ in workers):
            exited = [
                (stage, process.returncode)
                for stage, _, process in workers
                if process.poll() is not None
            ]
            assert not exited, f"child exited before readiness: {exited}"
            missing = [
                stage for stage, ready_path, _ in workers if not ready_path.exists()
            ]
            remaining = import_deadline - time.monotonic()
            assert remaining > 0, (
                f"child import readiness timed out; missing stages: {missing}"
            )
            time.sleep(min(0.05, remaining))

        start_path.touch()
        write_deadline = time.monotonic() + 30
        pending = {process: stage for stage, _, process in workers}
        while pending:
            for process, stage in list(pending.items()):
                returncode = process.poll()
                if returncode is None:
                    continue
                assert returncode == 0, (
                    f"child process failed: stage={stage}, returncode={returncode}"
                )
                del pending[process]
            if not pending:
                break
            remaining = write_deadline - time.monotonic()
            assert remaining > 0, (
                "child writes timed out after readiness; pending stages: "
                f"{list(pending.values())}"
            )
            time.sleep(min(0.01, remaining))
    finally:
        for _, _, process in workers:
            if process.poll() is None:
                process.kill()
        cleanup_deadline = time.monotonic() + 5
        survivors = []
        for stage, _, process in workers:
            try:
                process.wait(timeout=max(0, cleanup_deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                survivors.append(stage)
        assert not survivors, f"child cleanup timed out: {survivors}"

    # Verifikation: jeder Stage-Override muss persistiert sein
    store = WorkspaceRoutingStore(data_dir=tmp_path)
    final = store.load()
    assert set(final.stage_overrides.keys()) == {stage for stage, _ in stages_and_models}
    for stage, expected_model in stages_and_models:
        assert final.stage_overrides[stage].model == expected_model, (
            f"Lost update for stage {stage!r}: erwarteter Model {expected_model!r}, "
            f"gefunden {final.stage_overrides[stage].model!r}"
        )


def test_concurrent_threads_no_lost_update(tmp_path: Path):
    """Innerhalb eines Prozesses schützt der ``threading.Lock``.

    Dieser Test sichert, dass der File-Lock den vorhandenen ``threading.Lock``
    nicht versehentlich nutzlos macht (z.B. durch falsche Lock-Reihenfolge).
    """
    store = WorkspaceRoutingStore(data_dir=tmp_path)
    stages = [
        "document_ingest",
        "ontology_generation",
        "graph_build",
        "persona_generation",
        "simulation_rounds",
        "report_generation",
        "evaluation",
    ]

    def _write(stage: str) -> None:
        store.set_stage_override(
            stage,  # type: ignore[arg-type]
            StageLLMRoute(provider_id="openai", model=f"model-{stage}"),
        )

    with ThreadPoolExecutor(max_workers=len(stages)) as executor:
        list(executor.map(_write, stages))

    final = store.load()
    assert set(final.stage_overrides.keys()) == set(stages)


def test_save_creates_lock_sidecar(tmp_path: Path):
    """Lock-Sidecar darf neben dem Store-File entstehen."""
    store = WorkspaceRoutingStore(data_dir=tmp_path)
    store.set_global_default(StageLLMRoute(provider_id="openai", model="gpt-4o"))
    lock_path = tmp_path / "workspace_llm_routing.lock"
    assert lock_path.exists()


def test_save_sets_restrictive_permissions(tmp_path: Path):
    """Issue #450 P1.3 — JSON-File darf nicht world-readable sein."""
    store = WorkspaceRoutingStore(data_dir=tmp_path)
    store.set_global_default(StageLLMRoute(provider_id="openai", model="gpt-4o"))
    store_path = tmp_path / "workspace_llm_routing.json"
    mode = stat.S_IMODE(store_path.stat().st_mode)
    # 0600 für Hauptdatei; Lockdatei muss nicht gehärtet sein
    assert mode == 0o600, f"erwartete 0600, gefunden 0o{mode:o}"


def test_corrupt_json_is_logged_and_replaced_safely(tmp_path: Path):
    """Korrupter Store wird laut geloggt und beim nächsten save überschrieben.

    ``caplog`` kann hier nicht direkt verwendet werden, weil der Modul-Logger
    via ``app.utils.logger.setup_logger`` mit ``propagate=False`` initialisiert
    wird. Wir hängen stattdessen einen eigenen ``MemoryHandler`` an den
    bekannten Logger und prüfen die Records direkt.
    """
    store_path = tmp_path / "workspace_llm_routing.json"
    store_path.write_text("{not: valid json", encoding="utf-8")

    captured: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    target_logger = logging.getLogger("agora.services.workspace_routing_store")
    handler = _ListHandler(level=logging.ERROR)
    target_logger.addHandler(handler)
    try:
        store = WorkspaceRoutingStore(data_dir=tmp_path)
        loaded = store.load()
        assert loaded.stage_overrides == {}
        assert any("korrupt" in r.getMessage().lower() for r in captured), [
            r.getMessage() for r in captured
        ]
        # Nächster save überschreibt die korrupte Datei sauber
        store.set_global_default(StageLLMRoute(provider_id="openai", model="gpt-4o"))
        fresh = json.loads(store_path.read_text(encoding="utf-8"))
        assert fresh["global_default"]["model"] == "gpt-4o"
    finally:
        target_logger.removeHandler(handler)
