from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.models.pagination import (
    DEFAULT_PAGE_SIZE,
    PaginatedResponse,
    normalize_page,
    normalize_page_size,
)
from app.models.playlist import (
    DEFAULT_PLAYLIST_NAME,
    PlaylistCreate,
    PlaylistItemORM,
    PlaylistItemResponse,
    PlaylistORM,
    PlaylistReloadResult,
    PlaylistResponse,
)
from app.models.task import TaskORM, TaskStatus
from app.services.file_manager import build_public_url, get_download_root
from app.services.playlist_m3u import playlist_live_m3u_url, render_live_m3u
from app.utils.encoding import title_from_task_file
from app.utils.media import (
    is_media_path,
    media_display_name,
    media_type_for_path,
    resolve_media_rel_path,
    to_rel_path,
)


class PlaylistService:
    def _item_to_response(
        self, item: PlaylistItemORM, public_base: str
    ) -> PlaylistItemResponse:
        rel = item.rel_path
        path = resolve_media_rel_path(rel)
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        name = media_display_name(rel, item.title)
        return PlaylistItemResponse(
            id=item.id,
            playlist_id=item.playlist_id,
            rel_path=rel,
            title=item.title or name,
            name=name,
            size=size,
            media_type=media_type_for_path(rel),
            task_id=item.task_id,
            sort_order=item.sort_order,
            public_url=build_public_url(rel, public_base) if exists else "",
            exists=exists,
            added_at=item.added_at,
        )

    def _playlist_to_response(
        self, playlist: PlaylistORM, item_count: Optional[int] = None
    ) -> PlaylistResponse:
        count = item_count if item_count is not None else len(playlist.items)
        return PlaylistResponse(
            id=playlist.id,
            name=playlist.name,
            is_default=playlist.is_default,
            item_count=count,
            created_at=playlist.created_at,
        )

    def _scan_media_rel_paths(self) -> set[str]:
        root = get_download_root()
        paths: set[str] = set()
        if not root.exists():
            return paths
        for path in root.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            if not is_media_path(path):
                continue
            paths.add(path.relative_to(root).as_posix())
        return paths

    async def ensure_default_playlist(self) -> PlaylistORM:
        async with async_session() as session:
            result = await session.execute(
                select(PlaylistORM).where(PlaylistORM.is_default.is_(True))
            )
            playlist = result.scalar_one_or_none()
            if playlist:
                return playlist
            playlist = PlaylistORM(name=DEFAULT_PLAYLIST_NAME, is_default=True)
            session.add(playlist)
            await session.commit()
            await session.refresh(playlist)
            return playlist

    async def _next_sort_order(self, session: AsyncSession, playlist_id: int) -> int:
        result = await session.execute(
            select(func.max(PlaylistItemORM.sort_order)).where(
                PlaylistItemORM.playlist_id == playlist_id
            )
        )
        max_order = result.scalar()
        return (max_order or 0) + 1

    async def _add_item_if_new(
        self,
        session: AsyncSession,
        playlist_id: int,
        rel_path: str,
        title: str = "",
        task_id: Optional[int] = None,
    ) -> bool:
        if not rel_path or not is_media_path(rel_path):
            return False
        result = await session.execute(
            select(PlaylistItemORM).where(
                PlaylistItemORM.playlist_id == playlist_id,
                PlaylistItemORM.rel_path == rel_path,
            )
        )
        if result.scalar_one_or_none():
            return False
        sort_order = await self._next_sort_order(session, playlist_id)
        session.add(
            PlaylistItemORM(
                playlist_id=playlist_id,
                rel_path=rel_path,
                title=title,
                task_id=task_id,
                sort_order=sort_order,
            )
        )
        return True

    async def add_media_to_default(
        self,
        rel_path: str,
        title: str = "",
        task_id: Optional[int] = None,
    ) -> bool:
        default = await self.ensure_default_playlist()
        async with async_session() as session:
            added = await self._add_item_if_new(
                session, default.id, rel_path, title, task_id
            )
            if added:
                await session.commit()
            return added

    async def on_task_completed(self, task: TaskORM) -> None:
        file_path = task.file_path
        if not file_path or not Path(file_path).exists():
            if task.output_dir:
                base = Path(task.output_dir)
                candidates = list(base.glob(f"task_{task.id}_*"))
                if candidates:
                    file_path = str(max(candidates, key=lambda p: p.stat().st_mtime))
        if not file_path or not Path(file_path).exists():
            return
        if not is_media_path(file_path):
            return
        rel_path = to_rel_path(file_path)
        if not rel_path:
            return
        title = task.title or title_from_task_file(file_path, task.id)
        await self.add_media_to_default(rel_path, title, task.id)

    async def sync_default_from_tasks(self) -> int:
        default = await self.ensure_default_playlist()
        async with async_session() as session:
            result = await session.execute(
                select(TaskORM).where(TaskORM.status == TaskStatus.COMPLETED.value)
            )
            tasks = result.scalars().all()
            added_count = 0
            for task in tasks:
                file_path = task.file_path
                if not file_path or not Path(file_path).exists():
                    if task.output_dir:
                        base = Path(task.output_dir)
                        candidates = list(base.glob(f"task_{task.id}_*"))
                        if candidates:
                            file_path = str(
                                max(candidates, key=lambda p: p.stat().st_mtime)
                            )
                if not file_path or not Path(file_path).exists():
                    continue
                if not is_media_path(file_path):
                    continue
                rel_path = to_rel_path(file_path)
                if not rel_path:
                    continue
                title = task.title or title_from_task_file(file_path, task.id)
                if await self._add_item_if_new(
                    session, default.id, rel_path, title, task.id
                ):
                    added_count += 1
            await session.commit()
            return added_count

    async def list_playlists(self) -> list[PlaylistResponse]:
        async with async_session() as session:
            result = await session.execute(
                select(PlaylistORM, func.count(PlaylistItemORM.id))
                .outerjoin(PlaylistItemORM, PlaylistORM.id == PlaylistItemORM.playlist_id)
                .group_by(PlaylistORM.id)
                .order_by(PlaylistORM.is_default.desc(), PlaylistORM.id)
            )
            rows = result.all()
            return [
                PlaylistResponse(
                    id=row[0].id,
                    name=row[0].name,
                    is_default=row[0].is_default,
                    item_count=row[1],
                    created_at=row[0].created_at,
                )
                for row in rows
            ]

    async def get_playlist(self, playlist_id: int) -> Optional[PlaylistResponse]:
        async with async_session() as session:
            result = await session.execute(
                select(PlaylistORM, func.count(PlaylistItemORM.id))
                .outerjoin(PlaylistItemORM, PlaylistORM.id == PlaylistItemORM.playlist_id)
                .where(PlaylistORM.id == playlist_id)
                .group_by(PlaylistORM.id)
            )
            row = result.one_or_none()
            if not row:
                return None
            return PlaylistResponse(
                id=row[0].id,
                name=row[0].name,
                is_default=row[0].is_default,
                item_count=row[1],
                created_at=row[0].created_at,
            )

    async def get_default_playlist(self) -> PlaylistResponse:
        default = await self.ensure_default_playlist()
        playlist = await self.get_playlist(default.id)
        return playlist or self._playlist_to_response(default, 0)

    async def create_playlist(self, data: PlaylistCreate) -> PlaylistResponse:
        name = data.name.strip()
        if not name:
            raise ValueError("播放列表名称不能为空")
        async with async_session() as session:
            playlist = PlaylistORM(name=name, is_default=False)
            session.add(playlist)
            await session.commit()
            await session.refresh(playlist)
            return self._playlist_to_response(playlist, 0)

    async def delete_playlist(self, playlist_id: int) -> None:
        async with async_session() as session:
            playlist = await session.get(PlaylistORM, playlist_id)
            if not playlist:
                raise ValueError("播放列表不存在")
            if playlist.is_default:
                raise ValueError("不能删除默认播放列表")
            await session.delete(playlist)
            await session.commit()

    async def list_items(
        self,
        playlist_id: int,
        public_base: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ):
        async with async_session() as session:
            result = await session.execute(
                select(PlaylistORM).where(PlaylistORM.id == playlist_id)
            )
            if not result.scalar_one_or_none():
                raise ValueError("播放列表不存在")

            if page is not None:
                pg = normalize_page(page)
                ps = normalize_page_size(page_size or DEFAULT_PAGE_SIZE)
                count_result = await session.execute(
                    select(func.count(PlaylistItemORM.id)).where(
                        PlaylistItemORM.playlist_id == playlist_id
                    )
                )
                total = int(count_result.scalar() or 0)
                result = await session.execute(
                    select(PlaylistItemORM)
                    .where(PlaylistItemORM.playlist_id == playlist_id)
                    .order_by(PlaylistItemORM.sort_order, PlaylistItemORM.id)
                    .offset((pg - 1) * ps)
                    .limit(ps)
                )
                items = result.scalars().all()
                responses = [self._item_to_response(item, public_base) for item in items]
                return PaginatedResponse.from_items(responses, total, pg, ps)

            result = await session.execute(
                select(PlaylistItemORM)
                .where(PlaylistItemORM.playlist_id == playlist_id)
                .order_by(PlaylistItemORM.sort_order, PlaylistItemORM.id)
            )
            items = result.scalars().all()
            return [self._item_to_response(item, public_base) for item in items]

    async def reload_playlist_from_disk(self, playlist_id: int) -> PlaylistReloadResult:
        disk_paths = self._scan_media_rel_paths()
        added = 0
        removed = 0
        item_count = 0

        async with async_session() as session:
            playlist = await session.get(PlaylistORM, playlist_id)
            if not playlist:
                raise ValueError("播放列表不存在")

            result = await session.execute(
                select(PlaylistItemORM).where(PlaylistItemORM.playlist_id == playlist_id)
            )
            items = result.scalars().all()
            existing_rels = {item.rel_path: item for item in items}

            for rel_path, item in existing_rels.items():
                if rel_path not in disk_paths:
                    await session.delete(item)
                    removed += 1

            for rel_path in sorted(disk_paths):
                if rel_path in existing_rels:
                    continue
                if await self._add_item_if_new(
                    session,
                    playlist_id,
                    rel_path,
                    media_display_name(rel_path),
                    None,
                ):
                    added += 1

            await session.commit()

            count_result = await session.execute(
                select(func.count(PlaylistItemORM.id)).where(
                    PlaylistItemORM.playlist_id == playlist_id
                )
            )
            item_count = count_result.scalar() or 0

        parts: list[str] = []
        if added:
            parts.append(f"新增 {added} 个")
        if removed:
            parts.append(f"移除 {removed} 个")
        message = "、".join(parts) if parts else "已与本地目录同步，无变更"

        return PlaylistReloadResult(
            added=added,
            removed=removed,
            item_count=item_count,
            message=message,
        )

    async def add_item(
        self,
        playlist_id: int,
        rel_path: Optional[str] = None,
        task_id: Optional[int] = None,
        public_base: str = "",
    ) -> PlaylistItemResponse:
        resolved_rel = rel_path or ""
        title = ""
        resolved_task_id: Optional[int] = task_id

        if task_id:
            async with async_session() as session:
                task = await session.get(TaskORM, task_id)
                if not task:
                    raise ValueError("任务不存在")
                if task.status != TaskStatus.COMPLETED.value:
                    raise ValueError("只能添加已完成的任务")
                file_path = task.file_path
                if not file_path or not Path(file_path).exists():
                    if task.output_dir:
                        base = Path(task.output_dir)
                        candidates = list(base.glob(f"task_{task.id}_*"))
                        if candidates:
                            file_path = str(
                                max(candidates, key=lambda p: p.stat().st_mtime)
                            )
                if not file_path or not Path(file_path).exists():
                    raise ValueError("任务文件不存在")
                if not is_media_path(file_path):
                    raise ValueError("不是视频或音频文件")
                resolved_rel = to_rel_path(file_path)
                if not resolved_rel:
                    raise ValueError("文件不在下载目录内")
                title = task.title or title_from_task_file(file_path, task.id)

        if not resolved_rel:
            raise ValueError("请提供 rel_path 或 task_id")

        path = resolve_media_rel_path(resolved_rel)
        if not path.is_file():
            raise ValueError("文件不存在")
        if not is_media_path(path):
            raise ValueError("不是视频或音频文件")

        async with async_session() as session:
            result = await session.execute(
                select(PlaylistORM).where(PlaylistORM.id == playlist_id)
            )
            if not result.scalar_one_or_none():
                raise ValueError("播放列表不存在")

            existing = await session.execute(
                select(PlaylistItemORM).where(
                    PlaylistItemORM.playlist_id == playlist_id,
                    PlaylistItemORM.rel_path == resolved_rel,
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError("该文件已在播放列表中")

            sort_order = await self._next_sort_order(session, playlist_id)
            item = PlaylistItemORM(
                playlist_id=playlist_id,
                rel_path=resolved_rel,
                title=title,
                task_id=resolved_task_id,
                sort_order=sort_order,
            )
            session.add(item)
            await session.commit()
            await session.refresh(item)
            return self._item_to_response(item, public_base)

    async def remove_item(self, playlist_id: int, item_id: int) -> None:
        async with async_session() as session:
            item = await session.get(PlaylistItemORM, item_id)
            if not item or item.playlist_id != playlist_id:
                raise ValueError("条目不存在")
            await session.delete(item)
            await session.commit()

    async def remove_items_by_rel_path(self, rel_path: str) -> int:
        async with async_session() as session:
            result = await session.execute(
                select(PlaylistItemORM).where(PlaylistItemORM.rel_path == rel_path)
            )
            items = result.scalars().all()
            for item in items:
                await session.delete(item)
            await session.commit()
            return len(items)

    async def build_live_m3u(self, playlist_id: int, public_base: str) -> str:
        async with async_session() as session:
            playlist = await session.get(PlaylistORM, playlist_id)
            if not playlist:
                raise ValueError("播放列表不存在")
            result = await session.execute(
                select(PlaylistItemORM)
                .where(PlaylistItemORM.playlist_id == playlist_id)
                .order_by(PlaylistItemORM.sort_order, PlaylistItemORM.id)
            )
            items = [
                self._item_to_response(row, public_base)
                for row in result.scalars().all()
            ]
        return render_live_m3u(items)

    async def build_tvbox_live_groups(
        self, public_base: str
    ) -> list[dict[str, Any]]:
        """Each non-empty playlist becomes one lives group with a combined live.m3u channel."""
        if not public_base.strip():
            return []
        groups: list[dict[str, Any]] = []
        for playlist in await self.list_playlists():
            if playlist.item_count <= 0:
                continue
            try:
                body = await self.build_live_m3u(playlist.id, public_base)
            except ValueError:
                continue
            if not body.strip() or body.strip() == "#EXTM3U":
                continue
            groups.append(
                {
                    "group": playlist.name,
                    "channels": [
                        {
                            "name": playlist.name,
                            "url": playlist_live_m3u_url(playlist.id, public_base),
                        }
                    ],
                }
            )
        return groups

    async def build_tvbox_live_channels(
        self, public_base: str
    ) -> list[dict[str, str]]:
        channels: list[dict[str, str]] = []
        for group in await self.build_tvbox_live_groups(public_base):
            channels.extend(group.get("channels") or [])
        return channels

    async def list_media_files(
        self,
        public_base: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ):
        root = get_download_root()
        all_entries: list[PlaylistItemResponse] = []
        if root.exists():
            for path in sorted(root.rglob("*"), key=lambda p: p.name.lower()):
                if not path.is_file() or path.name.startswith("."):
                    continue
                if not is_media_path(path):
                    continue
                rel = path.relative_to(root).as_posix()
                all_entries.append(
                    PlaylistItemResponse(
                        id=0,
                        playlist_id=0,
                        rel_path=rel,
                        title=path.name,
                        name=path.name,
                        size=path.stat().st_size,
                        media_type=media_type_for_path(rel),
                        public_url=build_public_url(rel, public_base),
                        exists=True,
                    )
                )

        if page is not None:
            pg = normalize_page(page)
            ps = normalize_page_size(page_size or DEFAULT_PAGE_SIZE)
            total = len(all_entries)
            start = (pg - 1) * ps
            slice_entries = all_entries[start : start + ps]
            return PaginatedResponse.from_items(slice_entries, total, pg, ps)
        return all_entries


playlist_service = PlaylistService()
