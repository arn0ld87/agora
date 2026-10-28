"""Memory profiler, TWHIN-BERT memory profile & cache, and OASIS compatibility patches."""

import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import sys
import threading
import time
from typing import Any, Callable

logger = logging.getLogger("agora._sim_common")

_TWHIN_BERT_MODEL_NAMES: frozenset[str] = frozenset(
    {
        "Twitter/twhin-bert-base",
    }
)

_BERT_PROFILE_DEFAULT = "auto"
_BERT_FP32_MIN_AVAIL_MB = 4096


class TwhinCacheError(RuntimeError):
    """TWHIN-BERT-Cache weder lokal vollstaendig noch aus dem Hub ladbar."""


_TWHIN_BERT_REPO_ID = "Twitter/twhin-bert-base"


def ensure_twhin_cache(repo_id: str = _TWHIN_BERT_REPO_ID) -> bool:
    """Stellt sicher, dass repo_id vollstaendig im lokalen HF-Cache liegt."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return True

    try:
        snapshot_download(repo_id=repo_id, local_files_only=True)
        cache_was_complete = True
    except OSError:
        try:
            snapshot_download(repo_id=repo_id, local_files_only=False)
        except Exception as exc:
            raise TwhinCacheError(
                f"TWHIN-BERT-Cache ({repo_id}) ist weder lokal vollstaendig "
                f"noch aus dem Hub ladbar: {exc}"
            ) from exc
        cache_was_complete = False

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    logger.info(
        "TWHIN-BERT-Cache (%s) %s — Prozess laeuft ab jetzt im HF-Offline-Modus.",
        repo_id,
        "bereits vollstaendig" if cache_was_complete else "per Warmup-Download befuellt",
    )
    return cache_was_complete


_TWHIN_BERT_REPORT_LOGGER_NAMES = frozenset({"transformers.modeling_utils"})
_TWHIN_BERT_EXPECTED_MISSING = frozenset({"pooler.dense.bias", "pooler.dense.weight"})
_TWHIN_BERT_EXPECTED_UNEXPECTED_PREFIX = "cls.predictions"
_WEIGHT_LIST_RE = re.compile(r"\[([^\]]*)\]")


def _extract_weight_names(message: str) -> list[str]:
    match = _WEIGHT_LIST_RE.search(message)
    if not match:
        return []
    return [name.strip().strip("'\"") for name in match.group(1).split(",") if name.strip()]


class TwhinBertLoadReportFilter(logging.Filter):
    """Downgraded den erwarteten TWHIN-BERT-Ladereport auf INFO."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name not in _TWHIN_BERT_REPORT_LOGGER_NAMES:
            return True
        message = record.getMessage()
        if _TWHIN_BERT_REPO_ID not in message:
            return True

        names = _extract_weight_names(message)
        if not names:
            return True

        if "newly initialized" in message and set(names) <= _TWHIN_BERT_EXPECTED_MISSING:
            record.msg = (
                f"TWHIN-BERT ({_TWHIN_BERT_REPO_ID}): Pooler-Gewichte fehlen im "
                "Checkpoint und werden neu initialisiert (erwartet — der "
                "Recommender nutzt Mean-Pooling statt pooler_output, siehe "
                "install_recsys_mean_pooling_patch, #1236)."
            )
            record.args = ()
            record.levelno = logging.INFO
            record.levelname = "INFO"
            return True

        if "were not used when initializing" in message and all(
            name.startswith(_TWHIN_BERT_EXPECTED_UNEXPECTED_PREFIX) for name in names
        ):
            record.msg = (
                f"TWHIN-BERT ({_TWHIN_BERT_REPO_ID}): MLM-Kopf (cls.predictions.*) "
                "wird beim Laden verworfen (erwartet — nur der Encoder wird fuer "
                "Embeddings gebraucht)."
            )
            record.args = ()
            record.levelno = logging.INFO
            record.levelname = "INFO"
            return True

        return True


def install_twhin_bert_load_report_filter() -> None:
    root_logger = logging.getLogger()
    if not any(isinstance(f, TwhinBertLoadReportFilter) for f in root_logger.filters):
        root_logger.addFilter(TwhinBertLoadReportFilter())


def _get_read_available_mb_linux() -> Callable[[], float | None]:
    for mod_name in ("_sim_common", "backend.scripts._sim_common"):
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, "_read_available_mb_linux"):
            fn = mod._read_available_mb_linux
            if fn is not _read_available_mb_linux:
                return fn
    for mod_name in ("_sim_common", "backend.scripts._sim_common"):
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, "_read_available_mb_linux"):
            return mod._read_available_mb_linux
    return _read_available_mb_linux


def _get_ensure_twhin_cache() -> Callable[..., bool]:
    for mod_name in ("_sim_common", "backend.scripts._sim_common"):
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, "ensure_twhin_cache"):
            fn = mod.ensure_twhin_cache
            if fn is not ensure_twhin_cache:
                return fn
    for mod_name in ("_sim_common", "backend.scripts._sim_common"):
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, "ensure_twhin_cache"):
            return mod.ensure_twhin_cache
    return ensure_twhin_cache


def install_bert_memory_profile(
    profile: str | None = None,
    *,
    needs_twhin_bert: bool = True,
    read_available_mb_fn: Callable[[], float | None] | None = None,
    ensure_twhin_cache_fn: Callable[..., bool] | None = None,
) -> str:
    """Aktiviert ein speicherschonendes Ladeprofil für TWHIN-BERT."""
    cache_fn = ensure_twhin_cache_fn or _get_ensure_twhin_cache()
    if needs_twhin_bert:
        cache_fn()
    install_twhin_bert_load_report_filter()

    effective = (profile or os.environ.get("AGORA_BERT_MEMORY_PROFILE") or _BERT_PROFILE_DEFAULT).lower()
    if effective == "off":
        return "off"

    read_avail_fn = read_available_mb_fn or _get_read_available_mb_linux()
    if effective == "auto":
        avail_mb = read_avail_fn()
        inject_fp16 = not (avail_mb is not None and avail_mb >= _BERT_FP32_MIN_AVAIL_MB)
        if inject_fp16:
            logger.warning(
                "TWHIN-BERT laedt in fp16, weil nur %s MB RAM frei sind "
                "(fp32 braucht >= %d MB). Der Twitter-Recommender wird dadurch "
                "sehr langsam (~12 min pro Runde). Container-Speicherlimit "
                "anheben oder AGORA_BERT_MEMORY_PROFILE setzen.",
                "unbekannt" if avail_mb is None else f"{avail_mb:.0f}",
                _BERT_FP32_MIN_AVAIL_MB,
            )
    else:
        inject_fp16 = True

    try:
        import transformers  # type: ignore[import-not-found]
    except ImportError:
        return effective

    auto_model = getattr(transformers, "AutoModel", None)
    if auto_model is None:
        return effective

    original = auto_model.from_pretrained
    if getattr(original, "_agora_bert_memory_profile_applied", False):
        return effective

    torch_float16: Any = None
    try:
        import torch  # type: ignore[import-not-found]
        torch_float16 = torch.float16
    except ImportError:
        pass

    def _patched_from_pretrained(*args: Any, **kwargs: Any):
        model_name = args[0] if args else kwargs.get("pretrained_model_name_or_path")
        if isinstance(model_name, str) and model_name in _TWHIN_BERT_MODEL_NAMES:
            if "low_cpu_mem_usage" not in kwargs:
                kwargs["low_cpu_mem_usage"] = True
            if torch_float16 is not None and inject_fp16 and "torch_dtype" not in kwargs:
                kwargs["torch_dtype"] = torch_float16
        return original(*args, **kwargs)

    _patched_from_pretrained._agora_bert_memory_profile_applied = True  # type: ignore[attr-defined]
    auto_model.from_pretrained = _patched_from_pretrained
    return effective


def install_recsys_mean_pooling_patch() -> bool:
    """Ersetzt process_recsys_posts.process_batch durch Mean-Pooling."""
    try:
        from oasis.social_platform import process_recsys_posts  # type: ignore[import-not-found]
    except ImportError:
        return False

    original = process_recsys_posts.process_batch
    if getattr(original, "_agora_mean_pooling_applied", False):
        return True

    import torch  # type: ignore[import-not-found]

    @torch.no_grad()
    def _mean_pooled_process_batch(model: Any, tokenizer: Any, batch_texts: list[str]) -> Any:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        inputs = tokenizer(batch_texts, return_tensors="pt", padding=True, truncation=True)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        outputs = model(**inputs)
        mask = inputs["attention_mask"].unsqueeze(-1).to(outputs.last_hidden_state.dtype)
        return (outputs.last_hidden_state * mask).sum(1) / mask.sum(1).clamp(min=1e-9)

    _mean_pooled_process_batch._agora_mean_pooling_applied = True  # type: ignore[attr-defined]
    process_recsys_posts.process_batch = _mean_pooled_process_batch
    return True


def _read_rss_mb_linux() -> float | None:
    """Liest VmRSS aus /proc/self/status."""
    status_path = Path(f"/proc/{os.getpid()}/status")
    try:
        with status_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        return None
    return None


def _read_available_mb_linux() -> float | None:
    """Verfuegbaren RAM in MB — cgroup-Limit bevorzugt, Fallback /proc/meminfo."""
    try:
        limit_text = Path("/sys/fs/cgroup/memory.max").read_text(encoding="utf-8").strip()
        if limit_text != "max":
            limit_bytes = int(limit_text)
            usage_bytes = int(
                Path("/sys/fs/cgroup/memory.current").read_text(encoding="utf-8").strip()
            )
            return max(0.0, (limit_bytes - usage_bytes) / 1024.0 / 1024.0)
    except (OSError, ValueError):
        pass
    try:
        limit_bytes = int(
            Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
            .read_text(encoding="utf-8")
            .strip()
        )
        if limit_bytes < (1 << 62):
            usage_bytes = int(
                Path("/sys/fs/cgroup/memory/memory.usage_in_bytes")
                .read_text(encoding="utf-8")
                .strip()
            )
            return max(0.0, (limit_bytes - usage_bytes) / 1024.0 / 1024.0)
    except (OSError, ValueError):
        pass
    try:
        with Path("/proc/meminfo").open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return float(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        pass
    return None


def make_default_memory_sink(project_root: Path) -> Path:
    """Baut den Default-NDJSON-Sink-Pfad fuer den Memory-Sampler."""
    return project_root / ".runtime" / f"mem_profile.{os.getpid()}.ndjson"


def _get_read_rss_mb_linux() -> Callable[[], float | None]:
    for mod_name in ("backend.scripts._sim_common", "_sim_common"):
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, "_read_rss_mb_linux"):
            return mod._read_rss_mb_linux
    return _read_rss_mb_linux


def install_memory_sampler(
    sink: Path,
    *,
    interval_s: float = 0.5,
    rss_reader: Callable[[], float | None] | None = None,
) -> Callable[[], None]:
    """Startet bei aktivierter Debug-Konfiguration einen Hintergrund-Thread zur RSS-Speicherüberwachung."""
    enabled = os.environ.get("AGORA_DEBUG_MEMORY", "").lower() in {"1", "true", "yes"}
    if not enabled:
        return _noop_stop

    if rss_reader is None:
        def rss_reader() -> float | None:
            reader = _get_read_rss_mb_linux()
            return reader()

        user_supplied_reader = False
    else:
        user_supplied_reader = True

    if (
        not user_supplied_reader
        and rss_reader() is None
        and not Path(f"/proc/{os.getpid()}/status").exists()
    ):
        def rss_reader() -> float | None:
            return None

    stop_event = threading.Event()
    start = time.monotonic()
    sink.parent.mkdir(parents=True, exist_ok=True)
    sink_handle = sink.open("a", encoding="utf-8")

    def _sampler_loop() -> None:
        while not stop_event.is_set():
            snap = {
                "label": "tick",
                "rss_mb": rss_reader(),
                "time_s": time.monotonic() - start,
            }
            try:
                sink_handle.write(json.dumps(snap) + "\n")
                sink_handle.flush()
            except (OSError, ValueError):
                pass
            stop_event.wait(interval_s)

    thread = threading.Thread(
        target=_sampler_loop,
        name="agora-memory-sampler",
        daemon=True,
    )
    thread.start()

    def _stop() -> None:
        stop_event.set()
        thread.join(timeout=interval_s * 2)
        try:
            sink_handle.close()
        except OSError:
            pass

    return _stop


def _noop_stop() -> None:
    """Führt beim Beenden des Speichersamplers keine Aktion aus."""
    return None


_REDDIT_NESTED_EXPECTED_VERSION = "0.2.5"


def install_reddit_nested_comments_patch() -> bool:
    """Ergaenzt OASIS 0.2.5 um Reddit-Kommentar-Verschachtelung."""
    import importlib.metadata

    _patch_logger = logging.getLogger("agora._sim_common")

    try:
        actual_version = importlib.metadata.version("camel-oasis")
    except importlib.metadata.PackageNotFoundError:
        _patch_logger.warning(
            "install_reddit_nested_comments_patch: camel-oasis nicht gefunden "
            "— Patch NICHT installiert (sichtbare Degradation, #1713 S5)"
        )
        return False

    if actual_version != _REDDIT_NESTED_EXPECTED_VERSION:
        _patch_logger.warning(
            "install_reddit_nested_comments_patch: erwartet camel-oasis==%s, "
            "gefunden %s — Patch NICHT installiert (sichtbare Degradation, #1713 S5)",
            _REDDIT_NESTED_EXPECTED_VERSION,
            actual_version,
        )
        return False

    try:
        import oasis.social_platform.database as _oasis_db
        import oasis.social_platform.platform as _oasis_platform
        import oasis.social_platform.platform_utils as _oasis_pu
        import oasis.social_agent.agent_action as _oasis_aa
    except ImportError:
        return False

    if getattr(_oasis_db.create_db, "_agora_nested_comments_applied", False):
        return True

    _original_create_db = _oasis_db.create_db

    def _patched_create_db(db_path: Any = None) -> Any:
        conn, cursor = _original_create_db(db_path)
        cursor.execute("PRAGMA table_info(comment)")
        cols = {row[1] for row in cursor.fetchall()}
        if "parent_comment_id" not in cols:
            cursor.execute(
                "ALTER TABLE comment ADD COLUMN parent_comment_id INTEGER"
            )
            conn.commit()
        return conn, cursor

    _patched_create_db._agora_nested_comments_applied = True
    _oasis_db.create_db = _patched_create_db
    _oasis_platform.create_db = _patched_create_db

    _original_platform_create_comment = _oasis_platform.Platform.create_comment

    async def _patched_platform_create_comment(
        self: Any, agent_id: int, comment_message: Any
    ) -> Any:
        if isinstance(comment_message, (list, tuple)) and len(comment_message) == 3:
            post_id_arg, content_arg, parent_comment_id_arg = comment_message
        else:
            post_id_arg, content_arg = comment_message
            parent_comment_id_arg = None

        if parent_comment_id_arg is not None:
            self.db_cursor.execute(
                "SELECT post_id FROM comment WHERE comment_id = ?",
                (parent_comment_id_arg,),
            )
            row = self.db_cursor.fetchone()
            if row is None:
                return {
                    "success": False,
                    "error": (
                        f"parent_comment_id {parent_comment_id_arg} existiert nicht"
                    ),
                }
            if row[0] != post_id_arg:
                return {
                    "success": False,
                    "error": (
                        f"parent_comment_id {parent_comment_id_arg} gehoert zu "
                        f"post_id {row[0]}, nicht zu {post_id_arg}"
                    ),
                }

        result = await _original_platform_create_comment(
            self, agent_id, (post_id_arg, content_arg)
        )
        if result.get("success") and parent_comment_id_arg is not None:
            comment_id_new = result.get("comment_id")
            if comment_id_new is not None:
                self.db_cursor.execute(
                    "UPDATE comment SET parent_comment_id = ? WHERE comment_id = ?",
                    (parent_comment_id_arg, comment_id_new),
                )
                self.db.commit()
        return result

    _patched_platform_create_comment.__name__ = "create_comment"
    _patched_platform_create_comment.__qualname__ = _original_platform_create_comment.__qualname__
    _patched_platform_create_comment._agora_nested_comments_applied = True
    _oasis_platform.Platform.create_comment = _patched_platform_create_comment

    _original_sa_create_comment = _oasis_aa.SocialAction.create_comment

    async def _patched_sa_create_comment(
        self: Any, post_id: int, content: str, parent_comment_id: int | None = None
    ) -> Any:
        if parent_comment_id is not None:
            comment_message: Any = (post_id, content, parent_comment_id)
        else:
            comment_message = (post_id, content)
        return await self.perform_action(
            comment_message,
            "create_comment",
        )

    _patched_sa_create_comment.__name__ = "create_comment"
    _patched_sa_create_comment.__qualname__ = _original_sa_create_comment.__qualname__
    _patched_sa_create_comment._agora_nested_comments_applied = True
    _oasis_aa.SocialAction.create_comment = _patched_sa_create_comment

    _original_add_comments = _oasis_pu.PlatformUtils._add_comments_to_posts

    def _patched_add_comments_to_posts(self: Any, posts_results: Any) -> Any:
        posts = _original_add_comments(self, posts_results)
        for post in posts:
            for comment in post.get("comments", []):
                cid = comment.get("comment_id")
                if cid is not None:
                    try:
                        self.db_cursor.execute(
                            "SELECT parent_comment_id FROM comment WHERE comment_id = ?",
                            (cid,),
                        )
                        pcid_row = self.db_cursor.fetchone()
                        comment["parent_comment_id"] = pcid_row[0] if pcid_row else None
                    except sqlite3.Error:
                        logger.warning(
                            "parent_comment_id-Lookup fuer comment_id=%s fehlgeschlagen "
                            "(#1713 S5) — Feld bleibt None",
                            cid,
                            exc_info=True,
                        )
                        comment["parent_comment_id"] = None
                else:
                    comment["parent_comment_id"] = None
        return posts

    _patched_add_comments_to_posts._agora_nested_comments_applied = True
    _oasis_pu.PlatformUtils._add_comments_to_posts = _patched_add_comments_to_posts

    _patch_logger.info(
        "install_reddit_nested_comments_patch: alle Patches installiert "
        "(camel-oasis==%s, #1713 S5)",
        actual_version,
    )
    return True
