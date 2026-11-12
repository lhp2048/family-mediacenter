import calendar
import secrets
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.models.playlist import (
    PlaylistItemORM,
    PlaylistORM,
    WatchEyeCare,
    WatchPlaylistResponse,
)
from app.models.share_read import ShareReadORM, ShareReadVisitORM
from app.models.share_watch import (
    ShareDayStat,
    ShareDeviceORM,
    ShareDeviceResponse,
    ShareDeviceStat,
    ShareEyeCareORM,
    ShareEyeCareResponse,
    ShareHotItem,
    ShareHourStat,
    SharePlaybackORM,
    ShareStatsResponse,
    ShareVisitORM,
)
from app.services.file_manager import get_file_for_serve, to_storage_rel
from app.services.playlist_service import playlist_service

VISITOR_COOKIE = "fmc_visitor"
VISIT_COOKIE = "fmc_visit"
MAX_TICK_SEC = 15.0
PRUNE_INTERVAL = timedelta(hours=6)


def device_label(user_agent: str) -> str:
    ua = user_agent or ""
    if "iPad" in ua:
        device = "iPad"
    elif "iPhone" in ua:
        device = "iPhone"
    elif "Android" in ua:
        device = "Android"
    elif "Windows" in ua:
        device = "Windows"
    elif "Macintosh" in ua or "Mac OS X" in ua:
        device = "Mac"
    elif "Linux" in ua:
        device = "Linux"
    else:
        device = "未知设备"

    if "Edg/" in ua:
        browser = "Edge"
    elif "Chrome/" in ua:
        browser = "Chrome"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = ""
    if browser:
        return f"{device} · {browser}"
    return device


def local_naive(at: datetime | None = None) -> datetime:
    if at is None:
        current = datetime.now().astimezone()
    elif at.tzinfo is None:
        return at
    else:
        current = at.astimezone()
    return current.replace(tzinfo=None)


def retention_cutoff(today: date | None = None) -> date:
    """Earliest local date still kept. Same day last month, clamped to that month."""
    current = today or local_naive().date()
    month = current.month - 1
    year = current.year
    if month < 1:
        month = 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(current.day, last_day))


def parse_stats_range(from_date: str | None, to_date: str | None) -> tuple[date, date]:
    today = local_naive().date()
    try:
        start = date.fromisoformat(from_date) if from_date else today - timedelta(days=6)
        end = date.fromisoformat(to_date) if to_date else today
    except ValueError as exc:
        raise ValueError("日期无效") from exc
    if start > end:
        raise ValueError("日期范围无效")
    return start, end


class ShareWatchService:
    def __init__(self) -> None:
        self._pruned_at: datetime | None = None

    async def prune_expired(self, *, force: bool = False) -> None:
        now = local_naive()
        if (
            not force
            and self._pruned_at is not None
            and now - self._pruned_at < PRUNE_INTERVAL
        ):
            return
        cutoff = retention_cutoff(now.date())
        cutoff_at = datetime.combine(cutoff, time.min)
        async with async_session() as session:
            await session.execute(
                delete(SharePlaybackORM).where(SharePlaybackORM.day < cutoff.isoformat())
            )
            await session.execute(
                delete(ShareVisitORM).where(ShareVisitORM.started_at < cutoff_at)
            )
            await session.execute(
                delete(ShareReadORM).where(ShareReadORM.day < cutoff.isoformat())
            )
            await session.execute(
                delete(ShareReadVisitORM).where(ShareReadVisitORM.started_at < cutoff_at)
            )
            await session.commit()
        self._pruned_at = now

    async def open_visit(
        self, token: str, visitor_token: str, ip: str, user_agent: str
    ) -> tuple[str, int]:
        await self.prune_expired()
        now = local_naive()
        async with async_session() as session:
            playlist = await self._playlist(session, token)
            device = await self._ensure_device(session, visitor_token, ip, user_agent, now)
            visit = ShareVisitORM(
                device_id=device.id,
                playlist_id=playlist.id,
                started_at=now,
                last_seen_at=now,
                ip=(ip or "")[:64],
                user_agent=user_agent or "",
                device_label=device.device_label,
            )
            session.add(visit)
            await session.commit()
            await session.refresh(visit)
            return device.visitor_token, visit.id

    async def eye_status(self, device_id: int, now: datetime | None = None) -> WatchEyeCare:
        current = now or local_naive()
        async with async_session() as session:
            device = await session.get(ShareDeviceORM, device_id)
            policy = await self._policy(session)
            if device is None:
                return self._eye_view(policy, None, current)
            self._eye_locked(policy, device, current)
            view = self._eye_view(policy, device, current)
            await session.commit()
            return view

    async def get_eye_care(self) -> ShareEyeCareResponse:
        async with async_session() as session:
            policy = await self._policy(session)
            await session.commit()
            return ShareEyeCareResponse(
                enabled=bool(policy.enabled),
                play_minutes=int(policy.play_minutes),
                rest_minutes=int(policy.rest_minutes),
            )

    async def set_eye_care(self, enabled: bool, play_minutes: int, rest_minutes: int) -> ShareEyeCareResponse:
        async with async_session() as session:
            policy = await self._policy(session)
            policy.enabled = bool(enabled)
            policy.play_minutes = max(1, min(240, int(play_minutes)))
            policy.rest_minutes = max(1, min(180, int(rest_minutes)))
            await session.commit()
            return ShareEyeCareResponse(
                enabled=bool(policy.enabled),
                play_minutes=int(policy.play_minutes),
                rest_minutes=int(policy.rest_minutes),
            )

    async def _policy(self, session: AsyncSession) -> ShareEyeCareORM:
        policy = await session.get(ShareEyeCareORM, 1)
        if policy is None:
            policy = ShareEyeCareORM(id=1, enabled=True, play_minutes=30, rest_minutes=15)
            session.add(policy)
            await session.flush()
        return policy

    def _eye_view(self, policy: ShareEyeCareORM, device: ShareDeviceORM | None, now: datetime) -> WatchEyeCare:
        if not policy.enabled or device is None:
            return WatchEyeCare(
                enabled=bool(policy.enabled),
                locked=False,
                play_minutes=int(policy.play_minutes),
                rest_minutes=int(policy.rest_minutes),
                watched_sec=0,
            )
        locked = bool(device.eye_locked_until and device.eye_locked_until > now)
        return WatchEyeCare(
            enabled=True,
            locked=locked,
            rest_remaining_sec=self._eye_remaining(device, now) if locked else 0,
            play_minutes=int(policy.play_minutes),
            rest_minutes=int(policy.rest_minutes),
            watched_sec=0 if locked else int(device.eye_watched_sec or 0),
        )

    def _eye_remaining(self, device: ShareDeviceORM, now: datetime) -> int:
        if not device.eye_locked_until or device.eye_locked_until <= now:
            return 0
        return max(1, int((device.eye_locked_until - now).total_seconds()))

    def _eye_locked(self, policy: ShareEyeCareORM, device: ShareDeviceORM, now: datetime) -> bool:
        """Refresh rest state. A pause at least as long as the rest clears the streak."""
        if not policy.enabled:
            return False
        locked_until = device.eye_locked_until
        if locked_until and locked_until > now:
            return True
        if locked_until and locked_until <= now:
            device.eye_locked_until = None
            device.eye_watched_sec = 0.0
            device.eye_last_play_at = None
            return False
        last = device.eye_last_play_at
        rest_sec = int(policy.rest_minutes or 15) * 60
        if last is not None and (now - last).total_seconds() >= rest_sec:
            device.eye_watched_sec = 0.0
        return False

    def _add_eye_play(self, policy: ShareEyeCareORM, device: ShareDeviceORM, now: datetime, delta: float) -> None:
        if not policy.enabled or delta <= 0:
            return
        self._eye_locked(policy, device, now)
        if device.eye_locked_until and device.eye_locked_until > now:
            return
        device.eye_watched_sec = float(device.eye_watched_sec or 0) + float(delta)
        device.eye_last_play_at = now
        limit = int(policy.play_minutes or 30) * 60
        if device.eye_watched_sec >= limit:
            device.eye_locked_until = now + timedelta(minutes=int(policy.rest_minutes or 15))
            device.eye_watched_sec = 0.0

    async def prepare_watch(
        self, token: str, visitor_token: str, ip: str, user_agent: str, public_base: str
    ) -> tuple[WatchPlaylistResponse, str]:
        now = local_naive()
        async with async_session() as session:
            playlist = await self._playlist(session, token)
            device = await self._ensure_device(session, visitor_token, ip, user_agent, now)
            allowed = bool(device.allowed)
            visitor = device.visitor_token
            hide_completed = bool(playlist.share_hide_completed)
            hide_after = int(playlist.share_hide_after or 1)
            if hide_after < 1:
                hide_after = 1
            playlist_id = playlist.id
            device_id = device.id
            day = now.date().isoformat()
            await session.commit()

        payload = await playlist_service.get_watch_payload(token, public_base)
        if not allowed:
            payload.items = []
            payload.progress = None
            payload.allowed = False
            return payload, visitor
        counts = await self._today_completes(playlist_id, device_id, day) if hide_completed else {}
        if hide_completed:
            payload.items = [
                item for item in payload.items if counts.get(item.id, 0) < hide_after
            ]
            if payload.progress and all(item.id != payload.progress.item_id for item in payload.items):
                payload.progress = None
        for item in payload.items:
            item.public_url = f"/api/v1/watch/{token}/media/{item.id}"
            item.completed_today = int(counts.get(item.id, 0))
        payload.allowed = True
        payload.hide_completed = hide_completed
        payload.hide_after = hide_after
        eye = await self.eye_status(device_id)
        payload.eye_care = eye
        if eye.locked:
            payload.items = []
            payload.progress = None
        return payload, visitor

    async def media_file(self, token: str, visitor_token: str, item_id: int) -> Path:
        async with async_session() as session:
            await self._playlist(session, token)
            device = await self._device_by_token(session, visitor_token)
            if device is None:
                raise PermissionError("未识别设备")
            if not device.allowed:
                raise PermissionError("这台设备未允许播放")
            policy = await self._policy(session)
            locked = self._eye_locked(policy, device, local_naive())
            await session.commit()
            if locked:
                raise PermissionError("该休息一下")
            item = await session.get(PlaylistItemORM, item_id)
            playlist = await self._playlist(session, token)
            if not item or item.playlist_id != playlist.id:
                raise ValueError("条目不属于该播放列表")
            rel_path = item.rel_path
        try:
            return get_file_for_serve(to_storage_rel(rel_path))
        except ValueError as exc:
            raise ValueError("文件不存在") from exc

    async def record_event(
        self,
        token: str,
        visitor_token: str,
        visit_id: int,
        event_type: str,
        item_id: int,
        delta_sec: float = 0.0,
        at: datetime | None = None,
    ) -> dict:
        if event_type not in {"play", "tick", "complete"}:
            raise ValueError("事件类型无效")
        now = local_naive(at)
        if now.date() < retention_cutoff():
            return {"ok": True, "counted": False}
        await self.prune_expired()
        async with async_session() as session:
            playlist = await self._playlist(session, token)
            device = await self._device_by_token(session, visitor_token)
            if device is None:
                raise PermissionError("未识别设备")
            if not device.allowed:
                raise PermissionError("这台设备未允许播放")
            visit = await session.get(ShareVisitORM, visit_id)
            if (
                visit is None
                or visit.device_id != device.id
                or visit.playlist_id != playlist.id
            ):
                raise ValueError("访问记录无效")
            item = await session.get(PlaylistItemORM, item_id)
            if not item or item.playlist_id != playlist.id:
                raise ValueError("条目不属于该播放列表")

            policy = await self._policy(session)
            if self._eye_locked(policy, device, now):
                await session.commit()
                return {
                    "ok": True,
                    "counted": False,
                    "eye_rest": True,
                    "rest_remaining_sec": self._eye_remaining(device, now),
                }

            counted = True
            if event_type == "tick" and not (0 < delta_sec <= MAX_TICK_SEC):
                counted = False
            else:
                bucket = await self._bucket(
                    session, visit, device, item, now
                )
                if event_type == "play":
                    bucket.play_count += 1
                elif event_type == "complete":
                    bucket.complete_count += 1
                else:
                    bucket.watch_sec = float(bucket.watch_sec or 0) + float(delta_sec)
                    self._add_eye_play(policy, device, now, float(delta_sec))
                if bucket.first_played_at is None:
                    bucket.first_played_at = now
                bucket.last_played_at = now
                visit.last_seen_at = now
                device.last_seen_at = now
            eye_rest = bool(device.eye_locked_until and device.eye_locked_until > now)
            await session.commit()
            return {
                "ok": True,
                "counted": counted,
                "eye_rest": eye_rest and bool(policy.enabled),
                "rest_remaining_sec": self._eye_remaining(device, now) if policy.enabled else 0,
            }

    async def query_stats(self, start: date, end: date) -> ShareStatsResponse:
        await self.prune_expired(force=True)
        start_at = datetime.combine(start, time.min)
        end_at = datetime.combine(end, time.max)
        start_key = start.isoformat()
        end_key = end.isoformat()
        async with async_session() as session:
            visits = (
                await session.execute(
                    select(ShareVisitORM).where(
                        ShareVisitORM.started_at >= start_at,
                        ShareVisitORM.started_at <= end_at,
                    )
                )
            ).scalars().all()
            playbacks = (
                await session.execute(
                    select(SharePlaybackORM).where(
                        SharePlaybackORM.day >= start_key,
                        SharePlaybackORM.day <= end_key,
                    )
                )
            ).scalars().all()
            device_ids = {row.device_id for row in visits} | {row.device_id for row in playbacks}
            if not device_ids:
                return ShareStatsResponse(from_date=start_key, to_date=end_key, devices=[])
            devices = (
                await session.execute(
                    select(ShareDeviceORM).where(ShareDeviceORM.id.in_(device_ids))
                )
            ).scalars().all()

        by_device_days: dict[int, dict[str, ShareDayStat]] = {}
        by_device_items: dict[int, dict[int, ShareHotItem]] = {}
        watch_totals: dict[int, float] = {device.id: 0.0 for device in devices}

        for row in playbacks:
            day = by_device_days.setdefault(row.device_id, {}).get(row.day)
            if day is None:
                day = ShareDayStat(date=row.day)
                by_device_days.setdefault(row.device_id, {})[row.day] = day
            seconds = float(row.watch_sec or 0)
            day.watch_sec += seconds
            watch_totals[row.device_id] = watch_totals.get(row.device_id, 0.0) + seconds
            if row.first_played_at and (day.first_at is None or row.first_played_at < day.first_at):
                day.first_at = row.first_played_at
            if row.last_played_at and (day.last_at is None or row.last_played_at > day.last_at):
                day.last_at = row.last_played_at
            if seconds > 0:
                slot = next((hour for hour in day.hours if hour.hour == row.hour), None)
                if slot is None:
                    day.hours.append(ShareHourStat(hour=row.hour, watch_sec=seconds))
                else:
                    slot.watch_sec += seconds
            hot = by_device_items.setdefault(row.device_id, {}).get(row.item_id)
            if hot is None:
                hot = ShareHotItem(item_id=row.item_id, title=row.title or "")
                by_device_items.setdefault(row.device_id, {})[row.item_id] = hot
            hot.watch_sec += seconds
            hot.play_count += int(row.play_count or 0)
            hot.complete_count += int(row.complete_count or 0)
            if row.title:
                hot.title = row.title

        for row in visits:
            by_device_days.setdefault(row.device_id, {}).setdefault(
                row.started_at.date().isoformat(),
                ShareDayStat(date=row.started_at.date().isoformat()),
            )

        stats: list[ShareDeviceStat] = []
        for device in devices:
            days = list(by_device_days.get(device.id, {}).values())
            for day in days:
                day.hours.sort(key=lambda hour: hour.hour)
                day.watch_sec = round(day.watch_sec, 3)
                for hour in day.hours:
                    hour.watch_sec = round(hour.watch_sec, 3)
            days.sort(key=lambda day: day.date)
            hot_items = list(by_device_items.get(device.id, {}).values())
            hot_items = [
                item
                for item in hot_items
                if item.watch_sec > 0 or item.play_count > 0 or item.complete_count > 0
            ]
            hot_items.sort(key=lambda item: (-item.watch_sec, -item.play_count, item.item_id))
            for item in hot_items:
                item.watch_sec = round(item.watch_sec, 3)
            stats.append(
                ShareDeviceStat(
                    id=device.id,
                    device_label=device.device_label,
                    last_ip=device.last_ip,
                    user_agent=device.user_agent,
                    allowed=bool(device.allowed),
                    watch_sec=round(watch_totals.get(device.id, 0.0), 3),
                    by_day=days,
                    hot_items=hot_items,
                )
            )
        stats.sort(key=lambda row: (-row.watch_sec, row.id))
        return ShareStatsResponse(from_date=start_key, to_date=end_key, devices=stats)

    async def set_allowed(self, device_id: int, allowed: bool) -> ShareDeviceResponse:
        async with async_session() as session:
            device = await session.get(ShareDeviceORM, device_id)
            if device is None:
                raise ValueError("设备不存在")
            device.allowed = bool(allowed)
            await session.commit()
            await session.refresh(device)
            return self._device_response(device)

    async def _today_completes(self, playlist_id: int, device_id: int, day: str) -> dict[int, int]:
        async with async_session() as session:
            rows = (
                await session.execute(
                    select(
                        SharePlaybackORM.item_id,
                        func.coalesce(func.sum(SharePlaybackORM.complete_count), 0),
                    )
                    .where(
                        SharePlaybackORM.playlist_id == playlist_id,
                        SharePlaybackORM.device_id == device_id,
                        SharePlaybackORM.day == day,
                    )
                    .group_by(SharePlaybackORM.item_id)
                )
            ).all()
        return {int(item_id): int(total or 0) for item_id, total in rows}

    async def _playlist(self, session: AsyncSession, token: str) -> PlaylistORM:
        result = await session.execute(
            select(PlaylistORM).where(
                PlaylistORM.share_token == token,
                PlaylistORM.share_enabled.is_(True),
            )
        )
        playlist = result.scalar_one_or_none()
        if playlist is None:
            raise ValueError("分享不存在或已停用")
        return playlist

    async def _device_by_token(
        self, session: AsyncSession, visitor_token: str
    ) -> ShareDeviceORM | None:
        if not visitor_token:
            return None
        result = await session.execute(
            select(ShareDeviceORM).where(ShareDeviceORM.visitor_token == visitor_token)
        )
        return result.scalar_one_or_none()

    async def _ensure_device(
        self,
        session: AsyncSession,
        visitor_token: str,
        ip: str,
        user_agent: str,
        now: datetime,
    ) -> ShareDeviceORM:
        device = await self._device_by_token(session, visitor_token)
        label = device_label(user_agent)
        if device is None:
            device = ShareDeviceORM(
                visitor_token=secrets.token_urlsafe(24),
                device_label=label,
                user_agent=user_agent or "",
                last_ip=(ip or "")[:64],
                allowed=True,
                created_at=now,
                last_seen_at=now,
            )
            session.add(device)
            await session.flush()
            return device
        if user_agent:
            device.device_label = label
            device.user_agent = user_agent
        if ip:
            device.last_ip = ip[:64]
        device.last_seen_at = now
        return device

    async def _bucket(
        self,
        session: AsyncSession,
        visit: ShareVisitORM,
        device: ShareDeviceORM,
        item: PlaylistItemORM,
        now: datetime,
    ) -> SharePlaybackORM:
        day = now.date().isoformat()
        hour = now.hour
        result = await session.execute(
            select(SharePlaybackORM).where(
                SharePlaybackORM.visit_id == visit.id,
                SharePlaybackORM.item_id == item.id,
                SharePlaybackORM.day == day,
                SharePlaybackORM.hour == hour,
            )
        )
        bucket = result.scalar_one_or_none()
        if bucket is not None:
            return bucket
        title = item.title or item.rel_path.rsplit("/", 1)[-1]
        bucket = SharePlaybackORM(
            visit_id=visit.id,
            device_id=device.id,
            playlist_id=visit.playlist_id,
            item_id=item.id,
            title=title,
            day=day,
            hour=hour,
            watch_sec=0.0,
            play_count=0,
            complete_count=0,
        )
        session.add(bucket)
        await session.flush()
        return bucket

    @staticmethod
    def _device_response(device: ShareDeviceORM) -> ShareDeviceResponse:
        return ShareDeviceResponse(
            id=device.id,
            device_label=device.device_label,
            last_ip=device.last_ip,
            user_agent=device.user_agent,
            allowed=bool(device.allowed),
        )


share_watch = ShareWatchService()
