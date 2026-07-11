import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import resolve_download_dir, settings
from app.db import async_session
from app.engines.alist import AlistEngine
from app.engines.aria2 import Aria2Engine
from app.engines.base import DownloadEngine, parse_options, serialize_options
from app.engines.ytdlp import YtDlpEngine
from app.models.pagination import (
    DEFAULT_PAGE_SIZE,
    PaginatedResponse,
    normalize_page,
    normalize_page_size,
)
from app.models.task import SourceType, TaskCreate, TaskORM, TaskResponse, TaskStatus
from app.services.engine_router import detect_engine
from app.utils.encoding import title_from_task_file
from app.utils.url_extract import extract_url_from_text
from app.utils.download_log import (
    download_log_exists,
    log_api_path,
    remove_download_log,
    write_download_log,
)


class TaskManager:
    def __init__(self) -> None:
        self._engines: dict[str, DownloadEngine] = {
            SourceType.YTDLP.value: YtDlpEngine(),
            SourceType.ARIA2.value: Aria2Engine(),
            SourceType.ALIST.value: AlistEngine(),
        }
        self._running_count = 0
        self._poll_task: Optional[asyncio.Task] = None
        self._queue_lock = asyncio.Lock()

    def get_engine(self, source_type: str) -> DownloadEngine:
        engine = self._engines.get(source_type)
        if not engine:
            raise ValueError(f"Unknown engine: {source_type}")
        return engine

    async def start_polling(self) -> None:
        if self._poll_task is None:
            self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop_polling(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

    async def recover_on_startup(self) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(TaskORM).where(
                    TaskORM.status.in_(
                        [TaskStatus.RUNNING.value, TaskStatus.PENDING.value]
                    )
                )
            )
            tasks = result.scalars().all()
            for task in tasks:
                task.status = TaskStatus.FAILED.value
                task.error_message = "Service restarted; task was interrupted"
                task.updated_at = datetime.utcnow()
            await session.commit()

    async def create_task(self, data: TaskCreate) -> TaskResponse:
        url = extract_url_from_text(data.url)
        source_type = detect_engine(url, data.engine)
        output_dir = resolve_download_dir(data.output_dir or settings.download.default_dir)

        async with async_session() as session:
            task = TaskORM(
                url=url,
                source_type=source_type,
                status=TaskStatus.PENDING.value,
                options_json=serialize_options(data.options),
                output_dir=output_dir,
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            task_id = task.id

        await self._try_start_pending()
        return await self.get_task(task_id)

    async def _try_start_pending(self) -> None:
        async with self._queue_lock:
            async with async_session() as session:
                running = await session.execute(
                    select(TaskORM).where(TaskORM.status == TaskStatus.RUNNING.value)
                )
                self._running_count = len(running.scalars().all())
                max_concurrent = settings.download.max_concurrent

                if self._running_count >= max_concurrent:
                    return

                result = await session.execute(
                    select(TaskORM)
                    .where(TaskORM.status == TaskStatus.PENDING.value)
                    .order_by(TaskORM.created_at)
                    .limit(max_concurrent - self._running_count)
                )
                pending = result.scalars().all()

                for task in pending:
                    await self._start_task(session, task)

                await session.commit()

    async def _start_task(self, session: AsyncSession, task: TaskORM) -> None:
        engine = self.get_engine(task.source_type)
        options = parse_options(task.options_json)
        try:
            if not await engine.is_available():
                task.status = TaskStatus.FAILED.value
                msg = f"Engine {task.source_type} is not available"
                task.error_message = f"{msg}（完整日志: {log_api_path(task.id)}）"
                task.updated_at = datetime.utcnow()
                write_download_log(
                    task.id,
                    [msg],
                    engine=task.source_type,
                    url=task.url,
                )
                return
            engine_task_id = await engine.start(
                task.id, task.url, task.output_dir, options
            )
            task.engine_task_id = engine_task_id
            task.status = TaskStatus.RUNNING.value
            self._running_count += 1
        except Exception as e:
            task.status = TaskStatus.FAILED.value
            msg = str(e) or f"Engine {task.source_type} start failed"
            task.error_message = f"{msg}（完整日志: {log_api_path(task.id)}）"
            task.updated_at = datetime.utcnow()
            write_download_log(
                task.id,
                [msg],
                engine=task.source_type,
                url=task.url,
            )

    async def get_task(self, task_id: int) -> TaskResponse:
        async with async_session() as session:
            task = await session.get(TaskORM, task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            return self._to_response(task)

    async def list_tasks(
        self,
        status: Optional[str] = None,
        tab: Optional[str] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> list[TaskResponse] | PaginatedResponse[TaskResponse]:
        if page is not None:
            return await self.list_tasks_paginated(
                status=status,
                tab=tab,
                page=page,
                page_size=page_size or DEFAULT_PAGE_SIZE,
            )
        statuses = self._tab_to_statuses(tab)
        async with async_session() as session:
            q = select(TaskORM).order_by(TaskORM.created_at.desc())
            if status:
                q = q.where(TaskORM.status == status)
            elif statuses:
                q = q.where(TaskORM.status.in_(statuses))
            result = await session.execute(q)
            return [self._to_response(t) for t in result.scalars().all()]

    def _task_filters(self, status: Optional[str], tab: Optional[str]):
        statuses = self._tab_to_statuses(tab)
        filters = []
        if status:
            filters.append(TaskORM.status == status)
        elif statuses:
            filters.append(TaskORM.status.in_(statuses))
        return filters

    async def list_tasks_paginated(
        self,
        status: Optional[str] = None,
        tab: Optional[str] = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> PaginatedResponse[TaskResponse]:
        page = normalize_page(page)
        page_size = normalize_page_size(page_size)
        filters = self._task_filters(status, tab)
        async with async_session() as session:
            count_q = select(func.count(TaskORM.id))
            for f in filters:
                count_q = count_q.where(f)
            total = int((await session.execute(count_q)).scalar() or 0)

            q = select(TaskORM).order_by(TaskORM.created_at.desc())
            for f in filters:
                q = q.where(f)
            q = q.offset((page - 1) * page_size).limit(page_size)
            result = await session.execute(q)
            items = [self._to_response(t) for t in result.scalars().all()]
        return PaginatedResponse.from_items(items, total, page, page_size)

    def _tab_to_statuses(self, tab: Optional[str]) -> Optional[list[str]]:
        if not tab or tab == "all":
            return None
        mapping = {
            "active": [
                TaskStatus.PENDING.value,
                TaskStatus.RUNNING.value,
                TaskStatus.PAUSED.value,
            ],
            "completed": [TaskStatus.COMPLETED.value],
            "failed": [
                TaskStatus.FAILED.value,
                TaskStatus.CANCELLED.value,
            ],
        }
        return mapping.get(tab)

    async def get_task_counts(self) -> dict[str, int]:
        async with async_session() as session:
            result = await session.execute(
                select(TaskORM.status, func.count(TaskORM.id)).group_by(TaskORM.status)
            )
            by_status = {row[0]: row[1] for row in result.all()}
        active = sum(
            by_status.get(s, 0)
            for s in (
                TaskStatus.PENDING.value,
                TaskStatus.RUNNING.value,
                TaskStatus.PAUSED.value,
            )
        )
        completed = by_status.get(TaskStatus.COMPLETED.value, 0)
        failed = sum(
            by_status.get(s, 0)
            for s in (TaskStatus.FAILED.value, TaskStatus.CANCELLED.value)
        )
        total = sum(by_status.values())
        return {
            "active": active,
            "completed": completed,
            "failed": failed,
            "all": total,
        }

    async def delete_task(self, task_id: int, delete_file: bool = False) -> None:
        async with async_session() as session:
            task = await session.get(TaskORM, task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            if task.status in (
                TaskStatus.RUNNING.value,
                TaskStatus.PENDING.value,
            ):
                raise ValueError("无法删除进行中的任务，请先取消")
            file_path = task.file_path
            await session.delete(task)
            await session.commit()

        if delete_file and file_path:
            path = Path(file_path)
            if path.exists() and path.is_file():
                try:
                    os.remove(path)
                except OSError as e:
                    raise ValueError(f"任务已删除，但文件删除失败: {e}") from e

        remove_download_log(task_id)

    async def pause_task(self, task_id: int) -> TaskResponse:
        async with async_session() as session:
            task = await session.get(TaskORM, task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            engine = self.get_engine(task.source_type)
            ok = await engine.pause(task.engine_task_id, task.id)
            if ok:
                task.status = TaskStatus.PAUSED.value
                task.updated_at = datetime.utcnow()
                await session.commit()
            return self._to_response(task)

    async def cancel_task(self, task_id: int) -> TaskResponse:
        async with async_session() as session:
            task = await session.get(TaskORM, task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            engine = self.get_engine(task.source_type)
            await engine.cancel(task.engine_task_id, task.id)
            task.status = TaskStatus.CANCELLED.value
            task.updated_at = datetime.utcnow()
            await session.commit()
            await self._try_start_pending()
            return self._to_response(task)

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_running_tasks()
                await self._try_start_pending()
            except Exception:
                pass
            await asyncio.sleep(2)

    async def _poll_running_tasks(self) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(TaskORM).where(TaskORM.status == TaskStatus.RUNNING.value)
            )
            tasks = result.scalars().all()
            for task in tasks:
                engine = self.get_engine(task.source_type)
                prog = await engine.poll(task.engine_task_id, task.id)
                if prog.progress:
                    task.progress = prog.progress
                if prog.speed:
                    task.speed = prog.speed
                if prog.file_path:
                    task.file_path = prog.file_path
                if prog.file_size:
                    task.file_size = prog.file_size
                if prog.title:
                    task.title = prog.title
                if prog.status:
                    was_completed = task.status == TaskStatus.COMPLETED.value
                    previous_status = task.status
                    task.status = prog.status
                    if prog.status in (
                        TaskStatus.COMPLETED.value,
                        TaskStatus.FAILED.value,
                        TaskStatus.CANCELLED.value,
                        TaskStatus.PAUSED.value,
                    ):
                        self._running_count = max(0, self._running_count - 1)
                    if (
                        prog.status == TaskStatus.FAILED.value
                        and previous_status != TaskStatus.FAILED.value
                        and not download_log_exists(task.id)
                        and prog.error_message
                    ):
                        write_download_log(
                            task.id,
                            [prog.error_message],
                            engine=task.source_type,
                            url=task.url,
                        )
                    if (
                        prog.status == TaskStatus.COMPLETED.value
                        and not was_completed
                    ):
                        from app.services.playlist_service import playlist_service

                        await playlist_service.on_task_completed(task)
                if prog.error_message:
                    msg = prog.error_message
                    if (
                        prog.status == TaskStatus.FAILED.value
                        and log_api_path(task.id) not in msg
                    ):
                        msg = f"{msg}（完整日志: {log_api_path(task.id)}）"
                    task.error_message = msg
                task.updated_at = datetime.utcnow()
            await session.commit()

    def _resolve_task_file(self, task: TaskORM) -> str:
        if task.file_path and Path(task.file_path).exists():
            return task.file_path
        if task.output_dir:
            base = Path(task.output_dir)
            candidates = list(base.glob(f"task_{task.id}_*"))
            if candidates:
                latest = max(candidates, key=lambda p: p.stat().st_mtime)
                return str(latest)
        return task.file_path or ""

    def _to_response(self, task: TaskORM) -> TaskResponse:
        file_path = self._resolve_task_file(task)
        title = task.title
        if file_path and Path(file_path).exists():
            title = title_from_task_file(file_path, task.id)
        return TaskResponse(
            id=task.id,
            url=task.url,
            title=title,
            source_type=task.source_type,
            status=task.status,
            progress=task.progress,
            speed=task.speed,
            file_path=file_path,
            file_size=task.file_size,
            engine_task_id=task.engine_task_id,
            options=parse_options(task.options_json),
            output_dir=task.output_dir,
            error_message=task.error_message,
            log_available=download_log_exists(task.id),
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


task_manager = TaskManager()
