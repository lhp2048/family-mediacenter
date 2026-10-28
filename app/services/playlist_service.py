import asyncio
import os
import stat as stat_mode
from pathlib import Path
from typing import Any, Optional
import secrets
from datetime import datetime, timezone

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
    PlaylistRenameReplaceItem,
    PlaylistRenameReplaceResult,
    PlaylistResponse,
    PlaylistShareResponse,
    WatchItemResponse,
    WatchPlaylistResponse,
    WatchProgress,
)
from app.models.task import TaskORM, TaskStatus
from app.services.file_manager import build_public_url, get_download_root, to_storage_rel
from app.services.playlist_m3u import playlist_live_m3u_url, render_live_m3u
from app.utils.encoding import title_from_task_file
from app.utils.media import (
    is_media_path,
    media_display_name,
    media_type_for_path,
    resolve_media_rel_path,
    to_rel_path,
)

def _scan_media_names(root: Path, probe: bool) -> list[tuple[str, str, int]]:
    """Walk download media names. Stat file size only when probe is set."""
    found: list[tuple[str, str, int]] = []
    if not root.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            if not is_media_path(rel):
                continue
            size = 0
            if probe:
                try:
                    st = full.stat()
                except OSError:
                    continue
                if not stat_mode.S_ISREG(st.st_mode):
                    continue
                size = int(st.st_size)
            found.append((rel, name, size))
    found.sort(key=lambda row: row[1].lower())
    return found


class PlaylistService:
    def _item_to_response(
        self, item: PlaylistItemORM, public_base: str, *, probe: bool = True
    ) -> PlaylistItemResponse:
        rel = item.rel_path
        name = media_display_name(rel, item.title)
        public_url = build_public_url(to_storage_rel(rel), public_base)
        if not probe:
            return PlaylistItemResponse(
                id=item.id,
                playlist_id=item.playlist_id,
                rel_path=rel,
                title=item.title or name,
                name=name,
                size=0,
                media_type=media_type_for_path(rel),
                task_id=item.task_id,
                sort_order=item.sort_order,
                public_url=public_url,
                exists=True,
                info_ready=False,
                added_at=item.added_at,
            )
        path = resolve_media_rel_path(rel)
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
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
            public_url=public_url if exists else "",
            exists=exists,
            info_ready=True,
            added_at=item.added_at,
        )

    def _share_url(self, token: Optional[str], enabled: bool, public_base: str) -> str:
        if not enabled or not token or not public_base:
            return ""
        return f"{public_base.rstrip('/')}/watch/{token}"

    def _playlist_to_response(
        self,
        playlist: PlaylistORM,
        item_count: Optional[int] = None,
        public_base: str = "",
    ) -> PlaylistResponse:
        count = item_count if item_count is not None else len(playlist.items)
        token = playlist.share_token or ""
        enabled = bool(playlist.share_enabled)
        return PlaylistResponse(
            id=playlist.id,
            name=playlist.name,
            is_default=playlist.is_default,
            item_count=count,
            created_at=playlist.created_at,
            share_enabled=enabled,
            share_token=token if enabled else "",
            share_url=self._share_url(token, enabled, public_base),
            share_autoplay=bool(playlist.share_autoplay),
            share_last_item_id=playlist.share_last_item_id,
            share_position_sec=float(playlist.share_position_sec or 0),
            share_updated_at=playlist.share_updated_at,
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

    async def list_playlists(self, public_base: str = "") -> list[PlaylistResponse]:
        async with async_session() as session:
            result = await session.execute(
                select(PlaylistORM, func.count(PlaylistItemORM.id))
                .outerjoin(PlaylistItemORM, PlaylistORM.id == PlaylistItemORM.playlist_id)
                .group_by(PlaylistORM.id)
                .order_by(PlaylistORM.is_default.desc(), PlaylistORM.id)
            )
            rows = result.all()
            return [
                self._playlist_to_response(row[0], row[1], public_base) for row in rows
            ]

    async def get_playlist(
        self, playlist_id: int, public_base: str = ""
    ) -> Optional[PlaylistResponse]:
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
            return self._playlist_to_response(row[0], row[1], public_base)

    async def get_default_playlist(self, public_base: str = "") -> PlaylistResponse:
        default = await self.ensure_default_playlist()
        playlist = await self.get_playlist(default.id, public_base)
        return playlist or self._playlist_to_response(default, 0, public_base)

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
        probe: bool = True,
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
                responses = [
                    self._item_to_response(item, public_base, probe=probe) for item in items
                ]
                return PaginatedResponse.from_items(responses, total, pg, ps)

            result = await session.execute(
                select(PlaylistItemORM)
                .where(PlaylistItemORM.playlist_id == playlist_id)
                .order_by(PlaylistItemORM.sort_order, PlaylistItemORM.id)
            )
            items = result.scalars().all()
            return [self._item_to_response(item, public_base, probe=probe) for item in items]

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

    async def remove_items(self, playlist_id: int, item_ids: list[int]) -> int:
        ids = [int(i) for i in item_ids if i is not None]
        if not ids:
            raise ValueError("请选择要移除的条目")
        async with async_session() as session:
            playlist = await session.get(PlaylistORM, playlist_id)
            if not playlist:
                raise ValueError("播放列表不存在")
            result = await session.execute(
                select(PlaylistItemORM).where(
                    PlaylistItemORM.playlist_id == playlist_id,
                    PlaylistItemORM.id.in_(ids),
                )
            )
            rows = result.scalars().all()
            for item in rows:
                await session.delete(item)
            await session.commit()
            return len(rows)

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        bad = '<>:"/\\|?*'
        out = "".join("_" if ch in bad else ch for ch in name)
        out = out.strip(" .")
        return out

    async def rename_replace_in_playlist(
        self,
        playlist_id: int,
        find: str,
        replace: str = "",
        *,
        dry_run: bool = False,
    ) -> PlaylistRenameReplaceResult:
        """Replace substring in basenames on disk; update all playlist refs to old path."""
        find = find or ""
        if not find:
            raise ValueError("查找字符串不能为空")
        replace = replace if replace is not None else ""

        result = PlaylistRenameReplaceResult(
            ok=True, dry_run=dry_run, find=find, replace=replace
        )

        async with async_session() as session:
            playlist = await session.get(PlaylistORM, playlist_id)
            if not playlist:
                raise ValueError("播放列表不存在")
            rows = (
                await session.execute(
                    select(PlaylistItemORM)
                    .where(PlaylistItemORM.playlist_id == playlist_id)
                    .order_by(PlaylistItemORM.sort_order, PlaylistItemORM.id)
                )
            ).scalars().all()

            # Deduplicate by rel_path (rename each file once)
            seen: set[str] = set()
            plans: list[tuple[str, str, str, str]] = []  # old_rel, new_rel, old_name, new_name

            for item in rows:
                old_rel = item.rel_path
                if not old_rel or old_rel in seen:
                    continue
                seen.add(old_rel)
                old_name = Path(old_rel).name
                if find not in old_name:
                    result.skipped.append(f"未匹配: {old_name}")
                    continue
                new_name = self._sanitize_filename(old_name.replace(find, replace))
                if not new_name:
                    result.errors.append(f"替换后文件名为空: {old_name}")
                    continue
                if new_name == old_name:
                    result.skipped.append(f"无变化: {old_name}")
                    continue
                if not is_media_path(new_name):
                    result.errors.append(f"替换后不是媒体扩展名: {new_name}")
                    continue
                parent = Path(old_rel).parent
                new_rel = (
                    new_name if str(parent) in (".", "") else f"{parent.as_posix()}/{new_name}"
                )
                plans.append((old_rel, new_rel, old_name, new_name))

            for old_rel, new_rel, old_name, new_name in plans:
                try:
                    src = resolve_media_rel_path(old_rel)
                    dst = resolve_media_rel_path(new_rel)
                except ValueError as e:
                    result.errors.append(f"{old_name}: {e}")
                    continue

                if not src.is_file():
                    result.errors.append(f"文件不存在: {old_rel}")
                    continue
                if dst.exists() and src.resolve() != dst.resolve():
                    result.errors.append(f"目标已存在: {new_rel}")
                    continue

                if dry_run:
                    # count refs that would update
                    cnt = (
                        await session.execute(
                            select(func.count())
                            .select_from(PlaylistItemORM)
                            .where(PlaylistItemORM.rel_path == old_rel)
                        )
                    ).scalar() or 0
                    result.renamed.append(
                        PlaylistRenameReplaceItem(
                            old_rel_path=old_rel,
                            new_rel_path=new_rel,
                            old_name=old_name,
                            new_name=new_name,
                            refs_updated=int(cnt),
                        )
                    )
                    continue

                try:
                    src.rename(dst)
                except OSError as e:
                    result.errors.append(f"重命名失败 {old_name} → {new_name}: {e}")
                    continue

                # Update all playlist items referencing old path
                items = (
                    await session.execute(
                        select(PlaylistItemORM).where(PlaylistItemORM.rel_path == old_rel)
                    )
                ).scalars().all()
                refs = 0
                for row in items:
                    row.rel_path = new_rel
                    title = row.title or ""
                    if find in title:
                        row.title = title.replace(find, replace)
                    elif title == old_name or not title:
                        row.title = new_name
                    refs += 1
                result.renamed.append(
                    PlaylistRenameReplaceItem(
                        old_rel_path=old_rel,
                        new_rel_path=new_rel,
                        old_name=old_name,
                        new_name=new_name,
                        refs_updated=refs,
                    )
                )

            if not dry_run and result.renamed:
                await session.commit()

        n = len(result.renamed)
        err_n = len(result.errors)
        if dry_run:
            result.message = f"预览：将重命名 {n} 个文件"
        elif n and not err_n:
            result.message = f"已重命名 {n} 个文件"
        elif n and err_n:
            result.message = f"已重命名 {n} 个，另有 {err_n} 个失败"
            result.ok = False
        elif err_n:
            result.message = f"重命名失败（{err_n}）"
            result.ok = False
        else:
            result.message = "没有需要重命名的文件"
        return result

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

    async def count_items_by_rel_path(self, rel_path: str) -> int:
        if not rel_path:
            return 0
        async with async_session() as session:
            cnt = (
                await session.execute(
                    select(func.count())
                    .select_from(PlaylistItemORM)
                    .where(PlaylistItemORM.rel_path == rel_path)
                )
            ).scalar() or 0
            return int(cnt)

    async def remap_rel_path(
        self,
        old_rel: str,
        new_rel: str,
        *,
        find: str = "",
        replace: str = "",
        old_name: str = "",
        new_name: str = "",
    ) -> int:
        """Update all playlist items pointing at old_rel → new_rel."""
        if not old_rel or not new_rel or old_rel == new_rel:
            return 0
        async with async_session() as session:
            items = (
                await session.execute(
                    select(PlaylistItemORM).where(PlaylistItemORM.rel_path == old_rel)
                )
            ).scalars().all()
            refs = 0
            for row in items:
                row.rel_path = new_rel
                title = row.title or ""
                if find and find in title:
                    row.title = title.replace(find, replace)
                elif title == old_name or not title:
                    row.title = new_name or Path(new_rel).name
                refs += 1
            if refs:
                await session.commit()
            return refs

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
        probe: bool = True,
    ):
        root = get_download_root()
        found = await asyncio.to_thread(_scan_media_names, root, probe)
        all_entries: list[PlaylistItemResponse] = []
        for rel, name, size in found:
            all_entries.append(
                PlaylistItemResponse(
                    id=0,
                    playlist_id=0,
                    rel_path=rel,
                    title=name,
                    name=name,
                    size=size,
                    media_type=media_type_for_path(rel),
                    public_url=build_public_url(to_storage_rel(rel), public_base),
                    exists=True,
                    info_ready=probe,
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

    async def enable_share(
        self, playlist_id: int, public_base: str
    ) -> PlaylistShareResponse:
        async with async_session() as session:
            playlist = await session.get(PlaylistORM, playlist_id)
            if not playlist:
                raise ValueError("播放列表不存在")
            if not playlist.share_token:
                playlist.share_token = secrets.token_urlsafe(16)
            playlist.share_enabled = True
            await session.commit()
            await session.refresh(playlist)
            token = playlist.share_token or ""
            return PlaylistShareResponse(
                share_enabled=True,
                share_token=token,
                share_url=self._share_url(token, True, public_base),
                share_autoplay=bool(playlist.share_autoplay),
            )

    async def disable_share(self, playlist_id: int) -> PlaylistShareResponse:
        async with async_session() as session:
            playlist = await session.get(PlaylistORM, playlist_id)
            if not playlist:
                raise ValueError("播放列表不存在")
            playlist.share_enabled = False
            await session.commit()
            await session.refresh(playlist)
            return PlaylistShareResponse(
                share_enabled=False,
                share_token="",
                share_url="",
                share_autoplay=bool(playlist.share_autoplay),
            )

    async def rotate_share(
        self, playlist_id: int, public_base: str
    ) -> PlaylistShareResponse:
        async with async_session() as session:
            playlist = await session.get(PlaylistORM, playlist_id)
            if not playlist:
                raise ValueError("播放列表不存在")
            playlist.share_token = secrets.token_urlsafe(16)
            playlist.share_enabled = True
            await session.commit()
            await session.refresh(playlist)
            token = playlist.share_token or ""
            return PlaylistShareResponse(
                share_enabled=True,
                share_token=token,
                share_url=self._share_url(token, True, public_base),
                share_autoplay=bool(playlist.share_autoplay),
            )

    async def clear_share_progress(self, playlist_id: int) -> PlaylistResponse:
        async with async_session() as session:
            playlist = await session.get(PlaylistORM, playlist_id)
            if not playlist:
                raise ValueError("播放列表不存在")
            playlist.share_last_item_id = None
            playlist.share_position_sec = 0.0
            playlist.share_updated_at = None
            await session.commit()
        return await self.get_playlist(playlist_id) or PlaylistResponse(
            id=playlist_id, name="", item_count=0
        )

    async def set_share_autoplay(
        self, playlist_id: int, autoplay: bool, public_base: str = ""
    ) -> PlaylistResponse:
        async with async_session() as session:
            playlist = await session.get(PlaylistORM, playlist_id)
            if not playlist:
                raise ValueError("播放列表不存在")
            playlist.share_autoplay = bool(autoplay)
            await session.commit()
        result = await self.get_playlist(playlist_id, public_base)
        if not result:
            raise ValueError("播放列表不存在")
        return result

    async def reorder_items(
        self,
        playlist_id: int,
        items: list[tuple[int, int]],
        public_base: str = "",
    ) -> list[PlaylistItemResponse]:
        async with async_session() as session:
            playlist = await session.get(PlaylistORM, playlist_id)
            if not playlist:
                raise ValueError("播放列表不存在")
            for item_id, sort_order in items:
                row = await session.get(PlaylistItemORM, item_id)
                if not row or row.playlist_id != playlist_id:
                    raise ValueError(f"条目不存在: {item_id}")
                row.sort_order = sort_order
            await session.commit()
        result = await self.list_items(playlist_id, public_base, probe=False)
        if isinstance(result, list):
            return result
        return result.items
    async def get_watch_payload(
        self, token: str, public_base: str
    ) -> WatchPlaylistResponse:
        async with async_session() as session:
            result = await session.execute(
                select(PlaylistORM).where(
                    PlaylistORM.share_token == token,
                    PlaylistORM.share_enabled.is_(True),
                )
            )
            playlist = result.scalar_one_or_none()
            if not playlist:
                raise ValueError("分享不存在或已停用")

            item_result = await session.execute(
                select(PlaylistItemORM)
                .where(PlaylistItemORM.playlist_id == playlist.id)
                .order_by(PlaylistItemORM.sort_order, PlaylistItemORM.id)
            )
            rows = item_result.scalars().all()

            watch_items: list[WatchItemResponse] = []
            for item in rows:
                resp = self._item_to_response(item, public_base)
                if not resp.exists or not resp.public_url:
                    continue
                watch_items.append(
                    WatchItemResponse(
                        id=resp.id,
                        title=resp.title or resp.name,
                        media_type=resp.media_type,
                        public_url=resp.public_url,
                        sort_order=resp.sort_order,
                    )
                )

            progress = None
            if playlist.share_last_item_id is not None:
                valid_ids = {w.id for w in watch_items}
                if playlist.share_last_item_id in valid_ids:
                    progress = WatchProgress(
                        item_id=playlist.share_last_item_id,
                        position_sec=float(playlist.share_position_sec or 0),
                        updated_at=playlist.share_updated_at,
                    )

            return WatchPlaylistResponse(
                name=playlist.name,
                autoplay=bool(playlist.share_autoplay),
                items=watch_items,
                progress=progress,
            )

    async def update_watch_progress(
        self, token: str, item_id: int, position_sec: float
    ) -> WatchProgress:
        async with async_session() as session:
            result = await session.execute(
                select(PlaylistORM).where(
                    PlaylistORM.share_token == token,
                    PlaylistORM.share_enabled.is_(True),
                )
            )
            playlist = result.scalar_one_or_none()
            if not playlist:
                raise ValueError("分享不存在或已停用")
            item = await session.get(PlaylistItemORM, item_id)
            if not item or item.playlist_id != playlist.id:
                raise ValueError("条目不属于该播放列表")
            playlist.share_last_item_id = item_id
            playlist.share_position_sec = max(0.0, float(position_sec))
            playlist.share_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.commit()
            await session.refresh(playlist)
            return WatchProgress(
                item_id=item_id,
                position_sec=float(playlist.share_position_sec or 0),
                updated_at=playlist.share_updated_at,
            )

    async def update_watch_autoplay(self, token: str, autoplay: bool) -> bool:
        async with async_session() as session:
            result = await session.execute(
                select(PlaylistORM).where(
                    PlaylistORM.share_token == token,
                    PlaylistORM.share_enabled.is_(True),
                )
            )
            playlist = result.scalar_one_or_none()
            if not playlist:
                raise ValueError("分享不存在或已停用")
            playlist.share_autoplay = bool(autoplay)
            await session.commit()
            return bool(playlist.share_autoplay)

    async def get_share_playlist_name(self, token: str) -> Optional[str]:
        async with async_session() as session:
            result = await session.execute(
                select(PlaylistORM).where(
                    PlaylistORM.share_token == token,
                    PlaylistORM.share_enabled.is_(True),
                )
            )
            playlist = result.scalar_one_or_none()
            return playlist.name if playlist else None


playlist_service = PlaylistService()
