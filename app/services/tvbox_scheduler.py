"""Background scheduled TVBox source testing."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

import httpx

from app.config import load_settings
from app.tvbox_testing.orchestrator import run_all_source_tests
from app.tvbox_testing.types import TestMode

logger = logging.getLogger(__name__)


class TvboxScheduler:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()
        self._last_run_at: Optional[datetime] = None
        self._last_result: dict[str, Any] = {}

    def status(self) -> dict[str, Any]:
        tvbox = load_settings().tvbox
        return {
            "enabled": bool(getattr(tvbox, "test_schedule_enabled", False)),
            "interval_minutes": int(getattr(tvbox, "test_schedule_interval_minutes", 360) or 360),
            "mode": str(getattr(tvbox, "test_schedule_mode", "full") or "full"),
            "running": self._running,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "last_result": dict(self._last_result),
        }

    async def start(self) -> None:
        tvbox = load_settings().tvbox
        if not getattr(tvbox, "test_schedule_enabled", False):
            return
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            logger.info(
                "TVBox scheduled testing enabled (every %s min, mode=%s)",
                getattr(tvbox, "test_schedule_interval_minutes", 360),
                getattr(tvbox, "test_schedule_mode", "full"),
            )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        tvbox = load_settings().tvbox
        interval = max(30, int(getattr(tvbox, "test_schedule_interval_minutes", 360) or 360))
        while True:
            await asyncio.sleep(interval * 60)
            await self.run_once()

    async def run_once(self, *, mode_override: str | None = None) -> None:
        if self._running:
            logger.info("TVBox scheduled test skipped: previous run still active")
            return
        async with self._lock:
            if self._running:
                return
            self._running = True
        try:
            tvbox = load_settings().tvbox
            mode_str = mode_override or str(getattr(tvbox, "test_schedule_mode", "full") or "full")
            mode = TestMode.FULL if mode_str == "full" else TestMode.QUICK
            logger.info("TVBox scheduled test started (mode=%s)", mode.value)
            results = await run_all_source_tests(mode=mode)
            ok_count = sum(1 for item in results if item.ok)
            fail_count = len(results) - ok_count
            logger.info(
                "TVBox scheduled test finished: ok=%s fail=%s total=%s",
                ok_count,
                fail_count,
                len(results),
            )
            self._last_run_at = datetime.now()
            self._last_result = {
                "total": len(results),
                "ok_count": ok_count,
                "fail_count": fail_count,
                "mode": mode.value,
            }
            await self._notify(
                ok_count=ok_count,
                fail_count=fail_count,
                total=len(results),
                mode=mode.value,
            )
        except Exception:
            logger.exception("TVBox scheduled test failed")
        finally:
            self._running = False

    async def _notify(
        self,
        *,
        ok_count: int,
        fail_count: int,
        total: int,
        mode: str,
    ) -> None:
        webhook = (load_settings().tvbox.test_notify_webhook or "").strip()
        if not webhook:
            return
        payload = {
            "event": "tvbox_scheduled_test",
            "time": datetime.now().isoformat(),
            "mode": mode,
            "total": total,
            "ok_count": ok_count,
            "fail_count": fail_count,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(webhook, json=payload)
        except Exception:
            logger.exception("TVBox notify webhook failed: %s", webhook)


tvbox_scheduler = TvboxScheduler()
