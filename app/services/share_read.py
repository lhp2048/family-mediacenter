from datetime import date, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.db import async_session
from app.models.share_read import (
    ShareHotBook,
    ShareReadDayStat,
    ShareReadDeviceStat,
    ShareReadHourStat,
    ShareReadORM,
    ShareReadStatsResponse,
    ShareReadVisitORM,
)
from app.models.share_watch import ShareDeviceORM
from app.services import material_service
from app.services.material_service import _normalize_materials_subpath
from app.services.material_share import material_share_service
from app.services.share_watch import MAX_TICK_SEC, local_naive, retention_cutoff, share_watch

READ_VISIT_COOKIE = "fmc_read_visit"


class ShareReadService:
    async def open_read(
        self,
        token: str,
        relative_path: str,
        visitor_token: str,
        ip: str,
        user_agent: str,
    ) -> tuple[str, int]:
        await share_watch.prune_expired()
        share = await material_share_service.resolve_share(token)
        if not share.is_dir and _normalize_materials_subpath(relative_path):
            raise ValueError("路径超出分享范围")
        relative = relative_path if share.is_dir else ""
        file_path = material_share_service.share_file(share, relative)
        root = material_service.get_materials_root().resolve()
        library = file_path.resolve().relative_to(root).as_posix()
        now = local_naive()
        async with async_session() as session:
            device = await share_watch._ensure_device(
                session, visitor_token, ip, user_agent, now
            )
            if not device.allowed:
                await session.commit()
                raise PermissionError("这台设备未允许")
            visit = ShareReadVisitORM(
                device_id=device.id,
                token=token,
                book_path=library,
                title=file_path.name,
                started_at=now,
                last_seen_at=now,
                ip=(ip or "")[:64],
                user_agent=user_agent or "",
                device_label=device.device_label,
                opened=False,
            )
            session.add(visit)
            await session.commit()
            await session.refresh(visit)
            return device.visitor_token, visit.id

    async def prepare_access(
        self,
        token: str,
        visitor_token: str,
        ip: str,
        user_agent: str,
    ) -> tuple[str, bool]:
        await material_share_service.resolve_share(token)
        now = local_naive()
        async with async_session() as session:
            device = await share_watch._ensure_device(
                session, visitor_token, ip, user_agent, now
            )
            visitor = device.visitor_token
            allowed = bool(device.allowed)
            await session.commit()
        return visitor, allowed

    async def assert_allowed(self, visitor_token: str) -> None:
        async with async_session() as session:
            device = await share_watch._device_by_token(session, visitor_token)
            if device is None:
                raise PermissionError("未识别设备")
            if not device.allowed:
                raise PermissionError("这台设备未允许")

    async def record_event(
        self,
        token: str,
        visitor_token: str,
        visit_id: int,
        event_type: str,
        delta_sec: float = 0.0,
        at: datetime | None = None,
    ) -> dict:
        if event_type not in {"open", "tick"}:
            raise ValueError("事件类型无效")
        now = local_naive(at)
        if now.date() < retention_cutoff():
            return {"ok": True, "counted": False}
        await share_watch.prune_expired()
        await material_share_service.resolve_share(token)
        async with async_session() as session:
            device = await share_watch._device_by_token(session, visitor_token)
            if device is None:
                raise PermissionError("未识别设备")
            if not device.allowed:
                raise PermissionError("这台设备未允许")
            visit = await session.get(ShareReadVisitORM, visit_id)
            if visit is None or visit.device_id != device.id or visit.token != token:
                raise ValueError("访问记录无效")

            counted = True
            if event_type == "tick" and not (0 < delta_sec <= MAX_TICK_SEC):
                counted = False
            elif event_type == "open":
                bucket = await self._bucket(session, visit, device, now)
                marked = await session.execute(
                    update(ShareReadVisitORM)
                    .where(
                        ShareReadVisitORM.id == visit.id,
                        ShareReadVisitORM.opened.is_(False),
                    )
                    .values(opened=True, last_seen_at=now)
                )
                if marked.rowcount == 0:
                    counted = False
                else:
                    await self._add_bucket(
                        session,
                        bucket.id,
                        now,
                        open_count=1,
                    )
                    device.last_seen_at = now
            else:
                bucket = await self._bucket(session, visit, device, now)
                await self._add_bucket(session, bucket.id, now, read_sec=float(delta_sec))
                visit.last_seen_at = now
                device.last_seen_at = now
            await session.commit()
            return {"ok": True, "counted": counted}

    async def query_stats(self, start: date, end: date) -> ShareReadStatsResponse:
        await share_watch.prune_expired(force=True)
        start_key = start.isoformat()
        end_key = end.isoformat()
        async with async_session() as session:
            reads = (
                await session.execute(
                    select(ShareReadORM).where(
                        ShareReadORM.day >= start_key,
                        ShareReadORM.day <= end_key,
                    )
                )
            ).scalars().all()
            device_ids = {row.device_id for row in reads}
            if not device_ids:
                return ShareReadStatsResponse(from_date=start_key, to_date=end_key, devices=[])
            devices = (
                await session.execute(
                    select(ShareDeviceORM).where(ShareDeviceORM.id.in_(device_ids))
                )
            ).scalars().all()

        by_device_days: dict[int, dict[str, ShareReadDayStat]] = {}
        by_device_books: dict[int, dict[str, ShareHotBook]] = {}
        totals: dict[int, float] = {device.id: 0.0 for device in devices}

        for row in reads:
            day = by_device_days.setdefault(row.device_id, {}).get(row.day)
            if day is None:
                day = ShareReadDayStat(date=row.day)
                by_device_days[row.device_id][row.day] = day
            seconds = float(row.read_sec or 0)
            day.read_sec += seconds
            totals[row.device_id] = totals.get(row.device_id, 0.0) + seconds
            if row.first_read_at and (day.first_at is None or row.first_read_at < day.first_at):
                day.first_at = row.first_read_at
            if row.last_read_at and (day.last_at is None or row.last_read_at > day.last_at):
                day.last_at = row.last_read_at
            if seconds > 0:
                slot = next((hour for hour in day.hours if hour.hour == row.hour), None)
                if slot is None:
                    day.hours.append(ShareReadHourStat(hour=row.hour, read_sec=seconds))
                else:
                    slot.read_sec += seconds
            hot = by_device_books.setdefault(row.device_id, {}).get(row.book_path)
            if hot is None:
                hot = ShareHotBook(path=row.book_path or "", title=row.title or "")
                by_device_books[row.device_id][row.book_path] = hot
            hot.read_sec += seconds
            hot.open_count += int(row.open_count or 0)
            if row.title:
                hot.title = row.title

        stats: list[ShareReadDeviceStat] = []
        for device in devices:
            days = list(by_device_days.get(device.id, {}).values())
            for day in days:
                day.hours.sort(key=lambda hour: hour.hour)
                day.read_sec = round(day.read_sec, 3)
                for hour in day.hours:
                    hour.read_sec = round(hour.read_sec, 3)
            days.sort(key=lambda day: day.date)
            hot_books = [
                book
                for book in by_device_books.get(device.id, {}).values()
                if book.read_sec > 0 or book.open_count > 0
            ]
            hot_books.sort(key=lambda book: (-book.read_sec, -book.open_count, book.path))
            for book in hot_books:
                book.read_sec = round(book.read_sec, 3)
            stats.append(
                ShareReadDeviceStat(
                    id=device.id,
                    device_label=device.device_label,
                    last_ip=device.last_ip,
                    user_agent=device.user_agent,
                    allowed=bool(device.allowed),
                    read_sec=round(totals.get(device.id, 0.0), 3),
                    by_day=days,
                    hot_books=hot_books,
                )
            )
        stats.sort(key=lambda row: (-row.read_sec, row.id))
        return ShareReadStatsResponse(from_date=start_key, to_date=end_key, devices=stats)

    async def _bucket(
        self,
        session,
        visit: ShareReadVisitORM,
        device: ShareDeviceORM,
        now: datetime,
    ) -> ShareReadORM:
        day = now.date().isoformat()
        hour = now.hour
        result = await session.execute(
            select(ShareReadORM).where(
                ShareReadORM.visit_id == visit.id,
                ShareReadORM.day == day,
                ShareReadORM.hour == hour,
            )
        )
        bucket = result.scalar_one_or_none()
        if bucket is not None:
            return bucket
        bucket = ShareReadORM(
            visit_id=visit.id,
            device_id=device.id,
            token=visit.token,
            book_path=visit.book_path,
            title=visit.title,
            day=day,
            hour=hour,
            read_sec=0.0,
            open_count=0,
        )
        try:
            async with session.begin_nested():
                session.add(bucket)
                await session.flush()
        except IntegrityError:
            found = await session.execute(
                select(ShareReadORM).where(
                    ShareReadORM.visit_id == visit.id,
                    ShareReadORM.day == day,
                    ShareReadORM.hour == hour,
                )
            )
            bucket = found.scalar_one()
        return bucket

    async def _add_bucket(
        self,
        session,
        bucket_id: int,
        now: datetime,
        *,
        read_sec: float = 0.0,
        open_count: int = 0,
    ) -> None:
        await session.execute(
            update(ShareReadORM)
            .where(ShareReadORM.id == bucket_id)
            .values(
                read_sec=ShareReadORM.read_sec + read_sec,
                open_count=ShareReadORM.open_count + open_count,
                last_read_at=now,
                first_read_at=func.coalesce(ShareReadORM.first_read_at, now),
            )
        )


share_read = ShareReadService()
