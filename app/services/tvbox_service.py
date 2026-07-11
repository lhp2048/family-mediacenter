import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_settings
from app.db import async_session
from app.models.tvbox_source import (
    TvboxSourceCreate,
    TvboxSourceORM,
    TvboxSourceResponse,
    TvboxSourceTestResult,
    TvboxSourceUpdate,
)
from app.tvbox_testing.config_parse import is_live_url


def _feed_settings() -> dict[str, Any]:
    tvbox = load_settings().tvbox
    return {
        "feed_title": tvbox.feed_title or "Family Media Center TVBox 多合一",
        "feed_include_playlists": bool(getattr(tvbox, "feed_include_playlists", True)),
    }


def _is_live_source(url: str, note: str = "") -> bool:
    note_lower = (note or "").lower()
    if "直播" in note_lower or "m3u" in note_lower:
        return True
    return is_live_url(url)


def _parse_test_detail(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _compact_test_detail(data: dict[str, Any]) -> dict[str, Any]:
    """List API: keep summary only to avoid huge payloads and slow UI rendering."""
    if not data:
        return {}
    summary = data.get("summary")
    if isinstance(summary, dict):
        return {"summary": summary}
    return {}


class TvboxService:
    def _to_response(
        self,
        row: TvboxSourceORM,
        *,
        compact_detail: bool = False,
    ) -> TvboxSourceResponse:
        detail = _parse_test_detail(row.last_test_detail or "")
        if compact_detail:
            detail = _compact_test_detail(detail)
        return TvboxSourceResponse(
            id=row.id,
            name=row.name,
            url=row.url,
            enabled=row.enabled,
            sort_order=row.sort_order,
            note=row.note or "",
            last_test_at=row.last_test_at,
            last_test_ok=row.last_test_ok,
            last_test_message=row.last_test_message or "",
            last_test_latency_ms=row.last_test_latency_ms,
            last_test_summary=row.last_test_summary or "",
            last_test_detail=detail,
            last_test_score=row.last_test_score,
            last_test_grade=row.last_test_grade or "",
            created_at=row.created_at,
        )

    async def _next_sort_order(self, session: AsyncSession) -> int:
        result = await session.execute(
            select(TvboxSourceORM.sort_order)
            .order_by(TvboxSourceORM.sort_order.desc())
            .limit(1)
        )
        top = result.scalar_one_or_none()
        return (top or -1) + 1

    async def list_sources(self, *, enabled_only: bool = False) -> list[TvboxSourceResponse]:
        async with async_session() as session:
            stmt = select(TvboxSourceORM).order_by(TvboxSourceORM.sort_order, TvboxSourceORM.id)
            if enabled_only:
                stmt = stmt.where(TvboxSourceORM.enabled.is_(True))
            result = await session.execute(stmt)
            return [self._to_response(row, compact_detail=True) for row in result.scalars().all()]

    async def get_source(self, source_id: int) -> Optional[TvboxSourceResponse]:
        async with async_session() as session:
            row = await session.get(TvboxSourceORM, source_id)
            return self._to_response(row, compact_detail=False) if row else None

    async def create_source(self, data: TvboxSourceCreate) -> TvboxSourceResponse:
        async with async_session() as session:
            row = TvboxSourceORM(
                name=data.name.strip(),
                url=data.url.strip(),
                enabled=data.enabled,
                note=data.note.strip(),
                sort_order=await self._next_sort_order(session),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_response(row)

    async def update_source(self, source_id: int, data: TvboxSourceUpdate) -> TvboxSourceResponse:
        async with async_session() as session:
            row = await session.get(TvboxSourceORM, source_id)
            if not row:
                raise ValueError("源不存在")
            if data.name is not None:
                row.name = data.name.strip()
            if data.url is not None:
                row.url = data.url.strip()
            if data.enabled is not None:
                row.enabled = data.enabled
            if data.note is not None:
                row.note = data.note.strip()
            if data.sort_order is not None:
                row.sort_order = data.sort_order
            await session.commit()
            await session.refresh(row)
            return self._to_response(row)

    async def delete_source(self, source_id: int) -> None:
        async with async_session() as session:
            row = await session.get(TvboxSourceORM, source_id)
            if not row:
                raise ValueError("源不存在")
            await session.delete(row)
            await session.commit()

    async def reorder_sources(self, items: list[tuple[int, int]]) -> list[TvboxSourceResponse]:
        async with async_session() as session:
            for source_id, sort_order in items:
                row = await session.get(TvboxSourceORM, source_id)
                if row:
                    row.sort_order = sort_order
            await session.commit()
        return await self.list_sources()

    async def build_merged_config(self, *, public_base: str = "") -> dict[str, Any]:
        cfg = _feed_settings()
        sources = await self.list_sources(enabled_only=True)
        vod_urls: list[dict[str, str]] = []
        live_channels: list[dict[str, str]] = []

        for item in sources:
            if _is_live_source(item.url, item.note):
                live_channels.append({"name": item.name, "url": item.url})
            else:
                vod_urls.append({"name": item.name, "url": item.url})

        merged: dict[str, Any] = {}
        if vod_urls:
            merged["urls"] = vod_urls

        lives_groups: list[dict[str, Any]] = []
        if live_channels:
            lives_groups.append(
                {
                    "group": cfg["feed_title"],
                    "channels": live_channels,
                }
            )

        if cfg["feed_include_playlists"] and public_base.strip():
            from app.services.playlist_service import playlist_service

            playlist_groups = await playlist_service.build_tvbox_live_groups(
                public_base
            )
            if playlist_groups:
                lives_groups.extend(playlist_groups)

        if lives_groups:
            merged["lives"] = lives_groups
        return merged

    async def test_source(
        self,
        source_id: int,
        *,
        persist: bool = True,
        mode: str = "quick",
    ) -> TvboxSourceTestResult:
        from app.tvbox_testing.orchestrator import run_source_test
        from app.tvbox_testing.types import TestMode

        test_mode = TestMode.FULL if mode == "full" else TestMode.QUICK
        return await run_source_test(source_id, mode=test_mode, persist=persist)

    async def test_all_sources(self, *, mode: str = "quick") -> list[TvboxSourceTestResult]:
        from app.tvbox_testing.orchestrator import run_all_source_tests
        from app.tvbox_testing.types import TestMode

        test_mode = TestMode.FULL if mode == "full" else TestMode.QUICK
        return await run_all_source_tests(mode=test_mode)


tvbox_service = TvboxService()
