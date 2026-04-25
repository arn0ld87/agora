"""Optional Redis Pub/Sub listener for the OASIS subprocess scripts.

Issue #17 Phase D. The bridge runs in the same asyncio event loop as the
OASIS environment and consumes ``agora:sim:<id>:rpc.command`` messages
in real time. When ``REDIS_URL`` is unset or Redis is unreachable it
stays inactive and the legacy file IPC handler keeps doing the work.

Usage from a subprocess script::

    bridge = RedisIPCBridge(
        simulation_id=sim_id,
        redis_url=os.environ.get("REDIS_URL"),
        on_command=ipc_handler.dispatch_bus_event,
    )
    started = await bridge.start()
    ...
    await bridge.stop()

The ``on_command`` callback receives a decoded bus event dict
``{type, simulation_id, payload, correlation_id, ts}``. It is the
caller's responsibility to dedupe against the file-polling path.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger("agora.subprocess_redis_bridge")

_CHANNEL_PREFIX = "agora:sim"


def channel_key(simulation_id: str, channel: str) -> str:
    """Mirror of ``RedisEventBus._channel_key``; kept local so this module
    has no dependency on Flask app code."""
    return f"{_CHANNEL_PREFIX}:{simulation_id}:{channel}"


class RedisIPCBridge:
    """Async Redis Pub/Sub bridge used by OASIS subprocess scripts."""

    def __init__(
        self,
        simulation_id: str,
        redis_url: Optional[str],
        *,
        on_command: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.simulation_id = simulation_id
        self.redis_url = redis_url
        self._on_command = on_command
        self._client: Any = None
        self._pubsub: Any = None
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self.active = False

    async def start(self) -> bool:
        """Subscribe to the rpc.command channel. Returns True on success."""
        if not self.redis_url:
            logger.info("RedisIPCBridge: REDIS_URL unset — bridge disabled")
            return False
        try:
            import redis.asyncio as aioredis  # type: ignore[import-not-found]
        except ImportError:
            logger.warning(
                "RedisIPCBridge: redis.asyncio not available — bridge disabled"
            )
            return False
        try:
            self._client = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._client.ping()
        except Exception as exc:  # noqa: BLE001 — diagnostic logging only
            logger.warning(
                "RedisIPCBridge: Redis unreachable at %s (%s) — bridge disabled",
                self.redis_url,
                exc,
            )
            await self._safe_close()
            return False

        cmd_channel = channel_key(self.simulation_id, "rpc.command")
        self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        await self._pubsub.subscribe(cmd_channel)
        self._task = asyncio.create_task(self._listen(cmd_channel))
        self.active = True
        logger.info("RedisIPCBridge listening on %s", cmd_channel)
        return True

    async def _listen(self, cmd_channel: str) -> None:
        try:
            while not self._stop.is_set():
                msg = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if not msg or msg.get("type") != "message":
                    continue
                raw = msg.get("data")
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning(
                        "RedisIPCBridge: dropping malformed event on %s: %s",
                        cmd_channel,
                        exc,
                    )
                    continue
                try:
                    await self._on_command(data)
                except Exception:
                    logger.exception(
                        "RedisIPCBridge: on_command callback raised for %s",
                        data.get("correlation_id"),
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("RedisIPCBridge listener crashed")

    async def publish_response(
        self, correlation_id: str, payload: Dict[str, Any]
    ) -> bool:
        """Publish a response on ``rpc.response.<correlation_id>``.

        Returns True on success, False if the bridge is inactive or the
        publish failed (caller should keep the file response as fallback).
        """
        if not self.active or self._client is None:
            return False
        key = channel_key(self.simulation_id, f"rpc.response.{correlation_id}")
        try:
            await self._client.publish(
                key, json.dumps(payload, ensure_ascii=False)
            )
            return True
        except Exception:
            logger.exception(
                "RedisIPCBridge: failed to publish response on %s", key
            )
            return False

    async def stop(self) -> None:
        if not self.active and self._task is None:
            return
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        await self._safe_close()
        self.active = False

    async def _safe_close(self) -> None:
        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe()
            except Exception:
                pass
            try:
                await self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None


__all__ = ["RedisIPCBridge", "channel_key"]
